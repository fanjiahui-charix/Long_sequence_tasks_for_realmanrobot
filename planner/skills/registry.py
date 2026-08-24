from .human_skill import AbortSkill, AskHumanSkill
from .manipulation_skill import PickObjectSkill, PlaceObjectSkill
from .mock_backend import MockRobotBackend
from .navigation_skill import AlignToTableSkill, LocateTableSkill, NavigateToSkill, PlanPathSkill
from .perception_skill import DetectObjectSkill, LookAtSkill


def build_default_skill_registry(mock_backend: MockRobotBackend | None = None) -> dict:
    backend = mock_backend or MockRobotBackend()
    skills = [
        LocateTableSkill(),
        PlanPathSkill(),
        NavigateToSkill(mock_backend=backend),
        AlignToTableSkill(),
        LookAtSkill(),
        DetectObjectSkill(mock_backend=backend),
        PickObjectSkill(mock_backend=backend),
        PlaceObjectSkill(mock_backend=backend),
        AskHumanSkill(),
        AbortSkill(),
    ]
    return {skill.name: skill for skill in skills}

