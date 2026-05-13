from __future__ import annotations

ALLOWED_SKILLS = {
    "locate_table",
    "plan_path",
    "navigate_to",
    "align_to_table",
    "look_at",
    "detect_object",
    "pick_object",
    "place_object",
    "ask_human",
    "abort",
}


def validate_plan(plan: dict) -> list[str]:
    """Return validation errors for an LLM-generated plan."""
    errors: list[str] = []

    if not isinstance(plan, dict):
        return ["plan must be a JSON object"]

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("plan.steps must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{index}] must be an object")
            continue

        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            errors.append(f"steps[{index}].id must be a non-empty string")
        elif step_id in seen_ids:
            errors.append(f"duplicate step id: {step_id}")
        else:
            seen_ids.add(step_id)

        skill = step.get("skill")
        if skill not in ALLOWED_SKILLS:
            errors.append(f"steps[{index}].skill is not allowed: {skill}")

        args = step.get("args")
        if not isinstance(args, dict):
            errors.append(f"steps[{index}].args must be an object")

    return errors
