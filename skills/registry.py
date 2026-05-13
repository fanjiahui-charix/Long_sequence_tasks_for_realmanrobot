from .human_skill import AbortSkill, AskHumanSkill
from .manipulation_skill import PickObjectSkill, PlaceObjectSkill
from .navigation_skill import AlignToTableSkill, LocateTableSkill, NavigateToSkill, PlanPathSkill
from .perception_skill import DetectObjectSkill, LookAtSkill


def build_default_skill_registry() -> dict:
    skills = [
        LocateTableSkill(),
        PlanPathSkill(),
        NavigateToSkill(),
        AlignToTableSkill(),
        LookAtSkill(),
        DetectObjectSkill(),
        PickObjectSkill(),
        PlaceObjectSkill(),
        AskHumanSkill(),
        AbortSkill(),
    ]
    return {skill.name: skill for skill in skills}

