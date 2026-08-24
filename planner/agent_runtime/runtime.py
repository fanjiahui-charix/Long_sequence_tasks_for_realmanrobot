from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .contracts import SkillContract
from .executor import SkillExecutor
from .models import (
    ExecStatus,
    FailureCode,
    FailureReport,
    MissionBudgets,
    MissionPlan,
    MissionResult,
    MissionStatus,
    PlanStep,
    RuntimePhase,
    SkillResult,
    VerificationResult,
    VerificationStatus,
)
from .recovery import (
    BudgetTracker,
    FailureLoopDetector,
    RecoveryAction,
    RecoveryDecision,
    RecoveryPolicy,
)
from .replanner import ReplanError, Replanner
from .semantic_validator import SemanticPlanValidator
from .state import WorldState
from .trace import NullTraceWriter
from .verifiers import GoalVerifier, ObservationProvider, VerifierRegistry


class AgentRuntime:
    def __init__(
        self,
        *,
        mission_id: str,
        plan: MissionPlan,
        state: WorldState,
        contracts: dict[str, SkillContract],
        skill_registry: dict[str, Any],
        executor: SkillExecutor,
        observation_provider: ObservationProvider,
        verifiers: VerifierRegistry,
        goal_verifier: GoalVerifier,
        recovery_policy: RecoveryPolicy,
        replanner: Replanner,
        budgets: MissionBudgets,
        goal_observer: Callable[[dict[str, Any], WorldState], dict[str, Any]],
        trace: Any | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.mission_id = mission_id
        self.plan = plan
        self.original_goal = dict(plan.goal)
        self.state = state
        self.contracts = contracts
        self.skill_registry = skill_registry
        self.executor = executor
        self.observation_provider = observation_provider
        self.verifiers = verifiers
        self.goal_verifier = goal_verifier
        self.recovery_policy = recovery_policy
        self.replanner = replanner
        self.budgets = budgets
        self.goal_observer = goal_observer
        self.trace = trace or NullTraceWriter()
        self.monotonic_clock = monotonic_clock
        self.wall_clock = wall_clock
        self.budget = BudgetTracker(budgets, clock=monotonic_clock)
        self.loop_detector = FailureLoopDetector(budgets.repeated_failure_threshold)
        self.phase = RuntimePhase.PRECHECK
        self._committed_steps: list[PlanStep] = []
        self._recovery_counter = 0
        self._closed = False

    def run(self) -> MissionResult:
        self.trace.record(
            "mission_started",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            goal=self.original_goal,
            state=self.state,
        )
        validation_errors = SemanticPlanValidator(self.contracts).validate(
            self.plan, set(self.state.facts)
        )
        if validation_errors:
            return self._abort(
                FailureReport(
                    code=FailureCode.REPLAN_FAILED,
                    message="; ".join(validation_errors),
                )
            )

        while True:
            replanned = False
            for index, step in enumerate(self.plan.steps):
                outcome = self._run_step(step, self.plan.steps[index:])
                if isinstance(outcome, MissionResult):
                    return outcome
                if outcome == "replanned":
                    replanned = True
                    break
            if replanned:
                continue
            return self._finish_goal()

    def _run_step(
        self,
        step: PlanStep,
        remaining_steps: Sequence[PlanStep],
    ) -> str | MissionResult:
        contract = self.contracts[step.skill]
        attempts = 0
        while True:
            precheck = self._precheck(step, contract)
            if precheck is not None:
                failure = precheck
                verification = VerificationResult.failed(
                    failure.code,
                    message=failure.message,
                )
            else:
                if not self.budget.can_act():
                    return self._abort(
                        FailureReport(
                            code=FailureCode.BUDGET_EXHAUSTED,
                            step_id=step.id,
                            skill=step.skill,
                            args=step.args,
                            attempts=attempts,
                            message="mission action or deadline budget exhausted",
                        )
                    )
                attempts += 1
                execution, verification = self._execute_and_verify(
                    step, contract, attempts
                )
                if verification.status is VerificationStatus.VERIFIED:
                    self._commit(step, contract, verification)
                    return "committed"
                failure = self._failure_from(
                    step,
                    attempts,
                    execution,
                    verification,
                )

            self.state.last_failure = failure.code
            repeated = self.loop_detector.record(
                step.skill,
                step.args,
                failure.code,
                self.state.stable_hash(),
            )
            if repeated:
                return self._abort(
                    FailureReport(
                        code=FailureCode.BUDGET_EXHAUSTED,
                        step_id=step.id,
                        skill=step.skill,
                        args=step.args,
                        attempts=attempts,
                        message="identical failure repeated without a verified state change",
                    )
                )

            decision = self.recovery_policy.decide(
                contract,
                failure,
                verification,
                self.budget,
            )
            self._record_recovery(step, attempts, failure, decision)
            if decision.action is RecoveryAction.RETRY:
                continue
            if decision.action is RecoveryAction.REOBSERVE:
                reverified = self._reobserve(step, contract, attempts)
                if reverified.status is VerificationStatus.VERIFIED:
                    self._commit(step, contract, reverified)
                    return "committed"
                continue
            if decision.action is RecoveryAction.RUN_SKILL:
                if self._run_recovery_skill(step, decision):
                    continue
                if self.budget.can_replan() and self._replan(failure, remaining_steps):
                    return "replanned"
                return self._abort(failure)
            if decision.action is RecoveryAction.REPLAN:
                if self._replan(failure, remaining_steps):
                    return "replanned"
                return self._abort(
                    FailureReport(
                        code=FailureCode.REPLAN_FAILED,
                        step_id=step.id,
                        skill=step.skill,
                        args=step.args,
                        attempts=attempts,
                        message="remaining-plan repair was unavailable or invalid",
                    )
                )
            return self._abort(failure)

    def _precheck(
        self,
        step: PlanStep,
        contract: SkillContract,
    ) -> FailureReport | None:
        self._set_phase(RuntimePhase.PRECHECK, step=step)
        missing_dependencies = set(step.depends_on) - set(self.state.completed_steps)
        if missing_dependencies:
            return FailureReport(
                code=FailureCode.PRECONDITION_FAILED,
                step_id=step.id,
                skill=step.skill,
                args=step.args,
                message=f"uncommitted dependencies: {sorted(missing_dependencies)}",
            )
        arg_errors = contract.validate_args(step.args)
        if arg_errors:
            return FailureReport(
                code=FailureCode.INVALID_ARGUMENT,
                step_id=step.id,
                skill=step.skill,
                args=step.args,
                message="; ".join(arg_errors),
            )
        missing_facts = contract.missing_required_facts(step.args, self.state.facts)
        if missing_facts:
            return FailureReport(
                code=FailureCode.PRECONDITION_FAILED,
                step_id=step.id,
                skill=step.skill,
                args=step.args,
                message=f"missing committed facts: {sorted(missing_facts)}",
            )
        if step.skill == "pick_object" and contract.pose_ttl_s is not None:
            obj = str(step.args.get("object", ""))
            object_state = self.state.objects.get(obj)
            pose = object_state.pose if object_state else None
            if pose is None or not pose.is_fresh(
                now=self.wall_clock(), ttl_s=contract.pose_ttl_s
            ):
                return FailureReport(
                    code=FailureCode.POSE_STALE,
                    step_id=step.id,
                    skill=step.skill,
                    args=step.args,
                    message=f"object pose is missing or stale: {obj}",
                )
        return None

    def _execute_and_verify(
        self,
        step: PlanStep,
        contract: SkillContract,
        attempt: int,
    ) -> tuple[SkillResult, VerificationResult]:
        skill = self.skill_registry.get(step.skill)
        if skill is None:
            execution = SkillResult.rejected(
                FailureCode.UNAVAILABLE,
                message=f"skill not registered: {step.skill}",
            )
        else:
            self._set_phase(RuntimePhase.EXECUTE, step=step, attempt=attempt)
            self.budget.record_action()
            execution = self.executor.execute(skill, contract, step.args)
        self.trace.record(
            "execute_finished",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id,
            attempt=attempt,
            skill=step.skill,
            result=execution,
            state=self.state,
        )
        self._set_phase(RuntimePhase.VERIFY, step=step, attempt=attempt)
        observation = self.observation_provider.observe(
            step=step,
            execution=execution,
            state=self.state,
        )
        verifier = self.verifiers.get(contract.verifier)
        verification = verifier.verify(
            step=step,
            execution=execution,
            observation=observation,
            state=self.state,
            now=self.wall_clock(),
        )
        self.trace.record(
            "verification_finished",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id,
            attempt=attempt,
            skill=step.skill,
            result=execution,
            verification=verification,
            state=self.state,
        )
        return execution, verification

    def _reobserve(
        self,
        step: PlanStep,
        contract: SkillContract,
        attempt: int,
    ) -> VerificationResult:
        execution = SkillResult.unknown(
            FailureCode.PROTOCOL_ERROR,
            message="re-observing physical state",
        )
        observation = self.observation_provider.observe(
            step=step,
            execution=execution,
            state=self.state,
        )
        verification = self.verifiers.get(contract.verifier).verify(
            step=step,
            execution=execution,
            observation=observation,
            state=self.state,
            now=self.wall_clock(),
        )
        self.trace.record(
            "reobservation_finished",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id,
            attempt=attempt,
            skill=step.skill,
            verification=verification,
            state=self.state,
        )
        return verification

    def _commit(
        self,
        step: PlanStep,
        contract: SkillContract,
        verification: VerificationResult,
    ) -> None:
        self._set_phase(RuntimePhase.COMMIT, step=step)
        updates = verification.observations.get("state_updates", {})
        self.state.commit(
            step_id=step.id,
            produced=contract.produced_facts(step.args),
            invalidated=contract.invalidated_facts(step.args, self.state.facts),
            updates=updates,
        )
        self._committed_steps.append(step)
        self.trace.record(
            "step_committed",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id,
            skill=step.skill,
            verification=verification,
            state=self.state,
        )

    def _run_recovery_skill(
        self,
        failed_step: PlanStep,
        decision: RecoveryDecision,
    ) -> bool:
        if not decision.skill or decision.skill not in self.contracts or not self.budget.can_act():
            return False
        self._recovery_counter += 1
        recovery_step = PlanStep(
            id=f"recovery:{failed_step.id}:{self._recovery_counter}",
            skill=decision.skill,
            args=dict(decision.args),
        )
        contract = self.contracts[decision.skill]
        precheck = self._precheck(recovery_step, contract)
        if precheck is not None:
            return False
        execution, verification = self._execute_and_verify(recovery_step, contract, 1)
        if verification.status is not VerificationStatus.VERIFIED:
            self.trace.record(
                "recovery_skill_failed",
                step_id=failed_step.id,
                recovery_step_id=recovery_step.id,
                skill=recovery_step.skill,
                result=execution,
                verification=verification,
                state=self.state,
            )
            return False
        updates = verification.observations.get("state_updates", {})
        self.state.commit(
            step_id=recovery_step.id,
            produced=contract.produced_facts(recovery_step.args),
            invalidated=contract.invalidated_facts(recovery_step.args, self.state.facts),
            updates=updates,
            record_step=False,
        )
        self.trace.record(
            "recovery_skill_committed",
            step_id=failed_step.id,
            recovery_step_id=recovery_step.id,
            skill=recovery_step.skill,
            verification=verification,
            state=self.state,
        )
        return True

    def _replan(
        self,
        failure: FailureReport,
        remaining_steps: Sequence[PlanStep],
    ) -> bool:
        if not self.budget.can_replan():
            return False
        self._set_phase(RuntimePhase.REPLAN)
        self.budget.record_replan()
        try:
            repaired = self.replanner.replan(
                original_plan=self.plan,
                committed_steps=tuple(self._committed_steps),
                remaining_steps=remaining_steps,
                state=self.state,
                failure=failure,
                contracts=self.contracts,
            )
        except (ReplanError, RuntimeError, ValueError) as exc:
            self.trace.record("replan_failed", failure=failure, message=str(exc), state=self.state)
            return False
        if repaired is None:
            self.trace.record("replan_unavailable", failure=failure, state=self.state)
            return False
        self.plan = repaired
        self.trace.record(
            "plan_repaired",
            plan_id=repaired.plan_id,
            plan_version=repaired.version,
            parent_version=repaired.parent_version,
            steps=[step.to_dict() for step in repaired.steps],
            state=self.state,
        )
        return True

    def _finish_goal(self) -> MissionResult:
        observation = self.goal_observer(self.original_goal, self.state)
        verification = self.goal_verifier.verify(
            self.original_goal,
            self.state,
            observation,
        )
        self.trace.record("goal_verification", verification=verification, state=self.state)
        if verification.status is not VerificationStatus.VERIFIED:
            return self._abort(
                FailureReport(
                    code=verification.failure_code or FailureCode.GOAL_NOT_SATISFIED,
                    message=verification.message,
                )
            )
        self.phase = RuntimePhase.DONE
        return self._result(MissionStatus.SUCCEEDED, None)

    def _failure_from(
        self,
        step: PlanStep,
        attempts: int,
        execution: SkillResult,
        verification: VerificationResult,
    ) -> FailureReport:
        return FailureReport(
            code=verification.failure_code
            or execution.failure_code
            or FailureCode.VERIFICATION_FAILED,
            step_id=step.id,
            skill=step.skill,
            args=step.args,
            attempts=attempts,
            message=verification.message or execution.message,
        )

    def _record_recovery(
        self,
        step: PlanStep,
        attempt: int,
        failure: FailureReport,
        decision: RecoveryDecision,
    ) -> None:
        self._set_phase(RuntimePhase.RECOVER, step=step, attempt=attempt)
        self.trace.record(
            "recovery_decision",
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id,
            attempt=attempt,
            skill=step.skill,
            failure=failure,
            recovery=decision,
            state=self.state,
        )

    def _set_phase(
        self,
        phase: RuntimePhase,
        *,
        step: PlanStep | None = None,
        attempt: int | None = None,
    ) -> None:
        self.phase = phase
        self.trace.record(
            "phase_changed",
            phase=phase,
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            step_id=step.id if step else None,
            skill=step.skill if step else None,
            attempt=attempt,
            state=self.state,
        )

    def _abort(self, failure: FailureReport) -> MissionResult:
        self.phase = RuntimePhase.ABORT
        self.state.last_failure = failure.code
        return self._result(MissionStatus.ABORTED, failure)

    def _result(
        self,
        status: MissionStatus,
        failure: FailureReport | None,
    ) -> MissionResult:
        result = MissionResult(
            status=status,
            mission_id=self.mission_id,
            plan_id=self.plan.plan_id,
            plan_version=self.plan.version,
            state=self.state.snapshot(),
            total_actions=self.budget.total_actions,
            replans=self.budget.replans,
            failure=failure,
            trajectory_path=str(self.trace.path) if getattr(self.trace, "path", None) else None,
        )
        self.trace.record(
            "mission_finished",
            status=status,
            failure=failure,
            result=result,
            state=self.state,
        )
        if not self._closed:
            self.trace.close()
            self._closed = True
        return result
