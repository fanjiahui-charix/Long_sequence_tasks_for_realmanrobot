from __future__ import annotations

from dataclasses import asdict
from typing import Any

from planner.llm.schema import validate_plan
from planner.skills.base import SkillResult


class TaskExecutor:
    def __init__(self, skill_registry: dict[str, Any]) -> None:
        self.skill_registry = skill_registry

    def execute(self, plan: dict) -> dict:
        errors = validate_plan(plan)
        if errors:
            return asdict(SkillResult(ok=False, error="invalid plan", data={"errors": errors}))

        history = []
        for step in plan["steps"]:
            skill_name = step["skill"]
            skill = self.skill_registry.get(skill_name)
            if skill is None:
                return asdict(
                    SkillResult(
                        ok=False,
                        error=f"skill not registered: {skill_name}",
                        data={"history": history},
                    )
                )

            result = skill.run(**step.get("args", {}))
            history.append({"step": step, "result": asdict(result)})
            if not result.ok:
                return asdict(SkillResult(ok=False, error=result.error, data={"history": history}))

        return asdict(SkillResult(ok=True, data={"history": history}))
