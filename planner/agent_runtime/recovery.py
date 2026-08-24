from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .contracts import RetryMode, SkillContract
from .models import FailureCode, FailureReport, MissionBudgets, VerificationResult, VerificationStatus


class RecoveryAction(str, Enum):
    RETRY = "retry"
    REOBSERVE = "reobserve"
    RUN_SKILL = "run_skill"
    REPLAN = "replan"
    ABORT = "abort"


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    skill: str | None = None
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "skill": self.skill,
            "args": dict(self.args),
        }


class BudgetTracker:
    def __init__(
        self,
        budgets: MissionBudgets,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budgets = budgets
        self.clock = clock
        self.started_at = clock()
        self.total_actions = 0
        self.replans = 0

    def can_act(self) -> bool:
        return not self.deadline_exceeded() and self.total_actions < self.budgets.max_total_actions

    def record_action(self) -> None:
        self.total_actions += 1

    def can_replan(self) -> bool:
        return not self.deadline_exceeded() and self.replans < self.budgets.max_replans

    def record_replan(self) -> None:
        self.replans += 1

    def deadline_exceeded(self) -> bool:
        return self.clock() - self.started_at >= self.budgets.mission_timeout_s


class FailureLoopDetector:
    def __init__(self, threshold: int) -> None:
        if threshold < 1:
            raise ValueError("failure repetition threshold must be positive")
        self.threshold = threshold
        self._counts: dict[tuple[str, str, str, str], int] = {}

    def record(
        self,
        skill: str,
        args: dict[str, Any],
        code: FailureCode,
        state_hash: str,
    ) -> bool:
        normalized = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = (skill, normalized, code.value, state_hash)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] >= self.threshold


class RecoveryPolicy:
    def decide(
        self,
        contract: SkillContract,
        failure: FailureReport,
        verification: VerificationResult,
        budget: BudgetTracker,
    ) -> RecoveryDecision:
        code = failure.code
        if budget.deadline_exceeded() or not budget.can_act() and not budget.can_replan():
            return RecoveryDecision(RecoveryAction.ABORT, "mission budget exhausted")
        if code in {FailureCode.SAFETY_VIOLATION, FailureCode.BUDGET_EXHAUSTED}:
            return RecoveryDecision(RecoveryAction.ABORT, f"non-retryable failure: {code.value}")
        if (
            contract.side_effecting
            and verification.status is VerificationStatus.UNKNOWN
        ):
            action = RecoveryAction.REPLAN if budget.can_replan() else RecoveryAction.ABORT
            return RecoveryDecision(action, "physical outcome is ambiguous; blind retry forbidden")
        if code in {FailureCode.POSE_STALE, FailureCode.GRASP_FAILED}:
            obj = failure.args.get("object")
            if obj and budget.can_act():
                return RecoveryDecision(
                    RecoveryAction.RUN_SKILL,
                    f"refresh perception after {code.value}",
                    skill="detect_object",
                    args={"object": obj},
                )
        if failure.attempts < contract.max_attempts and budget.can_act():
            if code in {
                FailureCode.OBJECT_NOT_FOUND,
                FailureCode.NAVIGATION_FAILED,
                FailureCode.NAVIGATION_TIMEOUT,
            }:
                return RecoveryDecision(RecoveryAction.RETRY, f"bounded retry for {code.value}")
            if contract.retry_mode is RetryMode.SAFE:
                return RecoveryDecision(RecoveryAction.RETRY, "contract permits safe retry")
            if (
                contract.retry_mode is RetryMode.VERIFY_BEFORE_RETRY
                and verification.status is VerificationStatus.FAILED
            ):
                return RecoveryDecision(RecoveryAction.RETRY, "verification proves retry is safe")
        if budget.can_replan():
            return RecoveryDecision(RecoveryAction.REPLAN, "local recovery exhausted")
        return RecoveryDecision(RecoveryAction.ABORT, "recovery and replan budgets exhausted")
