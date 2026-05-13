import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from planner.executor.task_executor import TaskExecutor
from planner.llm.qwen_client import QwenPlannerClient
from planner.skills.registry import build_default_skill_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Qwen plan and execute it with mock skills.")
    parser.add_argument("--image", required=True, help="Path to the lab image.")
    parser.add_argument("--task", required=True, help="Natural-language robot task.")
    parser.add_argument("--model", default=None, help="Override Qwen model name.")
    args = parser.parse_args()

    planner = QwenPlannerClient(model=args.model)
    plan = planner.plan_from_image(
        image_path=args.image,
        user_task=args.task,
        skills_path=ROOT / "planner" / "configs" / "skills.yaml",
        scene_path=ROOT / "planner" / "configs" / "lab_scene_template.yaml",
    )

    executor = TaskExecutor(build_default_skill_registry())
    result = executor.execute(plan)

    print("=== PLAN ===")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print("=== MOCK EXECUTION RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
