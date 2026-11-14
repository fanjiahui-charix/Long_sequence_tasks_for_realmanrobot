from __future__ import annotations

import math
import time
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

ToolName = Literal[
    "navigate_to", "locate_object", "grasp_object", "observe_robot_state"
]
GraspState = Literal["HELD", "NOT_HELD", "UNKNOWN"]
Status = Literal["SUCCEEDED", "FAILED", "TIMEOUT", "UNKNOWN"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, allow_inf_nan=False
    )


class MissionSpec(Contract):
    mission_id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: Literal["mobile_pick_and_return"] = "mobile_pick_and_return"
    instruction: str = Field(min_length=1, max_length=4000)
    goal: str = "retrieve_black_glasses_case"
    start_location: str
    source_location: str
    target_object: str
    object_category: str = "glasses_case"
    success_conditions: tuple[str, str] = ("robot_at_start", "object_held")
    scene_entities: list[str] = Field(default_factory=list)
    location_mapping: dict[str, str]
    scene_image_sha256: str | None = None

    @model_validator(mode="after")
    def valid_mission(self):
        if self.success_conditions != ("robot_at_start", "object_held"):
            raise ValueError("V1 always requires returned-to-start AND holding target")
        if self.start_location == self.source_location:
            raise ValueError("start and source must differ")
        markers = [
            self.location_mapping.get(k)
            for k in (self.start_location, self.source_location)
        ]
        if (
            not all(isinstance(v, str) and v.strip() for v in markers)
            or markers[0] == markers[1]
        ):
            raise ValueError(
                "supply distinct trusted navigation mappings for start and source"
            )
        return self


class AgentDecision(Contract):
    action_type: Literal["CALL_TOOL", "FINISH", "ABORT", "REQUEST_HELP"]
    tool_name: ToolName | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    decision_summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def single_action(self):
        if self.action_type == "CALL_TOOL":
            if self.tool_name is None:
                raise ValueError("CALL_TOOL requires exactly one tool")
        elif self.tool_name is not None or self.arguments:
            raise ValueError("terminal decisions cannot contain tools or arguments")
        return self


class PoseReference(Contract):
    pose_id: str
    object_category: str
    captured_at: float
    reference_frame: str
    robot_location: str
    motion_epoch: int = Field(ge=0)
    matrix: list[list[float]]
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_ref: str | None = None

    @model_validator(mode="after")
    def rigid_transform(self):
        m = self.matrix
        if (
            len(m) != 4
            or any(len(r) != 4 for r in m)
            or any(not math.isfinite(x) for r in m for x in r)
        ):
            raise ValueError("pose must be finite 4x4")
        if any(abs(a - b) > 1e-4 for a, b in zip(m[3], [0, 0, 0, 1])):
            raise ValueError("invalid homogeneous row")
        for i in range(3):
            for j in range(3):
                if abs(sum(m[k][i] * m[k][j] for k in range(3)) - int(i == j)) > 1e-3:
                    raise ValueError("rotation must be orthonormal")
        det = (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )
        if abs(det - 1) > 1e-3:
            raise ValueError("rotation must have positive unit determinant")
        return self


class WidthSample(Contract):
    timestamp: float
    width_mm: float = Field(ge=0)
    measured: StrictBool = False
    source: str = Field(min_length=1)
    after_retreat: StrictBool = False


class GripperCalibration(Contract):
    calibration_id: str = Field(min_length=1)
    object_category: str
    origin: Literal["synthetic", "measured"]
    empty_range_mm: tuple[float, float]
    held_range_mm: tuple[float, float]
    max_spread_mm: float = Field(ge=0)
    min_samples: int = Field(ge=2)
    max_age_s: float = Field(gt=0)

    @model_validator(mode="after")
    def distinct_ranges(self):
        e, h = self.empty_range_mm, self.held_range_mm
        if not (0 <= e[0] <= e[1] and 0 <= h[0] <= h[1]):
            raise ValueError("width ranges must be ordered and nonnegative")
        if not (e[1] < h[0] or h[1] < e[0]):
            raise ValueError("empty and held intervals cannot overlap")
        return self


class Observation(Contract):
    timestamp: float = Field(default_factory=time.time)
    source: str
    robot_location: str | None = None
    localization_confirmed: StrictBool | None = None
    navigation_status: Literal["IDLE", "MOVING", "SUCCEEDED", "FAILED", "UNKNOWN"] = (
        "UNKNOWN"
    )
    arm_idle: StrictBool | None = None
    motion_settled: StrictBool | None = None
    gripper_samples: list[WidthSample] = Field(default_factory=list)
    retreat_complete: StrictBool | None = None
    object_category: str | None = None
    object_detected: StrictBool | None = None
    mask_valid: StrictBool | None = None
    pose: PoseReference | None = None
    raw_result_reference: str | None = None
    notes: list[str] = Field(default_factory=list)


class Verification(Contract):
    verified: bool = False
    error_code: str | None = None
    grasp_state: GraspState = "UNKNOWN"
    evidence: dict[str, Any] = Field(default_factory=dict)


class SkillReply(Contract):
    status: Status = "SUCCEEDED"
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    observation: Observation | None = None


class ToolResult(Contract):
    tool_name: ToolName
    status: Status
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    started_at: float
    finished_at: float
    duration_sec: float = Field(ge=0)
    observation: Observation
    verification: Verification = Field(default_factory=Verification)
    dispatched: bool = False
    execution_uncertain: bool = False
    carry_required: bool = False


class ExperienceSummary(Contract):
    """A model's bounded analysis, never a verified physical root cause."""

    trigger: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
    ]
    cause_hypothesis: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    cause_status: Literal["UNKNOWN", "HYPOTHESIS"] = "UNKNOWN"
    lesson: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
    ]
    precautions: list[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)
        ]
    ] = Field(min_length=1, max_length=5)


class Episode(Contract):
    episode_id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    task_type: str = "mobile_pick_and_return"
    object_category: str
    executed_skill: ToolName
    failure_type: str | None = None
    failure_observation: dict[str, Any] = Field(default_factory=dict)
    recovery_strategy: list[ToolName] = Field(default_factory=list)
    recovery_result: Literal["UNVERIFIED", "VERIFIED_SUCCESS", "FAILED"] = "UNVERIFIED"
    verification_result: dict[str, Any] = Field(default_factory=dict)
    verified: bool = False
    experience: ExperienceSummary | None = None
    experience_status: Literal["PENDING", "READY", "FAILED"] = "PENDING"
    experience_provider: str | None = None
    experience_error: str | None = None
    created_at: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def verified_recovery(self):
        if self.verified != (self.recovery_result == "VERIFIED_SUCCESS"):
            raise ValueError("verified flag must match verified recovery result")
        if self.verified and (
            not self.recovery_strategy or not self.verification_result
        ):
            raise ValueError(
                "verified recovery needs strategy and verification evidence"
            )
        return self

    @model_validator(mode="after")
    def valid_experience(self):
        if (self.experience_status == "READY") != (self.experience is not None):
            raise ValueError("only READY experience may contain a summary")
        return self
