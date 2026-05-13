from typing import Any

from .base import SkillResult


class AskHumanSkill:
    name = "ask_human"

    def run(self, **kwargs: Any) -> SkillResult:
        question = kwargs.get("question", "Need human clarification.")
        return SkillResult(ok=False, data={"question": question}, error="human input required")


class AbortSkill:
    name = "abort"

    def run(self, **kwargs: Any) -> SkillResult:
        reason = kwargs.get("reason", "Task aborted.")
        return SkillResult(ok=False, data={"reason": reason}, error=reason)

