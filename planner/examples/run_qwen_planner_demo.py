import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.llm.qwen_client import QwenPlannerClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a robot long-sequence plan from one image and task.")
    parser.add_argument("--image", required=True, help="Path to the lab image.")
    parser.add_argument("--task", required=True, help="Natural-language robot task.")
    parser.add_argument("--skills", default=str(ROOT / "planner" / "configs" / "skills.yaml"))
    parser.add_argument("--scene", default=str(ROOT / "planner" / "configs" / "lab_scene_template.yaml"))
    parser.add_argument("--model", default=None, help="Override Qwen model name.")
    parser.add_argument("--verbose", action="store_true", help="Print request and response metadata.")
    args = parser.parse_args()

    planner = QwenPlannerClient(model=args.model)
    plan = planner.plan_from_image(
        image_path=args.image,
        user_task=args.task,
        skills_path=args.skills,
        scene_path=args.scene,
    )

    if args.verbose:
        debug_info = {
            "api_key_present": bool(os.getenv("DASHSCOPE_API_KEY")),
            "meta": planner.last_response_meta,
        }
        print(json.dumps(debug_info, ensure_ascii=False, indent=2), file=sys.stderr)

    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
