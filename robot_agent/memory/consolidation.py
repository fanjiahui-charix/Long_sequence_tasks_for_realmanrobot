"""Turn execution evidence into bounded advisory experience, using the agent's client."""

from __future__ import annotations

from ..deadlines import wait_with_deadline
from ..schemas import Episode, ExperienceSummary


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
        observation = episode.failure_observation
        # Do not copy image/file references, pose matrices or arbitrary raw driver payloads.
        facts = {
            key: observation[key]
            for key in (
                "timestamp",
                "source",
                "robot_location",
                "localization_confirmed",
                "navigation_status",
                "arm_idle",
                "motion_settled",
                "retreat_complete",
                "object_category",
                "object_detected",
                "mask_valid",
            )
            if key in observation
        }
        facts["pose_available"] = observation.get("pose") is not None
        evidence = {
            key: episode.verification_result[key]
            for key in (
                "location",
                "grasp_state",
                "target",
                "robot_location",
                "widths_mm",
                "calibration_origin",
                "sources",
            )
            if key in episode.verification_result
        }
        context = {
            "task_type": episode.task_type,
            "object_category": episode.object_category,
            "executed_skill": episode.executed_skill,
            "failure_type": episode.failure_type,
            "failure_observation": facts,
            "recovery_strategy": episode.recovery_strategy,
            "recovery_result": episode.recovery_result,
            "recovery_verified": episode.verified,
            "verification_result": evidence,
        }
        result = await wait_with_deadline(summarize(context), self.timeout_s)
        # A client returning a dict or a constructed model cannot bypass validation.
        if isinstance(result, ExperienceSummary):
            result = result.model_dump(mode="json")
        experience = ExperienceSummary.model_validate(result)
        if experience.cause_status == "UNKNOWN":
            # Unknown must stay unknown even if the model's prose invents possible
            # physical causes. The observed error remains in the source episode.
            experience = experience.model_copy(
                update={
                    "cause_hypothesis": "具体原因尚未确认；错误与恢复结果不足以确定物理根因。"
                }
            )
        return experience
