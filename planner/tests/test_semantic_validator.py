from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.models import MissionPlan
from planner.agent_runtime.semantic_validator import SemanticPlanValidator
from planner.llm.schema import validate_plan


def test_pick_without_localization_is_rejected():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
                {
                    "id": "s2",
                    "skill": "pick_object",
                    "args": {"object": "cup"},
                    "depends_on": ["s1"],
                },
            ],
        }
    )

    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})

    assert any("ObjectLocalized(cup)" in error for error in errors)


def test_detect_then_pick_is_semantically_valid():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}},
                {
                    "id": "s2",
                    "skill": "pick_object",
                    "args": {"object": "cup"},
                    "depends_on": ["s1"],
                },
            ],
        }
    )

    assert SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"}) == []


def test_plan_cannot_override_runtime_policy():
    errors = validate_plan(
        {
            "steps": [
                {
                    "id": "s1",
                    "skill": "navigate_to",
                    "args": {"target": "pointb"},
                    "max_retry": 99,
                }
            ]
        }
    )

    assert any("runtime policy" in error for error in errors)


def test_unknown_dependency_is_rejected():
    plan = MissionPlan.from_dict(
        {
            "steps": [
                {
                    "id": "s1",
                    "skill": "navigate_to",
                    "args": {"target": "pointb"},
                    "depends_on": ["missing"],
                }
            ]
        }
    )

    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})

    assert errors == ["step s1 depends on unknown or later step: missing"]


def test_missing_required_contract_argument_is_rejected():
    plan = MissionPlan.from_dict(
        {"steps": [{"id": "s1", "skill": "detect_object", "args": {}}]}
    )

    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})

    assert "step s1 missing required argument: object" in errors


def test_duplicate_step_id_is_rejected():
    plan = MissionPlan.from_dict(
        {
            "steps": [
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointa"}},
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
            ]
        }
    )

    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})

    assert "duplicate step id: s1" in errors


def test_place_without_any_held_object_is_rejected():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "placed_object", "target": "table_1"},
            "steps": [
                {"id": "s1", "skill": "place_object", "args": {"target": "table_1"}}
            ],
        }
    )

    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})

    assert errors == ["step s1 missing required facts: Holding(*)"]
