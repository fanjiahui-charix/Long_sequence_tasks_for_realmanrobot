"""Turn execution evidence into bounded advisory experience, using the agent's client."""

from __future__ import annotations

from ..deadlines import wait_with_deadline
from ..schemas import Episode, ExperienceSummary
from .planning import classify_failure, decision_error_reasons, project_decision


class ExperienceConsolidator:
    def __init__(self, client, *, timeout_s=30):
        if timeout_s <= 0:
            raise ValueError("consolidation timeout must be positive")
        self.client = client
        self.timeout_s = timeout_s

    async def summarize(self, episode: Episode) -> ExperienceSummary:
        summarize = getattr(self.client, "summarize_experience", None)
        if not callable(summarize):
            raise ValueError("model client does not support experience consolidation")
        failed = next(
            (
                item
                for item in episode.decision_trace
                if item.turn == episode.failure_turn
            ),
            None,
        )
        if failed is None:
            raise ValueError("decision evidence is required for reflection")
        attribution, supported = classify_failure(failed)
        if (
            attribution != episode.failure_attribution
            or supported != episode.decision_error_verified
        ):
            raise ValueError("failure attribution must agree with runtime evidence")
        context = {
            "task_type": episode.task_type,
            "object_category": episode.object_category,
            "executed_skill": episode.executed_skill,
            "failure_type": episode.failure_type,
            "failure_turn": episode.failure_turn,
            "failure_attribution": attribution,
            "decision_error_verified": supported,
            "runtime_findings": decision_error_reasons(failed),
            "decision_trace": [
                project_decision(item) for item in episode.decision_trace
            ],
            "recovery_strategy": episode.recovery_strategy,
            "recovery_result": episode.recovery_result,
            "recovery_verified": episode.verified,
            "verification_result": {
                key: episode.verification_result[key]
                for key in ("location", "grasp_state", "target", "calibration_origin")
                if key in episode.verification_result
            },
        }
        result = await wait_with_deadline(summarize(context), self.timeout_s)
        # A client returning a dict or a constructed model cannot bypass validation.
        if isinstance(result, ExperienceSummary):
            result = result.model_dump(mode="json")
        experience = ExperienceSummary.model_validate(result)
        turns = {item.turn for item in episode.decision_trace}
        if episode.failure_turn not in experience.source_turns or not set(
            experience.source_turns
        ).issubset(turns):
            raise ValueError("reflection must cite actual decision turns")
        if supported != bool(experience.decision_issue):
            raise ValueError("decision issue must follow the deterministic attribution")
        return experience
