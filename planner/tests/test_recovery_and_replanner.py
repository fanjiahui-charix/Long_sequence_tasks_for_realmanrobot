from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.models import (
    FailureCode,
    FailureReport,
    MissionBudgets,
    VerificationResult,
)
from planner.agent_runtime.recovery import (
    BudgetTracker,
    FailureLoopDetector,
    RecoveryAction,
    RecoveryPolicy,
)


def test_unknown_side_effect_never_blind_retries():
    contract = default_contracts()["pick_object"]
    failure = FailureReport(
        code=FailureCode.GRASP_AMBIGUOUS,
        step_id="s1",
        skill="pick_object",
        args={"object": "cup"},
        attempts=1,
    )

    decision = RecoveryPolicy().decide(
        contract,
        failure,
        VerificationResult.unknown(FailureCode.GRASP_AMBIGUOUS),
        BudgetTracker(MissionBudgets()),
    )

    assert decision.action is RecoveryAction.REPLAN


def test_stale_pose_runs_deterministic_perception_recovery():
    contract = default_contracts()["pick_object"]
    failure = FailureReport(
        code=FailureCode.POSE_STALE,
        step_id="s1",
        skill="pick_object",
        args={"object": "cup"},
        attempts=0,
    )

    decision = RecoveryPolicy().decide(
        contract,
        failure,
        VerificationResult.failed(FailureCode.POSE_STALE),
        BudgetTracker(MissionBudgets()),
    )

    assert decision.action is RecoveryAction.RUN_SKILL
    assert decision.skill == "detect_object"
    assert decision.args == {"object": "cup"}


def test_definite_grasp_failure_reperceives_before_retry():
    contract = default_contracts()["pick_object"]
    failure = FailureReport(
        code=FailureCode.GRASP_FAILED,
        skill="pick_object",
        args={"object": "cup"},
        attempts=1,
    )

    decision = RecoveryPolicy().decide(
        contract,
        failure,
        VerificationResult.failed(FailureCode.GRASP_FAILED),
        BudgetTracker(MissionBudgets()),
    )

    assert decision.action is RecoveryAction.RUN_SKILL
    assert decision.skill == "detect_object"


def test_safety_failure_aborts_without_retry():
    contract = default_contracts()["navigate_to"]
    failure = FailureReport(code=FailureCode.SAFETY_VIOLATION, attempts=0)

    decision = RecoveryPolicy().decide(
        contract,
        failure,
        VerificationResult.failed(FailureCode.SAFETY_VIOLATION),
        BudgetTracker(MissionBudgets()),
    )

    assert decision.action is RecoveryAction.ABORT


def test_repeated_failure_same_state_escalates():
    tracker = FailureLoopDetector(threshold=3)

    for _ in range(2):
        assert not tracker.record(
            "pick_object",
            {"object": "cup"},
            FailureCode.GRASP_FAILED,
            "same-state",
        )

    assert tracker.record(
        "pick_object",
        {"object": "cup"},
        FailureCode.GRASP_FAILED,
        "same-state",
    )


def test_budget_tracker_prevents_extra_actions_and_replans():
    tracker = BudgetTracker(MissionBudgets(max_total_actions=1, max_replans=1))

    assert tracker.can_act()
    tracker.record_action()
    assert not tracker.can_act()
    assert tracker.can_replan()
    tracker.record_replan()
    assert not tracker.can_replan()
