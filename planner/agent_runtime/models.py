from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FailureCode(str, Enum):
    UNAVAILABLE = "unavailable"
    INVALID_ARGUMENT = "invalid_argument"
    PRECONDITION_FAILED = "precondition_failed"
    NAVIGATION_FAILED = "navigation_failed"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    PERCEPTION_UNAVAILABLE = "perception_unavailable"
    OBJECT_NOT_FOUND = "object_not_found"
    POSE_INVALID = "pose_invalid"
    POSE_STALE = "pose_stale"
    GRASP_FAILED = "grasp_failed"
    GRASP_AMBIGUOUS = "grasp_ambiguous"
    PLACE_FAILED = "place_failed"
    PROTOCOL_ERROR = "protocol_error"
    SAFETY_VIOLATION = "safety_violation"
    VERIFICATION_FAILED = "verification_failed"
    GOAL_NOT_SATISFIED = "goal_not_satisfied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REPLAN_FAILED = "replan_failed"
    INTERNAL_ERROR = "internal_error"


class RuntimePhase(str, Enum):
    PRECHECK = "precheck"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMMIT = "commit"
    RECOVER = "recover"
    REPLAN = "replan"
    DONE = "done"
    ABORT = "abort"


class MissionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    ABORTED = "aborted"
    CANCELLED = "cancelled"


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, set):
        return [jsonable(item) for item in sorted(value, key=str)]
    return value


@dataclass(frozen=True)
class PlanStep:
    id: str
    skill: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlanStep:
        if not isinstance(payload, dict):
            raise ValueError("plan step must be an object")
        step_id = payload.get("id")
        skill = payload.get("skill")
        args = payload.get("args", {})
        depends_on = payload.get("depends_on", [])
        if not isinstance(step_id, str) or not step_id:
            raise ValueError("step.id must be a non-empty string")
        if not isinstance(skill, str) or not skill:
            raise ValueError("step.skill must be a non-empty string")
        if not isinstance(args, dict):
            raise ValueError("step.args must be an object")
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise ValueError("step.depends_on must be a list of strings")
        return cls(id=step_id, skill=skill, args=dict(args), depends_on=tuple(depends_on))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "skill": self.skill, "args": jsonable(self.args)}
        if self.depends_on:
            payload["depends_on"] = list(self.depends_on)
        return payload


@dataclass(frozen=True)
class MissionPlan:
    goal: dict[str, Any]
    steps: tuple[PlanStep, ...]
    plan_id: str = "plan"
    version: int = 1
    parent_version: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MissionPlan:
        if not isinstance(payload, dict):
            raise ValueError("plan must be a JSON object")
        raw_goal = payload.get("goal", {})
        if isinstance(raw_goal, str):
            goal = {"type": "text", "description": raw_goal}
        elif isinstance(raw_goal, dict):
            goal = dict(raw_goal)
        else:
            raise ValueError("plan.goal must be an object or string")
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("plan.steps must be a non-empty list")
        try:
            version = int(payload.get("version", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("plan.version must be an integer") from exc
        parent_version = payload.get("parent_version")
        if parent_version is not None:
            try:
                parent_version = int(parent_version)
            except (TypeError, ValueError) as exc:
                raise ValueError("plan.parent_version must be an integer or null") from exc
        return cls(
            plan_id=str(payload.get("plan_id") or "plan"),
            version=version,
            parent_version=parent_version,
            goal=goal,
            steps=tuple(PlanStep.from_dict(step) for step in raw_steps),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "version": self.version,
            "parent_version": self.parent_version,
            "goal": jsonable(self.goal),
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class SkillResult:
    status: ExecStatus
    data: dict[str, Any] = field(default_factory=dict)
    failure_code: FailureCode | None = None
    retryable: bool = False
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is ExecStatus.SUCCEEDED

    @classmethod
    def succeeded(cls, data: dict[str, Any] | None = None, message: str | None = None) -> SkillResult:
        return cls(status=ExecStatus.SUCCEEDED, data=dict(data or {}), message=message)

    @classmethod
    def failed(
        cls,
        code: FailureCode,
        *,
        message: str | None = None,
        data: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> SkillResult:
        return cls(
            status=ExecStatus.FAILED,
            data=dict(data or {}),
            failure_code=code,
            retryable=retryable,
            message=message,
        )

    @classmethod
    def unknown(
        cls,
        code: FailureCode,
        *,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> SkillResult:
        return cls(
            status=ExecStatus.UNKNOWN,
            data=dict(data or {}),
            failure_code=code,
            message=message,
        )

    @classmethod
    def rejected(
        cls,
        code: FailureCode,
        *,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> SkillResult:
        return cls(
            status=ExecStatus.REJECTED,
            data=dict(data or {}),
            failure_code=code,
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": jsonable(self.data),
            "failure_code": self.failure_code.value if self.failure_code else None,
            "retryable": self.retryable,
            "message": self.message,
        }


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    confidence: float | None = None
    failure_code: FailureCode | None = None
    observations: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is VerificationStatus.VERIFIED

    @classmethod
    def verified(
        cls,
        observations: dict[str, Any] | None = None,
        *,
        confidence: float | None = None,
        message: str | None = None,
    ) -> VerificationResult:
        return cls(
            status=VerificationStatus.VERIFIED,
            confidence=confidence,
            observations=dict(observations or {}),
            message=message,
        )

    @classmethod
    def failed(
        cls,
        code: FailureCode,
        *,
        observations: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> VerificationResult:
        return cls(
            status=VerificationStatus.FAILED,
            failure_code=code,
            observations=dict(observations or {}),
            message=message,
        )

    @classmethod
    def unknown(
        cls,
        code: FailureCode,
        *,
        observations: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> VerificationResult:
        return cls(
            status=VerificationStatus.UNKNOWN,
            failure_code=code,
            observations=dict(observations or {}),
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "failure_code": self.failure_code.value if self.failure_code else None,
            "observations": jsonable(self.observations),
            "message": self.message,
        }


@dataclass(frozen=True)
class FailureReport:
    code: FailureCode
    step_id: str | None = None
    skill: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "step_id": self.step_id,
            "skill": self.skill,
            "args": jsonable(self.args),
            "attempts": self.attempts,
            "message": self.message,
        }


@dataclass(frozen=True)
class MissionBudgets:
    mission_timeout_s: float = 900.0
    max_total_actions: int = 50
    max_replans: int = 3
    repeated_failure_threshold: int = 3


@dataclass(frozen=True)
class MissionResult:
    status: MissionStatus
    mission_id: str
    plan_id: str
    plan_version: int
    state: dict[str, Any]
    total_actions: int
    replans: int
    failure: FailureReport | None = None
    trajectory_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is MissionStatus.SUCCEEDED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "mission_id": self.mission_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "state": jsonable(self.state),
            "total_actions": self.total_actions,
            "replans": self.replans,
            "failure": self.failure.to_dict() if self.failure else None,
            "trajectory_path": self.trajectory_path,
        }
