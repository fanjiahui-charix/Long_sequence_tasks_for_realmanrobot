from typing import Any

from .base import SkillResult


class PickObjectSkill:
    name = "pick_object"

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        return SkillResult(ok=True, data={"object": obj, "note": "grasping not connected"})


class PlaceObjectSkill:
    name = "place_object"

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target") or kwargs.get("table")
        return SkillResult(ok=True, data={"target": target, "note": "placing not connected"})

