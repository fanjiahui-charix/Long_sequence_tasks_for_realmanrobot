from __future__ import annotations

from typing import Protocol
from ..schemas import MissionSpec, Observation, PoseReference, SkillReply


class RobotBackend(Protocol):
    """Implement these high-level operations to integrate another robot.

    An acknowledgement is not completion. Observe must return measured,
    timestamped state; unsupported fields remain None/UNKNOWN. A cancelled
    coroutine/process does not prove a physical action has stopped.
    """

    async def navigate_to(self, target: str, mission: MissionSpec) -> SkillReply: ...
    async def locate_object(
        self, object_category: str, mission: MissionSpec, *, motion_epoch: int
    ) -> SkillReply: ...
    async def grasp_object(
        self, pose: PoseReference, mission: MissionSpec
    ) -> SkillReply: ...
    async def observe_robot_state(self, mission: MissionSpec) -> Observation: ...
    async def cancel_current_action(self) -> None: ...
