#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.agent_runtime.models import MissionPlan
from planner.examples.run_long_task import build_runtime
from planner.llm.qwen_client import QwenPlannerClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Qwen plan and execute the closed loop in mock.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--trajectory", default=None)
    parser.add_argument("--mission-timeout", type=float, default=300.0)
    parser.add_argument("--max-total-actions", type=int, default=50)
    parser.add_argument("--max-replans", type=int, default=0)
    parser.add_argument("--failure-repeat-threshold", type=int, default=3)
    args = parser.parse_args()

    os.environ["LONG_TASKS_NAV_BACKEND"] = "mock"
    os.environ["LONG_TASKS_PERCEPTION_BACKEND"] = "mock"
    os.environ["LONG_TASKS_MANIPULATION_BACKEND"] = "mock"
    args.mission_id = uuid.uuid4().hex

    planner = QwenPlannerClient(model=args.model)
    raw_plan = planner.plan_from_image(
        image_path=args.image,
        user_task=args.task,
        skills_path=ROOT / "planner" / "configs" / "skills.yaml",
        scene_path=ROOT / "planner" / "configs" / "lab_scene_template.yaml",
    )
    plan = MissionPlan.from_dict(raw_plan)
    trace_path = args.trajectory or ROOT / "runtime" / "trajectories" / f"{args.mission_id}.jsonl"
    runtime = build_runtime(plan, args, trace_path=trace_path, planner_client=planner)
    result = runtime.run()

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
