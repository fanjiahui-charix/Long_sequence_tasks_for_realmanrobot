from __future__ import annotations

from .schemas import GripperCalibration, Observation, PoseReference, Verification


class DeterministicVerifier:
    """Only current sensor evidence can establish physical facts."""

    def __init__(
        self,
        calibration: GripperCalibration | None,
        *,
        base_frame: str,
        pose_ttl_s: float = 10,
        observation_ttl_s: float = 5,
    ):
        if pose_ttl_s <= 0 or observation_ttl_s <= 0:
            raise ValueError("evidence lifetimes must be positive")
        self.calibration = calibration
        self.base_frame = base_frame
        self.pose_ttl_s = pose_ttl_s
        self.observation_ttl_s = observation_ttl_s

    def fresh(self, timestamp: float, now: float, ttl: float | None = None) -> bool:
        return 0 <= now - timestamp <= (self.observation_ttl_s if ttl is None else ttl)

    def navigation(self, obs: Observation, *, target: str, now: float) -> Verification:
        ok = (
            self.fresh(obs.timestamp, now)
            and obs.localization_confirmed is True
            and obs.robot_location == target
            and obs.navigation_status in {"IDLE", "SUCCEEDED"}
            and obs.motion_settled is True
        )
        return Verification(
            verified=ok,
            error_code=None if ok else "LOCALIZATION_UNKNOWN",
            evidence={
                "location": obs.robot_location,
                "localization_confirmed": obs.localization_confirmed,
            },
        )

    def pose(
        self,
        pose: PoseReference | None,
        *,
        now: float,
        location: str | None,
        motion_epoch: int,
    ) -> Verification:
        if pose is None:
            return Verification(error_code="POSE_ESTIMATION_FAILED")
        if (
            not self.fresh(pose.captured_at, now, self.pose_ttl_s)
            or pose.motion_epoch != motion_epoch
            or pose.robot_location != location
        ):
            return Verification(error_code="POSE_STALE")
        if pose.reference_frame != self.base_frame:
            return Verification(error_code="COORDINATE_TRANSFORM_FAILED")
        return Verification(
            verified=True,
            evidence={
                "pose_id": pose.pose_id,
                "frame": pose.reference_frame,
                "captured_at": pose.captured_at,
            },
        )

    def perception(
        self,
        obs: Observation,
        *,
        now: float,
        location: str | None,
        motion_epoch: int,
        object_category: str,
    ) -> Verification:
        if obs.object_detected is not True or obs.object_category != object_category:
            return Verification(error_code="OBJECT_NOT_FOUND")
        if obs.mask_valid is not True:
            return Verification(error_code="MASK_INVALID")
        if obs.pose is not None and obs.pose.object_category != object_category:
            return Verification(error_code="POSE_ESTIMATION_FAILED")
        return self.pose(
            obs.pose, now=now, location=location, motion_epoch=motion_epoch
        )

    def grasp(self, obs: Observation, *, now: float) -> Verification:
        cal = self.calibration
        if (
            cal is None
            or not self.fresh(obs.timestamp, now)
            or obs.arm_idle is not True
            or obs.motion_settled is not True
        ):
            return Verification(error_code="GRIPPER_FEEDBACK_UNAVAILABLE")
        samples = obs.gripper_samples
        if (
            len(samples) < cal.min_samples
            or len({s.timestamp for s in samples}) < cal.min_samples
            or any(
                not s.measured or not self.fresh(s.timestamp, now, cal.max_age_s)
                for s in samples
            )
        ):
            return Verification(error_code="GRIPPER_FEEDBACK_UNAVAILABLE")
        widths = [s.width_mm for s in samples]
        evidence = {
            "widths_mm": widths,
            "calibration_id": cal.calibration_id,
            "calibration_origin": cal.origin,
            "sources": sorted({s.source for s in samples}),
        }
        if max(widths) - min(widths) > cal.max_spread_mm:
            return Verification(error_code="GRIPPER_WIDTH_UNSTABLE", evidence=evidence)
        if all(cal.empty_range_mm[0] <= w <= cal.empty_range_mm[1] for w in widths):
            return Verification(
                verified=True, grasp_state="NOT_HELD", evidence=evidence
            )
        if (
            obs.retreat_complete is True
            and all(s.after_retreat for s in samples)
            and all(cal.held_range_mm[0] <= w <= cal.held_range_mm[1] for w in widths)
        ):
            return Verification(verified=True, grasp_state="HELD", evidence=evidence)
        return Verification(error_code="GRASP_UNKNOWN", evidence=evidence)

    def final_goal(self, state, *, now: float) -> Verification:
        obs = state.last_observation
        if obs is None or state.uncertain_action is not None:
            return Verification(error_code="FINAL_GOAL_NOT_VERIFIED")
        nav = self.navigation(obs, target=state.mission.start_location, now=now)
        grasp = self.grasp(obs, now=now)
        identity = state.grasped_object == state.mission.object_category
        ok = nav.verified and grasp.grasp_state == "HELD" and identity
        return Verification(
            verified=ok,
            error_code=None if ok else "FINAL_GOAL_NOT_VERIFIED",
            grasp_state=grasp.grasp_state,
            evidence={
                "robot_at_start": nav.verified,
                "object_held": grasp.grasp_state == "HELD" and identity,
                "navigation": nav.evidence,
                "grasp": grasp.evidence,
            },
        )
