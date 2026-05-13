import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm.schema import validate_plan


def test_valid_plan_has_no_errors():
    plan = {
        "goal": "move from table 1 to table 2",
        "steps": [
            {"id": "s1", "skill": "locate_table", "args": {"label": "1"}},
            {"id": "s2", "skill": "navigate_to", "args": {"target": "table_2"}},
        ],
    }
    assert validate_plan(plan) == []


def test_unknown_skill_is_rejected():
    plan = {
        "steps": [
            {"id": "s1", "skill": "run_arbitrary_code", "args": {}},
        ],
    }
    assert validate_plan(plan)

