import time

from planner.agent_runtime.contracts import RetryMode, SkillContract, default_contracts
from planner.agent_runtime.executor import SkillExecutor
from planner.agent_runtime.models import (
    ExecStatus,
    FailureCode,
    PlanStep,
    SkillResult,
    VerificationStatus,
)
from planner.agent_runtime.state import ObjectPoseState, ObjectState, WorldState
from planner.agent_runtime.verifiers import (
    GoalVerifier,
    GraspVerifier,
    NavigationVerifier,
    PerceptionVerifier,
)


IDENTITY_POSE = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


class SlowSkill:
    name = "slow"

    def run(self, **_kwargs):
        time.sleep(0.05)
        return SkillResult.succeeded()


def test_executor_timeout_of_side_effect_is_unknown():
    contract = SkillContract(
        name="slow",
        timeout_s=0.01,
        max_attempts=1,
        retry_mode=RetryMode.VERIFY_BEFORE_RETRY,
        side_effecting=True,
        verifier="control",
    )

    result = SkillExecutor().execute(SlowSkill(), contract, {})

    assert result.status is ExecStatus.UNKNOWN
    assert result.failure_code is FailureCode.PROTOCOL_ERROR


def test_navigation_command_acceptance_is_not_arrival():
    step = PlanStep(id="s1", skill="navigate_to", args={"target": "pointb"})

    verification = NavigationVerifier().verify(
        step=step,
        execution=SkillResult.succeeded({"command_accepted": True}),
        observation={
            "target": "pointb",
            "move_status": "moving",
            "running_status": "active",
        },
        state=WorldState(),
        now=10.0,
    )

    assert verification.status is VerificationStatus.FAILED
    assert verification.failure_code is FailureCode.NAVIGATION_FAILED


def test_navigation_verified_only_after_target_arrival():
    step = PlanStep(id="s1", skill="navigate_to", args={"target": "pointb"})

    verification = NavigationVerifier().verify(
        step=step,
        execution=SkillResult.succeeded({"command_accepted": True}),
        observation={
            "target": "pointb",
            "move_target": "pointb",
            "move_status": "succeeded",
            "running_status": "idle",
        },
        state=WorldState(),
        now=10.0,
    )

    assert verification.status is VerificationStatus.VERIFIED
    assert verification.observations["state_updates"]["current_location"] == "pointb"


def test_perception_rejects_stale_pose():
    step = PlanStep(id="s1", skill="detect_object", args={"object": "cup"})

    verification = PerceptionVerifier(pose_ttl_s=2.0).verify(
        step=step,
        execution=SkillResult.succeeded(),
        observation={
            "object": "cup",
            "found": True,
            "pose": IDENTITY_POSE,
            "frame_id": "camera",
            "timestamp": 7.0,
            "source": "mock",
        },
        state=WorldState(),
        now=10.0,
    )

    assert verification.failure_code is FailureCode.POSE_STALE


def test_perception_accepts_fresh_pose_without_confidence():
    step = PlanStep(id="s1", skill="detect_object", args={"object": "cup"})

    verification = PerceptionVerifier(pose_ttl_s=2.0).verify(
        step=step,
        execution=SkillResult.succeeded(),
        observation={
            "object": "cup",
            "found": True,
            "pose": IDENTITY_POSE,
            "frame_id": "camera",
            "timestamp": 9.0,
            "source": "mock",
            "confidence": None,
        },
        state=WorldState(),
        now=10.0,
    )

    assert verification.status is VerificationStatus.VERIFIED
    obj = verification.observations["state_updates"]["objects"]["cup"]
    assert obj.pose.confidence is None


def test_grasp_insufficient_evidence_is_unknown():
    step = PlanStep(id="s1", skill="pick_object", args={"object": "cup"})
    state = WorldState(
        objects={
            "cup": ObjectState(
                name="cup",
                visible=True,
                pose=ObjectPoseState(
                    pose=IDENTITY_POSE,
                    frame_id="camera",
                    timestamp=9.0,
                    source="mock",
                    valid=True,
                ),
            )
        },
        facts={"HandEmpty", "ObjectLocalized(cup)"},
    )

    verification = GraspVerifier().verify(
        step=step,
        execution=SkillResult.succeeded(),
        observation={},
        state=state,
        now=10.0,
    )

    assert verification.status is VerificationStatus.UNKNOWN
    assert verification.failure_code is FailureCode.GRASP_AMBIGUOUS


def test_goal_verifier_requires_current_holding_evidence():
    state = WorldState(holding_object="cup", facts={"Holding(cup)"})

    result = GoalVerifier().verify(
        {"type": "holding_object", "object": "cup"},
        state,
        {"holding_object": None},
    )

    assert result.status is VerificationStatus.FAILED
    assert result.failure_code is FailureCode.GOAL_NOT_SATISFIED


def test_goal_verifier_does_not_fall_back_to_stale_committed_state():
    state = WorldState(holding_object="cup", facts={"Holding(cup)"})

    result = GoalVerifier().verify(
        {"type": "holding_object", "object": "cup"},
        state,
        {"observation_error": "gripper feedback unavailable"},
    )

    assert result.status is VerificationStatus.FAILED
