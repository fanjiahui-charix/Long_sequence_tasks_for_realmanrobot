from typing import Any

from .base import SkillResult


class LookAtSkill:
    name = "look_at"

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target")
        # Later: publish to /servo_control/move or camera head controller.
        return SkillResult(ok=True, data={"target": target, "note": "head control not connected"})


class DetectObjectSkill:
    name = "detect_object"

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        # Later: call detection node and return object id, confidence, pose.
        return SkillResult(ok=True, data={"object": obj, "found": None, "note": "detector not connected"})

