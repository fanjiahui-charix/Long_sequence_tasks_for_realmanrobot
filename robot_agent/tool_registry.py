from __future__ import annotations

import time
from pydantic import ConfigDict, ValidationError

from .backends.base import RobotBackend
from .schemas import Contract


class NavigateArgs(Contract):
    model_config = ConfigDict(extra="forbid", strict=True)
    target: str


class ObjectArgs(Contract):
    model_config = ConfigDict(extra="forbid", strict=True)
    object_category: str


class GraspArgs(ObjectArgs):
    pose_reference: str


class ObserveArgs(Contract):
    pass


class ToolRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ToolRegistry:
    ARGUMENTS = {
        "navigate_to": NavigateArgs,
        "locate_object": ObjectArgs,
        "grasp_object": GraspArgs,
        "observe_robot_state": ObserveArgs,
    }
    DESCRIPTIONS = {
        "navigate_to": "Navigate to a trusted mission location label, then verify arrival. No coordinates or speed parameters.",
        "locate_object": "Acquire fresh RGB-D, segment target, estimate 6D pose and transform to arm base. Returns a trusted pose reference.",
        "grasp_object": "Execute pregrasp/grasp/close/retreat with the current pose reference; verify actual measured opening.",
        "observe_robot_state": "Read current navigation, arm and measured gripper state. Required after ambiguous physical execution.",
    }

    def __init__(self, backend: RobotBackend, verifier, *, timeouts=None):
        self.backend = backend
        self.verifier = verifier
        self.timeouts = {
            "navigate_to": 180.0,
            "locate_object": 180.0,
            "grasp_object": 120.0,
            "observe_robot_state": 10.0,
        }
        self.timeouts.update(timeouts or {})
        if any(t <= 0 for t in self.timeouts.values()):
            raise ValueError("tool timeouts must be positive")

    def describe(self):
        return [
            {
                "name": name,
                "description": self.DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            }
            for name, model in self.ARGUMENTS.items()
        ]

    def validate(self, decision, state, *, now=None):
        now = time.time() if now is None else now
        try:
            args = self.ARGUMENTS[decision.tool_name].model_validate(decision.arguments)
        except (KeyError, ValidationError):
            raise ToolRejected("INVALID_ARGUMENT") from None
        name = decision.tool_name
        if name == "observe_robot_state":
            return args
        if state.uncertain_action:
            raise ToolRejected("ACTION_UNRESOLVED")
        obs = state.last_observation
        if (
            obs is None
            or not self.verifier.fresh(obs.timestamp, now)
            or obs.arm_idle is not True
            or obs.motion_settled is not True
            or obs.navigation_status == "MOVING"
        ):
            raise ToolRejected("PRECONDITION_FAILED")
        if name == "navigate_to":
            if args.target not in {
                state.mission.start_location,
                state.mission.source_location,
            }:
                raise ToolRejected("INVALID_ARGUMENT")
        else:
            if args.object_category != state.mission.object_category:
                raise ToolRejected("INVALID_ARGUMENT")
            if state.current_location != state.mission.source_location:
                raise ToolRejected("PRECONDITION_FAILED")
            if name == "grasp_object":
                cal = self.verifier.calibration
                if cal is None or cal.object_category != args.object_category:
                    raise ToolRejected("GRIPPER_CALIBRATION_REQUIRED")
                if state.grasp_state != "NOT_HELD":
                    raise ToolRejected("GRASP_STATE_UNSAFE")
                if state.pose is None or args.pose_reference != state.pose.pose_id:
                    raise ToolRejected("POSE_STALE")
                verification = self.verifier.pose(
                    state.pose,
                    now=now,
                    location=state.current_location,
                    motion_epoch=state.motion_epoch,
                )
                if not verification.verified:
                    raise ToolRejected(verification.error_code)
        return args

    async def invoke(self, name, args, state, *, pose=None):
        if name == "navigate_to":
            return await self.backend.navigate_to(args.target, state.mission)
        if name == "locate_object":
            return await self.backend.locate_object(
                args.object_category, state.mission, motion_epoch=state.motion_epoch
            )
        if name == "grasp_object":
            return await self.backend.grasp_object(pose, state.mission)
        return None
