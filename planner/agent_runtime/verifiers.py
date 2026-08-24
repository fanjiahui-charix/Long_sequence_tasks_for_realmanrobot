from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import (
    ExecStatus,
    FailureCode,
    PlanStep,
    SkillResult,
    VerificationResult,
)
from .state import ObjectPoseState, ObjectState, WorldState


SUCCESS_STATES = {"idle", "success", "succeeded", "done", "completed", "arrived", "finished"}
FAILURE_STATES = {"failed", "error", "aborted", "canceled", "cancelled"}


class SkillVerifier(Protocol):
    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        raise NotImplementedError


class ObservationProvider(Protocol):
    def observe(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        state: WorldState,
    ) -> dict[str, Any]:
        raise NotImplementedError


class SkillObservationProvider:
    def __init__(self, skill_registry: dict[str, Any]) -> None:
        self.skill_registry = skill_registry

    def observe(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        state: WorldState,
    ) -> dict[str, Any]:
        del execution, state
        skill = self.skill_registry.get(step.skill)
        observe = getattr(skill, "observe", None)
        if not callable(observe):
            return {}
        try:
            value = observe(**step.args)
        except Exception as exc:
            return {"observation_error": f"{type(exc).__name__}: {exc}"}
        return value if isinstance(value, dict) else {"observation_error": "non-object observation"}


class NavigationVerifier:
    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        del state, now
        target = step.args.get("target") or step.args.get("marker") or step.args.get("table")
        observed_target = observation.get("move_target") or observation.get("target")
        move_status = str(observation.get("move_status", "")).lower()
        running_status = str(observation.get("running_status", "")).lower()
        arrived = observation.get("arrived") is True
        target_matches = target is None or str(observed_target).lower() == str(target).lower()

        if any(value in FAILURE_STATES for value in (move_status, running_status)):
            return VerificationResult.failed(
                FailureCode.NAVIGATION_FAILED,
                observations=observation,
                message=f"navigation reported failure for {target}",
            )
        if target_matches and (
            arrived
            or (move_status in SUCCESS_STATES and (not running_status or running_status in SUCCESS_STATES))
        ):
            return VerificationResult.verified(
                {
                    **observation,
                    "state_updates": {
                        "current_location": str(target) if target is not None else None,
                        "robot_pose": observation.get("current_pose"),
                    },
                }
            )
        if move_status or running_status or execution.ok:
            return VerificationResult.failed(
                FailureCode.NAVIGATION_FAILED,
                observations=observation,
                message="navigation command accepted but arrival is not verified",
            )
        return VerificationResult.unknown(
            FailureCode.PROTOCOL_ERROR,
            observations=observation,
            message="navigation status is unavailable",
        )


@dataclass(frozen=True)
class PerceptionVerifier:
    pose_ttl_s: float = 2.0

    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        del state
        obj = str(step.args.get("object", ""))
        if observation.get("found") is False or execution.failure_code is FailureCode.OBJECT_NOT_FOUND:
            return VerificationResult.failed(
                FailureCode.OBJECT_NOT_FOUND,
                observations=observation,
                message=f"object not found: {obj}",
            )
        pose = observation.get("pose", observation.get("object_pose"))
        frame_id = observation.get("frame_id", observation.get("camera_frame"))
        timestamp = observation.get("timestamp")
        if not _valid_pose_matrix(pose) or not frame_id:
            return VerificationResult.failed(
                FailureCode.POSE_INVALID,
                observations=observation,
                message=f"object pose is invalid: {obj}",
            )
        if not isinstance(timestamp, (int, float)):
            return VerificationResult.unknown(
                FailureCode.POSE_INVALID,
                observations=observation,
                message=f"object pose has no timestamp: {obj}",
            )
        if now - float(timestamp) < 0 or now - float(timestamp) > self.pose_ttl_s:
            return VerificationResult.failed(
                FailureCode.POSE_STALE,
                observations=observation,
                message=f"object pose is stale: {obj}",
            )
        pose_state = ObjectPoseState(
            pose=pose,
            frame_id=str(frame_id),
            timestamp=float(timestamp),
            source=observation.get("source"),
            confidence=observation.get("confidence"),
            valid=True,
        )
        object_state = ObjectState(name=obj, visible=True, pose=pose_state, grasped=False)
        return VerificationResult.verified(
            {
                **observation,
                "state_updates": {"objects": {obj: object_state}},
            },
            confidence=observation.get("confidence"),
        )


class GraspVerifier:
    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        del state, now
        obj = str(step.args.get("object", ""))
        held = observation.get("holding_object")
        grasped = observation.get("grasped")
        if held == obj or grasped is True:
            return VerificationResult.verified(
                {
                    **observation,
                    "state_updates": {
                        "holding_object": obj,
                        "objects": {obj: ObjectState(name=obj, visible=None, grasped=True)},
                    },
                }
            )
        if held is not None and held != obj:
            return VerificationResult.failed(
                FailureCode.GRASP_FAILED,
                observations=observation,
                message=f"holding {held}, expected {obj}",
            )
        if grasped is False or execution.failure_code is FailureCode.GRASP_FAILED:
            return VerificationResult.failed(
                FailureCode.GRASP_FAILED,
                observations=observation,
                message=f"grasp not established: {obj}",
            )
        return VerificationResult.unknown(
            FailureCode.GRASP_AMBIGUOUS,
            observations=observation,
            message=f"insufficient evidence that {obj} is held",
        )


class PlaceVerifier:
    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        del state, now
        target = step.args.get("target") or step.args.get("table")
        placed_target = observation.get("placed_target")
        if observation.get("holding_object") is None and placed_target == target:
            return VerificationResult.verified(
                {**observation, "state_updates": {"holding_object": None}}
            )
        if execution.status is ExecStatus.FAILED:
            return VerificationResult.failed(
                FailureCode.PLACE_FAILED,
                observations=observation,
                message=f"placement failed: {target}",
            )
        return VerificationResult.unknown(
            FailureCode.PLACE_FAILED,
            observations=observation,
            message=f"placement is not verified: {target}",
        )


class ControlVerifier:
    def verify(
        self,
        *,
        step: PlanStep,
        execution: SkillResult,
        observation: dict[str, Any],
        state: WorldState,
        now: float,
    ) -> VerificationResult:
        del step, state, now
        if execution.ok:
            return VerificationResult.verified(observation)
        code = execution.failure_code or FailureCode.VERIFICATION_FAILED
        if execution.status is ExecStatus.UNKNOWN:
            return VerificationResult.unknown(code, observations=observation, message=execution.message)
        return VerificationResult.failed(code, observations=observation, message=execution.message)


class GoalVerifier:
    def verify(
        self,
        goal: dict[str, Any],
        state: WorldState,
        observation: dict[str, Any],
    ) -> VerificationResult:
        goal_type = goal.get("type")
        if goal_type == "holding_object":
            expected = goal.get("object")
            observed = observation.get("holding_object", state.holding_object)
            if observed == expected:
                return VerificationResult.verified(observation)
        elif goal_type in {"at", "at_location"}:
            expected = goal.get("location") or goal.get("target")
            observed = observation.get("current_location", state.current_location)
            if observed == expected:
                return VerificationResult.verified(observation)
        elif goal_type in {"placed_object", "object_placed"}:
            target = goal.get("target")
            if observation.get("placed_target") == target:
                return VerificationResult.verified(observation)
        return VerificationResult.failed(
            FailureCode.GOAL_NOT_SATISFIED,
            observations=observation,
            message=f"goal is not verified: {goal}",
        )


class VerifierRegistry:
    def __init__(self, verifiers: dict[str, SkillVerifier] | None = None) -> None:
        self._verifiers: dict[str, SkillVerifier] = verifiers or {
            "navigation": NavigationVerifier(),
            "perception": PerceptionVerifier(),
            "grasp": GraspVerifier(),
            "place": PlaceVerifier(),
            "control": ControlVerifier(),
        }

    def get(self, name: str) -> SkillVerifier:
        try:
            return self._verifiers[name]
        except KeyError as exc:
            raise KeyError(f"verifier not registered: {name}") from exc


def _valid_pose_matrix(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    if not all(isinstance(row, list) and len(row) == 4 for row in value):
        return False
    try:
        numeric = [[float(item) for item in row] for row in value]
    except (TypeError, ValueError):
        return False
    return all(abs(numeric[3][index] - expected) <= 1e-4 for index, expected in enumerate((0, 0, 0, 1)))
