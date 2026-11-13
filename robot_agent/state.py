from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import Field

from .schemas import (
    AgentDecision,
    Contract,
    GraspState,
    MissionSpec,
    Observation,
    PoseReference,
    ToolResult,
)


class WorkingMemory(Contract):
    mission: MissionSpec
    mission_status: Literal["RUNNING", "COMPLETED", "ABORTED", "REQUEST_HELP"] = (
        "RUNNING"
    )
    current_location: str | None = None
    object_detected: bool | None = None
    pose: PoseReference | None = None
    grasp_state: GraspState = "UNKNOWN"
    grasped_object: str | None = None
    measured_gripper_width: float | None = None
    completed_actions: list[dict[str, Any]] = Field(default_factory=list)
    current_action: AgentDecision | None = None
    last_observation: Observation | None = None
    last_error: str | None = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    turn_count: int = 0
    motion_epoch: int = 0
    uncertain_action: str | None = None
    uncertain_since: float | None = None
    pending_grasp: bool = False
    updated_at: float = Field(default_factory=time.time)

    def ingest(self, obs, verifier, *, now):
        # Missing or old telemetry invalidates old claims; it never preserves HELD.
        self.last_observation = obs
        fresh = verifier.fresh(obs.timestamp, now)
        self.current_location = (
            obs.robot_location if fresh and obs.localization_confirmed is True else None
        )
        grasp = verifier.grasp(obs, now=now)
        self.grasp_state = grasp.grasp_state
        self.measured_gripper_width = (
            obs.gripper_samples[-1].width_mm
            if grasp.verified and obs.gripper_samples
            else None
        )
        if grasp.grasp_state == "NOT_HELD":
            self.grasped_object = None
        if (
            self.pose is not None
            and not verifier.pose(
                self.pose,
                now=now,
                location=self.current_location,
                motion_epoch=self.motion_epoch,
            ).verified
        ):
            self.pose = None
        self.updated_at = now

    def begin(self, decision):
        self.current_action = decision
        self.turn_count += 1

    def invalidate_for_motion(self, tool):
        self.motion_epoch += 1
        self.pose = None
        if tool == "navigate_to":
            self.current_location = None
        if tool == "grasp_object":
            self.grasp_state = "UNKNOWN"
            self.grasped_object = None
            self.pending_grasp = True

    def apply(self, result: ToolResult, verifier, *, now):
        self.ingest(result.observation, verifier, now=now)
        if result.execution_uncertain:
            self.uncertain_action = result.tool_name
            self.uncertain_since = result.finished_at
        if result.tool_name == "locate_object":
            self.object_detected = result.observation.object_detected
            self.pose = (
                result.observation.pose if result.verification.verified else None
            )
        if result.tool_name == "grasp_object" and result.verification.verified:
            self.grasped_object = self.mission.object_category
            self.pending_grasp = False
        # A timed-out physical action requires a subsequent explicit read-only turn.
        if result.tool_name == "observe_robot_state" and self.uncertain_action:
            obs = result.observation
            if (
                self.uncertain_since is not None
                and obs.timestamp >= self.uncertain_since
                and verifier.fresh(obs.timestamp, now)
                and obs.motion_settled is True
                and obs.arm_idle is True
                and obs.navigation_status in {"IDLE", "SUCCEEDED", "FAILED"}
            ):
                if (
                    self.pending_grasp
                    and self.grasp_state == "HELD"
                    and obs.retreat_complete is True
                ):
                    self.grasped_object = self.mission.object_category
                    self.pending_grasp = False
                self.uncertain_action = None
                self.uncertain_since = None
        if result.status == "SUCCEEDED" and result.verification.verified:
            self.completed_actions.append(
                {
                    "tool": result.tool_name,
                    "arguments": result.arguments,
                    "timestamp": result.finished_at,
                }
            )
            self.completed_actions = self.completed_actions[-24:]
            if result.tool_name != "observe_robot_state":
                self.last_error = None
        else:
            self.last_error = result.error_code or "TOOL_EXECUTION_UNKNOWN"
            key = result.tool_name + ":" + self.last_error
            self.retry_counts[key] = self.retry_counts.get(key, 0) + 1
        self.current_action = None

    def context(self):
        value = self.model_dump(mode="json", exclude={"last_observation"})
        value["latest_observation"] = (
            self.last_observation.model_dump(mode="json")
            if self.last_observation
            else None
        )
        return value
