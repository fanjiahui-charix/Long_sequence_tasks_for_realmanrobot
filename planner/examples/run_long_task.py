#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from navigation.chassis_client import ChassisNavigationClient, ChassisNavigationError
from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.executor import SkillExecutor
from planner.agent_runtime.models import MissionBudgets, MissionPlan
from planner.agent_runtime.recovery import RecoveryPolicy
from planner.agent_runtime.replanner import NoOpReplanner, QwenReplanner
from planner.agent_runtime.runtime import AgentRuntime
from planner.agent_runtime.state import WorldState
from planner.agent_runtime.trace import JsonlTraceWriter
from planner.agent_runtime.verifiers import (
    GoalVerifier,
    SkillObservationProvider,
    VerifierRegistry,
)
from planner.llm.qwen_client import QwenPlannerClient


def _patch_plan(plan: dict, pick_mode: str, task: str, nav_backend: str) -> dict:
    patched = json.loads(json.dumps(plan))
    explicit_marker = _detect_explicit_marker(task, nav_backend)
    if explicit_marker:
        for step in patched.get("steps", []):
            if step.get("skill") == "navigate_to":
                step_args = step.setdefault("args", {})
                step_args["target"] = explicit_marker
                step_args["marker"] = explicit_marker
                break
    if pick_mode != "as_planned":
        for step in patched.get("steps", []):
            if step.get("skill") == "pick_object":
                step.setdefault("args", {})["mode"] = pick_mode
    return patched


def _candidate_markers(nav_backend: str) -> set[str]:
    markers = {
        "pointa",
        "pointb",
        "pointc",
        "pointd",
        "point_a",
        "point_b",
        "start_point",
        "end_point",
    }
    if nav_backend != "tcp":
        return markers
    try:
        client = ChassisNavigationClient(
            host=os.getenv("LONG_TASKS_CHASSIS_HOST", "192.168.10.10"),
            port=int(os.getenv("LONG_TASKS_CHASSIS_PORT", "31001")),
            timeout=float(os.getenv("LONG_TASKS_CHASSIS_TIMEOUT", "3.0")),
        )
        parsed = client.markers().get("response", [])
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("results"), dict):
                markers.update(str(key).lower() for key in item["results"])
    except (ValueError, ChassisNavigationError):
        pass
    return markers


def _detect_explicit_marker(task: str, nav_backend: str) -> str | None:
    normalized = task.lower()
    tokens = set(re.findall(r"[a-zA-Z0-9_]+", normalized))
    for marker in sorted(_candidate_markers(nav_backend), key=lambda value: (-len(value), value)):
        if marker in tokens:
            return marker
    return None


def _goal_observer(skill_registry: dict[str, Any]):
    def observe(goal: dict[str, Any], _state: WorldState) -> dict[str, Any]:
        goal_type = goal.get("type")
        try:
            if goal_type == "holding_object":
                skill = skill_registry["pick_object"]
                return skill.observe(object=goal.get("object"))
            if goal_type in {"at", "at_location"}:
                target = goal.get("location") or goal.get("target")
                skill = skill_registry["navigate_to"]
                result = skill.observe(target=target)
                if result.get("arrived") is True:
                    result["current_location"] = target
                return result
            if goal_type in {"placed_object", "object_placed"}:
                target = goal.get("target")
                return skill_registry["place_object"].observe(target=target)
        except Exception as exc:
            return {"observation_error": f"{type(exc).__name__}: {exc}"}
        return {"observation_error": f"unsupported structured goal: {goal_type}"}

    return observe


def build_runtime(
    plan: MissionPlan,
    args: argparse.Namespace,
    *,
    trace_path: str | Path,
    planner_client: QwenPlannerClient | None = None,
) -> AgentRuntime:
    from planner.skills.registry import build_default_skill_registry

    mission_id = getattr(args, "mission_id", None) or uuid.uuid4().hex
    registry = build_default_skill_registry()
    replanner = (
        QwenReplanner(planner_client)
        if planner_client is not None and planner_client.api_key
        else NoOpReplanner()
    )
    budgets = MissionBudgets(
        mission_timeout_s=float(args.mission_timeout),
        max_total_actions=int(args.max_total_actions),
        max_replans=int(args.max_replans),
        repeated_failure_threshold=int(args.failure_repeat_threshold),
    )
    trace = JsonlTraceWriter(trace_path, mission_id=mission_id)
    return AgentRuntime(
        mission_id=mission_id,
        plan=plan,
        state=WorldState(),
        contracts=default_contracts(),
        skill_registry=registry,
        executor=SkillExecutor(),
        observation_provider=SkillObservationProvider(registry),
        verifiers=VerifierRegistry(),
        goal_verifier=GoalVerifier(),
        recovery_policy=RecoveryPolicy(),
        replanner=replanner,
        budgets=budgets,
        trace=trace,
        goal_observer=_goal_observer(registry),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and execute a long robot mission through AgentRuntime."
    )
    parser.add_argument("--image", default=None, help="Path to the lab image.")
    parser.add_argument("--camera-name", default=None, help="Capture RGB from this ROS camera.")
    parser.add_argument("--image-topic", default=None)
    parser.add_argument("--capture-timeout", default=5.0, type=float)
    parser.add_argument("--capture-path", default="/tmp/long_tasks_current_rgb.jpg")
    parser.add_argument("--task", required=True, help="Natural-language robot task.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--skills", default=str(ROOT / "planner" / "configs" / "skills.yaml"))
    parser.add_argument("--scene", default=str(ROOT / "planner" / "configs" / "lab_scene_template.yaml"))
    parser.add_argument("--nav-backend", default="mock", choices=["mock", "tcp", "ros"])
    parser.add_argument(
        "--perception-backend",
        default="mock",
        choices=["mock", "foundationpose"],
    )
    parser.add_argument("--manipulation-backend", default="mock", choices=["mock", "ros"])
    parser.add_argument(
        "--pick-mode",
        default="as_planned",
        choices=["as_planned", "close_only", "pick_demo", "pose_grasp"],
    )
    parser.add_argument("--mission-id", default=None)
    parser.add_argument("--mission-timeout", default=900.0, type=float)
    parser.add_argument("--max-total-actions", default=50, type=int)
    parser.add_argument("--max-replans", default=3, type=int)
    parser.add_argument("--failure-repeat-threshold", default=3, type=int)
    parser.add_argument("--trajectory", default=None)
    parser.add_argument("--save-plan", default=None)
    parser.add_argument("--save-result", default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.image and not args.camera_name:
        parser.error("one of --image or --camera-name is required")

    os.environ["LONG_TASKS_NAV_BACKEND"] = args.nav_backend
    os.environ["LONG_TASKS_PERCEPTION_BACKEND"] = args.perception_backend
    os.environ["LONG_TASKS_MANIPULATION_BACKEND"] = args.manipulation_backend

    image_path = args.image
    if args.camera_name:
        try:
            from vision_grasp.camera.ros_image_capture import (
                RosImageCaptureError,
                capture_rgb_image,
            )
        except ImportError as exc:
            raise SystemExit(f"ROS image capture adapter is unavailable: {exc}") from exc
        try:
            image_path = capture_rgb_image(
                output_path=args.capture_path,
                camera_name=args.camera_name,
                timeout=args.capture_timeout,
                topic=args.image_topic,
            )
        except RosImageCaptureError as exc:
            raise SystemExit(str(exc)) from exc

    planner = QwenPlannerClient(model=args.model)
    raw_plan = planner.plan_from_image(
        image_path=image_path,
        user_task=args.task,
        skills_path=args.skills,
        scene_path=args.scene,
    )
    raw_plan = _patch_plan(raw_plan, args.pick_mode, args.task, args.nav_backend)
    plan = MissionPlan.from_dict(raw_plan)

    if args.save_plan:
        output = Path(args.save_plan)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    mission_id = args.mission_id or uuid.uuid4().hex
    args.mission_id = mission_id
    trace_path = args.trajectory or ROOT / "runtime" / "trajectories" / f"{mission_id}.jsonl"
    runtime = build_runtime(plan, args, trace_path=trace_path, planner_client=planner)
    result = runtime.run()
    result_payload = result.to_dict()

    if args.save_result:
        output = Path(args.save_result)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.verbose:
        print(json.dumps({"planner": planner.last_response_meta}, ensure_ascii=False, indent=2), file=sys.stderr)
    print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
