from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SkillResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class RobotSkill(Protocol):
    name: str

    def run(self, **kwargs: Any) -> SkillResult:
        ...
