#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from navigation.chassis_client import ChassisNavigationClient, ChassisNavigationError
from planner.executor.task_executor import TaskExecutor
from planner.llm.qwen_client import QwenPlannerClient
from planner.skills.registry import build_default_skill_registry
from vision_grasp.camera.ros_image_capture import RosImageCaptureError, capture_rgb_image


def _patch_plan(plan: dict, pick_mode: str, task: str, nav_backend: str) -> dict:
    patched = json.loads(json.dumps(plan))

    explicit_marker = _detect_explicit_marker(task, nav_backend)
    if explicit_marker:
        patched["goal"] = task
        patched["steps"] = [
            {
                "id": "s1",
                "skill": "navigate_to",
                "args": {
                    "marker": explicit_marker,
                },
            }
        ]
        patched["failure_policy"] = {
            "on_failure": "abort",
            "reason": f"Could not navigate to marker {explicit_marker}.",
        }

    if pick_mode == "as_planned":
        return patched

    for step in patched.get("steps", []):
        if step.get("skill") == "pick_object":
            args = step.setdefault("args", {})
            args["mode"] = pick_mode
    return patched


def _candidate_markers(nav_backend: str) -> set[str]:
    markers = set()
    markers.update({"pointc", "pointd", "point_a", "point_b", "start_point", "end_point"})

    if nav_backend != "tcp":
        return markers

    try:
        client = ChassisNavigationClient(
            host=os.getenv("LONG_TASKS_CHASSIS_HOST", "192.168.10.10"),
            port=int(os.getenv("LONG_TASKS_CHASSIS_PORT", "31001")),
            timeout=float(os.getenv("LONG_TASKS_CHASSIS_TIMEOUT", "3.0")),
        )
        response = client.markers()
        parsed = response.get("response", [])
        for item in parsed:
            if not isinstance(item, dict):
                continue
            results = item.get("results", {})
            if isinstance(results, dict):
                markers.update(str(key).lower() for key in results.keys())
    except (ValueError, ChassisNavigationError):
        pass

    return markers


def _detect_explicit_marker(task: str, nav_backend: str) -> str | None:
    normalized = task.lower()
    tokens = set(re.findall(r"[a-zA-Z0-9_]+", normalized))
    for marker in sorted(_candidate_markers(nav_backend), key=len, reverse=True):
        if marker in tokens or marker in normalized:
            return marker
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a long-sequence plan from one image and execute it in one command."
    )
    parser.add_argument("--image", default=None, help="Path to the lab image.")
    parser.add_argument("--camera-name", default=None, help="Capture a current RGB image from this ROS camera name.")
    parser.add_argument("--image-topic", default=None, help="Optional explicit ROS image topic.")
    parser.add_argument("--capture-timeout", default=5.0, type=float)
    parser.add_argument(
        "--capture-path",
        default="/tmp/long_tasks_current_rgb.jpg",
        help="Where to save a captured current RGB frame.",
    )
    parser.add_argument("--task", required=True, help="Natural-language robot task.")
    parser.add_argument("--model", default=None, help="Override Qwen model name.")
    parser.add_argument("--skills", default=str(ROOT / "planner" / "configs" / "skills.yaml"))
    parser.add_argument("--scene", default=str(ROOT / "planner" / "configs" / "lab_scene_template.yaml"))
    parser.add_argument("--nav-backend", default="mock", choices=["mock", "tcp", "ros"])
    parser.add_argument("--manipulation-backend", default="mock", choices=["mock", "ros"])
    parser.add_argument(
        "--pick-mode",
        default="as_planned",
        choices=["as_planned", "close_only", "pick_demo", "pose_grasp"],
        help="Override how pick_object executes.",
    )
    parser.add_argument("--save-plan", default=None, help="Optional path to save the generated plan JSON.")
    parser.add_argument("--save-result", default=None, help="Optional path to save the execution result JSON.")
    parser.add_argument("--verbose", action="store_true", help="Print planner response metadata.")
    args = parser.parse_args()

    if not args.image and not args.camera_name:
        parser.error("one of --image or --camera-name is required")

    os.environ["LONG_TASKS_NAV_BACKEND"] = args.nav_backend
    os.environ["LONG_TASKS_MANIPULATION_BACKEND"] = args.manipulation_backend

    image_path = args.image
    if args.camera_name:
        try:
            image_path = capture_rgb_image(
                output_path=args.capture_path,
                camera_name=args.camera_name,
                timeout=args.capture_timeout,
                topic=args.image_topic,
            )
        except RosImageCaptureError as exc:
            raise SystemExit(str(exc))

    planner = QwenPlannerClient(model=args.model)
    plan = planner.plan_from_image(
        image_path=image_path,
        user_task=args.task,
        skills_path=args.skills,
        scene_path=args.scene,
    )
    plan = _patch_plan(plan, args.pick_mode, args.task, args.nav_backend)

    if args.save_plan:
        plan_path = Path(args.save_plan)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    executor = TaskExecutor(build_default_skill_registry())
    result = executor.execute(plan)

    if args.save_result:
        result_path = Path(args.save_result)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.verbose:
        meta = {
            "request_model": planner.last_response_meta.get("request_model"),
            "response_model": planner.last_response_meta.get("response_model"),
            "response_id": planner.last_response_meta.get("response_id"),
            "usage": planner.last_response_meta.get("usage"),
            "image_path": image_path,
            "nav_backend": args.nav_backend,
            "manipulation_backend": args.manipulation_backend,
            "pick_mode": args.pick_mode,
        }
        print("=== META ===")
        print(json.dumps(meta, ensure_ascii=False, indent=2))

    print("=== PLAN ===")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print("=== EXECUTION RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
