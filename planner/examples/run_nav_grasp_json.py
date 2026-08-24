#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from navigation.chassis_client import ChassisNavigationClient, ChassisNavigationError
from planner.agent_runtime.protocol import extract_machine_result


_extract_machine_result = extract_machine_result


DEFAULT_READY_JOINTS = [60.404, 57.102, 47.738, 69.798, 73.903, 40.15]
DEFAULT_GRASP_JOINTS = [60.404, 57.102, 47.738, 69.798, 73.903, 40.15]
SUCCESS_STATES = {"idle", "success", "succeeded", "done", "completed", "arrived", "finished", "stop", "stopped"}
FAILURE_STATES = {"failed", "error", "aborted", "canceled", "cancelled"}
ACTIVE_STATES = {"moving", "running", "planning", "navigating", "busy"}
DEFAULT_ARM_DEMO_PATH = Path("/home/rm/catkin_ws/src/rm_dual_arm_demos/arm_demo/scripts/arm_demo_65_grasp.py")
DEFAULT_ROS_SETUP = Path("/opt/ros/noetic/setup.bash")
DEFAULT_CATKIN_SETUP = Path("/home/rm/catkin_ws/devel/setup.bash")


def extract_markers_in_order(task: str) -> list[str]:
    markers: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(point[_]?[a-z0-9]+|dian[_]?[a-z0-9]+)", task.lower()):
        marker = match.group(1)
        if marker not in seen:
            markers.append(marker)
            seen.add(marker)
    return markers


def task_requests_grasp(task: str) -> bool:
    normalized = task.lower()
    return any(keyword in normalized for keyword in ("抓", "取", "pick", "grasp", "close hand"))


def _parse_float_list(raw_value: str, expected_len: int, name: str) -> list[float]:
    values = json.loads(raw_value)
    if not isinstance(values, list) or len(values) != expected_len:
        raise ValueError(f"{name} must be a JSON array with {expected_len} values")
    return [float(value) for value in values]


def _status_results(status_response: dict[str, Any]) -> dict[str, Any]:
    parsed = status_response.get("response", [])
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("results"), dict):
            return item["results"]
    raise ChassisNavigationError("No chassis status payload found in response")


def _wait_for_marker_arrival(
    client: ChassisNavigationClient,
    marker: str,
    *,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    seen_active = False
    last_results: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        status_response = client.status()
        results = _status_results(status_response)
        last_results = results
        move_target = str(results.get("move_target", "") or "").lower()
        move_status = str(results.get("move_status", "") or "").lower()
        running_status = str(results.get("running_status", "") or "").lower()

        if move_target == marker.lower() or move_status in ACTIVE_STATES or running_status in ACTIVE_STATES:
            seen_active = True

        if seen_active and (move_status in FAILURE_STATES or running_status in FAILURE_STATES):
            raise RuntimeError(
                f"Navigation to {marker} failed with move_status={move_status or 'unknown'} "
                f"running_status={running_status or 'unknown'}"
            )

        if seen_active and (
            move_status in SUCCESS_STATES
            or running_status in SUCCESS_STATES
            or (move_target == "" and move_status == "idle")
        ):
            return {
                "marker": marker,
                "move_status": results.get("move_status"),
                "running_status": results.get("running_status"),
                "move_target": results.get("move_target"),
                "current_pose": results.get("current_pose"),
                "power_percent": results.get("power_percent"),
            }

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out waiting for arrival at {marker}. Last status: {json.dumps(last_results or {}, ensure_ascii=False)}"
    )


def _load_arm_demo_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("arm_demo_65_grasp_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load arm demo script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_right_arm_grasp(
    *,
    arm_demo_script: Path,
    ready_joint_degrees: Sequence[float],
    grasp_joint_degrees: Sequence[float],
    ros_setup: Path,
    catkin_setup: Path,
) -> dict[str, Any]:
    ready_arg = json.dumps([float(value) for value in ready_joint_degrees], ensure_ascii=False)
    grasp_arg = json.dumps([float(value) for value in grasp_joint_degrees], ensure_ascii=False)
    command = " ".join(
        [
            "source",
            shlex.quote(str(ros_setup)),
            "&&",
            "source",
            shlex.quote(str(catkin_setup)),
            "&&",
            "/usr/bin/python3",
            shlex.quote(str(arm_demo_script)),
            "_arm_ns:=r_arm",
            f"_ready_joint_degrees:={shlex.quote(ready_arg)}",
            f"_grasp_joint_degrees:={shlex.quote(grasp_arg)}",
        ]
    )
    completed = subprocess.run(
        ["bash", "-lc", command],
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        detail = stderr or stdout or f"grasp subprocess exited with code {completed.returncode}"
        raise RuntimeError(f"Right-arm grasp failed: {detail}")
    try:
        return _extract_machine_result(stdout)
    except RuntimeError as exc:
        raise RuntimeError(f"Right-arm grasp returned no machine JSON result: {stdout}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-click JSON runner: prompt -> point navigation -> right-arm hardcoded grasp demo."
    )
    parser.add_argument("--task", required=True, help="Prompt text, e.g. '从pointa到pointb然后抓取'.")
    parser.add_argument("--host", default=os.getenv("LONG_TASKS_CHASSIS_HOST", "192.168.10.10"))
    parser.add_argument("--port", type=int, default=int(os.getenv("LONG_TASKS_CHASSIS_PORT", "31001")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("LONG_TASKS_CHASSIS_TIMEOUT", "3.0")))
    parser.add_argument("--arrival-timeout", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--ready-joint-degrees",
        default=json.dumps(DEFAULT_READY_JOINTS, ensure_ascii=False),
        help="JSON array for the right arm ready joint degrees.",
    )
    parser.add_argument(
        "--grasp-joint-degrees",
        default=json.dumps(DEFAULT_GRASP_JOINTS, ensure_ascii=False),
        help="JSON array for the right arm grasp joint degrees.",
    )
    parser.add_argument(
        "--arm-demo-script",
        default=str(Path(os.getenv("LONG_TASKS_ARM_DEMO_SCRIPT", str(DEFAULT_ARM_DEMO_PATH)))),
    )
    parser.add_argument(
        "--ros-setup",
        default=str(Path(os.getenv("LONG_TASKS_ROS_SETUP", str(DEFAULT_ROS_SETUP)))),
    )
    parser.add_argument(
        "--catkin-setup",
        default=str(Path(os.getenv("LONG_TASKS_CATKIN_SETUP", str(DEFAULT_CATKIN_SETUP)))),
    )
    parser.add_argument("--skip-grasp", action="store_true", help="Only navigate; do not run the right-arm grasp demo.")
    parser.add_argument("--save-result", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    markers = extract_markers_in_order(args.task)
    if len(markers) < 2:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Prompt must include at least two markers such as pointa and pointb.",
                    "task": args.task,
                    "markers": markers,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    ready_joint_degrees = _parse_float_list(args.ready_joint_degrees, 6, "ready_joint_degrees")
    grasp_joint_degrees = _parse_float_list(args.grasp_joint_degrees, 6, "grasp_joint_degrees")
    requires_grasp = not args.skip_grasp
    arm_demo_script = Path(args.arm_demo_script).expanduser()
    ros_setup = Path(args.ros_setup).expanduser()
    catkin_setup = Path(args.catkin_setup).expanduser()
    if not arm_demo_script.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Right-arm grasp script not found: {arm_demo_script}",
                    "task": args.task,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    if not ros_setup.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"ROS setup script not found: {ros_setup}",
                    "task": args.task,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    if not catkin_setup.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Catkin setup script not found: {catkin_setup}",
                    "task": args.task,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    result: dict[str, Any] = {
        "ok": False,
        "task": args.task,
        "plan": {
            "markers": markers,
            "requires_grasp": requires_grasp,
            "prompt_mentions_grasp": task_requests_grasp(args.task),
            "arm_ns": "r_arm",
            "ready_joint_degrees": ready_joint_degrees,
            "grasp_joint_degrees": grasp_joint_degrees,
        },
        "navigation": [],
        "grasp": None,
    }

    try:
        client = ChassisNavigationClient(host=args.host, port=args.port, timeout=args.timeout)
        for marker in markers:
            send_result = client.move_marker(marker)
            arrival_result = _wait_for_marker_arrival(
                client,
                marker,
                timeout=args.arrival_timeout,
                poll_interval=args.poll_interval,
            )
            result["navigation"].append(
                {
                    "send": send_result,
                    "arrival": arrival_result,
                }
            )

        if requires_grasp:
            result["grasp"] = _run_right_arm_grasp(
                arm_demo_script=arm_demo_script,
                ready_joint_degrees=ready_joint_degrees,
                grasp_joint_degrees=grasp_joint_degrees,
                ros_setup=ros_setup,
                catkin_setup=catkin_setup,
            )

        result["ok"] = True
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)

    if args.save_result:
        output_path = Path(args.save_result).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
