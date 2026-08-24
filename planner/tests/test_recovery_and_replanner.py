from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.models import (
    FailureCode,
    FailureReport,
    MissionBudgets,
    MissionPlan,
    VerificationResult,
)
from planner.agent_runtime.recovery import (
    BudgetTracker,
    FailureLoopDetector,
    RecoveryAction,
    RecoveryPolicy,
)
from planner.agent_runtime.replanner import ReplanError, apply_repaired_suffix, build_replan_context
from planner.agent_runtime.state import WorldState


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


def _original_plan() -> MissionPlan:
    return MissionPlan.from_dict(
        {
            "plan_id": "p1",
            "version": 1,
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
                {
                    "id": "s2",
                    "skill": "detect_object",
                    "args": {"object": "cup"},
                    "depends_on": ["s1"],
                },
                {
                    "id": "s3",
                    "skill": "pick_object",
                    "args": {"object": "cup"},
                    "depends_on": ["s2"],
                },
            ],
        }
    )


def test_replan_keeps_committed_prefix_immutable():
    original = _original_plan()
    state = WorldState(
        current_location="pointb",
        facts={"HandEmpty", "At(pointb)"},
        completed_steps=["s1"],
    )

    repaired = apply_repaired_suffix(
        original=original,
        committed_steps=[original.steps[0]],
        returned_steps=[
            {"id": "s2r", "skill": "detect_object", "args": {"object": "cup"}},
            {
                "id": "s3r",
                "skill": "pick_object",
                "args": {"object": "cup"},
                "depends_on": ["s2r"],
            },
        ],
        state=state,
        contracts=default_contracts(),
    )

    assert repaired.version == original.version + 1
    assert repaired.parent_version == original.version
    assert [step.id for step in repaired.steps] == ["s2r", "s3r"]
    assert repaired.goal == original.goal


def test_replan_rejects_committed_step_id_reuse():
    original = _original_plan()
    state = WorldState(facts={"HandEmpty", "At(pointb)"}, completed_steps=["s1"])

    try:
        apply_repaired_suffix(
            original=original,
            committed_steps=[original.steps[0]],
            returned_steps=[
                {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}}
            ],
            state=state,
            contracts=default_contracts(),
        )
    except ReplanError as exc:
        assert "committed" in str(exc)
    else:
        raise AssertionError("replanner must not reuse a committed step id")


def test_replan_context_is_compact_and_state_grounded():
    original = _original_plan()
    state = WorldState(
        current_location="pointb",
        facts={"HandEmpty", "At(pointb)"},
        completed_steps=["s1"],
    )
    failure = FailureReport(
        code=FailureCode.OBJECT_NOT_FOUND,
        step_id="s2",
        skill="detect_object",
        args={"object": "cup"},
        attempts=2,
    )

    context = build_replan_context(
        original,
        state,
        [original.steps[0]],
        list(original.steps[1:]),
        failure,
        default_contracts(),
    )

    assert set(context) == {
        "goal",
        "verified_world_state",
        "committed_steps",
        "remaining_plan",
        "failure",
        "available_skills",
    }
    assert context["verified_world_state"]["current_location"] == "pointb"
