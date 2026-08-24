from typing import Any

from planner.agent_runtime.models import ExecStatus, FailureCode

from .base import SkillResult


class AskHumanSkill:
    name = "ask_human"

    def run(self, **kwargs: Any) -> SkillResult:
        question = kwargs.get("question", "Need human clarification.")
        return SkillResult.rejected(
            FailureCode.PRECONDITION_FAILED,
            message="human input required",
            data={"question": question},
        )


class AbortSkill:
    name = "abort"

    def run(self, **kwargs: Any) -> SkillResult:
        reason = kwargs.get("reason", "Task aborted.")
        return SkillResult(
            status=ExecStatus.CANCELLED,
            failure_code=FailureCode.PRECONDITION_FAILED,
            message=str(reason),
            data={"reason": reason},
        )

