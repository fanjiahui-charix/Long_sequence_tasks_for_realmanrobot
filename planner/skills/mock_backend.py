from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from typing import Any

from planner.agent_runtime.models import FailureCode, SkillResult


IDENTITY_POSE = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


class MockRobotBackend:
    """Small stateful physical-world simulation shared by mock skills."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.location: str | None = None
        self.object_poses: dict[str, dict[str, Any]] = {}
        self.holding_object: str | None = None
        self.placed_target: str | None = None
        self._scripts: dict[str, deque[SkillResult]] = defaultdict(deque)

    def script(self, skill: str, results: Iterable[SkillResult]) -> None:
        self._scripts[skill].extend(results)

    def next_result(self, skill: str) -> SkillResult:
        if self._scripts[skill]:
            return self._scripts[skill].popleft()
        return SkillResult.succeeded()

    def navigate(self, target: str) -> SkillResult:
        result = self.next_result("navigate_to")
        if result.ok:
            self.location = target
            return SkillResult.succeeded({"backend": "mock", "command_accepted": True, "target": target})
        return result

    def observe_navigation(self, target: str) -> dict[str, Any]:
        arrived = self.location == target
        return {
            "backend": "mock",
            "target": target,
            "move_target": target if arrived else self.location,
            "move_status": "succeeded" if arrived else "failed",
            "running_status": "idle",
            "arrived": arrived,
        }

    def detect(self, obj: str) -> SkillResult:
        result = self.next_result("detect_object")
        if not result.ok:
            return result
        self.object_poses[obj] = {
            "object": obj,
            "found": True,
            "pose": IDENTITY_POSE,
            "frame_id": "mock_camera",
            "timestamp": float(self.clock()),
            "source": "mock",
            "confidence": None,
        }
        return SkillResult.succeeded({"backend": "mock", "object": obj, "observation_ready": True})

    def observe_object(self, obj: str) -> dict[str, Any]:
        if obj not in self.object_poses:
            return {"backend": "mock", "object": obj, "found": False}
        return dict(self.object_poses[obj])

    def pick(self, obj: str) -> SkillResult:
        result = self.next_result("pick_object")
        if not result.ok:
            return result
        if obj not in self.object_poses:
            return SkillResult.failed(
                FailureCode.PRECONDITION_FAILED,
                message=f"mock object is not localized: {obj}",
            )
        self.holding_object = obj
        return SkillResult.succeeded({"backend": "mock", "object": obj, "motion_completed": True})

    def observe_grasp(self, obj: str) -> dict[str, Any]:
        return {
            "backend": "mock",
            "object": obj,
            "holding_object": self.holding_object,
            "grasped": self.holding_object == obj,
        }

    def place(self, target: str) -> SkillResult:
        result = self.next_result("place_object")
        if not result.ok:
            return result
        if self.holding_object is None:
            return SkillResult.failed(
                FailureCode.PRECONDITION_FAILED,
                message="mock hand is empty",
            )
        self.holding_object = None
        self.placed_target = target
        return SkillResult.succeeded({"backend": "mock", "target": target, "motion_completed": True})

    def observe_place(self, target: str) -> dict[str, Any]:
        return {
            "backend": "mock",
            "target": target,
            "placed_target": self.placed_target,
            "holding_object": self.holding_object,
        }
