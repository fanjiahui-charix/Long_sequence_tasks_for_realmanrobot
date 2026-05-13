import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from executor.task_executor import TaskExecutor
from skills.registry import build_default_skill_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a generated plan using prototype local skills.")
    parser.add_argument("--plan", required=True, help="Path to a plan JSON file.")
    args = parser.parse_args()

    with Path(args.plan).open("r", encoding="utf-8") as f:
        plan = json.load(f)

    executor = TaskExecutor(build_default_skill_registry())
    result = executor.execute(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

