from __future__ import annotations

from typing import Any, Protocol

from planner.agent_runtime.models import SkillResult


class RobotSkill(Protocol):
    name: str

    def run(self, **kwargs: Any) -> SkillResult:
        ...


class ObservableSkill(RobotSkill, Protocol):
    def observe(self, **kwargs: Any) -> dict[str, Any]:
        ...
