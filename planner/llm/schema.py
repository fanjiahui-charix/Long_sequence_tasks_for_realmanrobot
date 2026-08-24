from __future__ import annotations

from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.models import MissionPlan
from planner.agent_runtime.semantic_validator import SemanticPlanValidator


RUNTIME_POLICY_KEYS = {
    "failure_policy",
    "max_retry",
    "max_retries",
    "max_attempts",
    "retry",
    "timeout",
    "timeout_s",
    "verifier",
    "success_criteria",
    "recovery",
}


def validate_plan(plan: dict) -> list[str]:
    """Return validation errors for an LLM-generated plan."""
    if not isinstance(plan, dict):
        return ["plan must be a JSON object"]

    errors: list[str] = []
    forbidden_top_level = sorted(RUNTIME_POLICY_KEYS.intersection(plan))
    for key in forbidden_top_level:
        errors.append(f"plan contains runtime policy key controlled by code: {key}")
    steps = plan.get("steps")
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            for key in sorted(RUNTIME_POLICY_KEYS.intersection(step)):
                errors.append(
                    f"steps[{index}] contains runtime policy key controlled by code: {key}"
                )

    try:
        parsed = MissionPlan.from_dict(plan)
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    errors.extend(SemanticPlanValidator(default_contracts()).validate(parsed, {"HandEmpty"}))
    return errors
