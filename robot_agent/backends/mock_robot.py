from __future__ import annotations

import time
from collections import defaultdict
from uuid import uuid4

from ..schemas import (
    GripperCalibration,
    Observation,
    PoseReference,
    SkillReply,
    WidthSample,
)


def mock_calibration():
    # Entirely synthetic. These values must never reach a real robot verifier.
    return GripperCalibration(
        calibration_id="mock-only-v1",
        object_category="glasses_case",
        origin="synthetic",
        empty_range_mm=(0, 2),
        held_range_mm=(20, 35),
        max_spread_mm=1,
        min_samples=3,
        max_age_s=5,
    )


class MockRobotBackend:
    """Deterministic in-process backend for repeatable skill and state tests."""

    def __init__(self, *, faults=None):
        self.location = "A"
        self.held = False
        self.retreat_complete = True
        self.arm_idle = True
        self.settled = True
        self.navigation_status = "IDLE"
        self.calls = []
        self.faults = {k: list(v) for k, v in (faults or {}).items()}
        self.counts = defaultdict(int)

    def _fault(self, skill):
        self.calls.append(skill)
        count = self.counts[skill]
        self.counts[skill] += 1
        sequence = self.faults.get(skill, [])
        return sequence[count] if count < len(sequence) else None

    async def observe_robot_state(self, mission):
        now = time.time()
        return Observation(
            timestamp=now,
            source="mock_actual_state",
            robot_location=self.location,
            localization_confirmed=self.location is not None,
            navigation_status=self.navigation_status,
            arm_idle=self.arm_idle,
            motion_settled=self.settled,
            retreat_complete=self.retreat_complete,
            gripper_samples=[
                WidthSample(
                    timestamp=now - i * 0.01,
                    width_mm=25 if self.held else 0,
                    measured=True,
                    source="mock_actual_encoder",
                    after_retreat=self.retreat_complete,
                )
                for i in range(3)
            ],
        )

    async def navigate_to(self, target, mission):
        fault = self._fault("navigate_to")
        if fault in {"NAV_TIMEOUT", "TOOL_EXECUTION_UNKNOWN"}:
            self.navigation_status = "FAILED"
            return SkillReply(status="TIMEOUT", error_code=fault)
        if fault in {"NAV_FAILED", "REPEATED_FAILURE"}:
            self.navigation_status = "FAILED"
            return SkillReply(status="FAILED", error_code="NAV_FAILED")
        self.location = target
        self.navigation_status = "SUCCEEDED"
        if fault == "DROP_OBJECT":
            self.held = False
        return SkillReply(
            result={
                "target": target,
                "marker": mission.location_mapping[target],
                "evaluation": "Mock/API-level Evaluation",
            }
        )

    async def locate_object(self, object_category, mission, *, motion_epoch):
        fault = self._fault("locate_object")
        if fault:
            return SkillReply(
                status="FAILED",
                error_code=fault,
                observation=Observation(
                    source="mock_rgbd",
                    object_category=object_category,
                    object_detected=False,
                ),
            )
        now = time.time()
        pose = PoseReference(
            pose_id=str(uuid4()),
            object_category=object_category,
            captured_at=now,
            reference_frame="mock_base",
            robot_location=self.location,
            motion_epoch=motion_epoch,
            matrix=[[1, 0, 0, 0.4], [0, 1, 0, 0], [0, 0, 1, 0.2], [0, 0, 0, 1]],
            confidence=0.99,
            source_ref="mock://current_rgbd",
        )
        return SkillReply(
            observation=Observation(
                timestamp=now,
                source="mock_rgbd",
                object_category=object_category,
                object_detected=True,
                mask_valid=True,
                pose=pose,
            )
        )

    async def grasp_object(self, pose, mission):
        fault = self._fault("grasp_object")
        if fault == "POSE_STALE":
            return SkillReply(status="FAILED", error_code=fault)
        self.retreat_complete = True
        if fault == "GRASP_NOT_HELD":
            self.held = False
            return SkillReply()
        if fault == "GRIPPER_FEEDBACK_UNAVAILABLE":
            return SkillReply(status="UNKNOWN", error_code=fault)
        self.held = True
        if fault == "TOOL_EXECUTION_UNKNOWN":
            return SkillReply(status="TIMEOUT", error_code=fault)
        return SkillReply(
            result={"sequence": ["home", "pregrasp", "grasp", "close", "retreat"]}
        )

    async def cancel_current_action(self):
        return None

    def ground_truth(self, mission):
        return self.location == mission.start_location and self.held
