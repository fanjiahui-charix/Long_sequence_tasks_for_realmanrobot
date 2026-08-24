from planner.agent_runtime.models import ExecStatus, FailureCode, SkillResult
from planner.agent_runtime.state import ObjectPoseState, WorldState


def test_skill_result_ok_only_for_succeeded():
    assert SkillResult.succeeded({"x": 1}).ok is True
    assert SkillResult.unknown(FailureCode.PROTOCOL_ERROR).ok is False
    assert SkillResult.failed(FailureCode.INTERNAL_ERROR).ok is False


def test_skill_result_serializes_enums_to_json_values():
    result = SkillResult.failed(
        FailureCode.NAVIGATION_FAILED,
        message="blocked",
        data={"target": "pointb"},
        retryable=True,
    )

    assert result.to_dict() == {
        "status": "failed",
        "data": {"target": "pointb"},
        "failure_code": "navigation_failed",
        "retryable": True,
        "message": "blocked",
    }


def test_world_state_hash_is_stable_for_equivalent_state():
    left = WorldState(facts={"HandEmpty", "At(pointa)"})
    right = WorldState(facts={"At(pointa)", "HandEmpty"})

    assert left.stable_hash() == right.stable_hash()


def test_object_pose_freshness_uses_injected_time():
    pose = ObjectPoseState(
        pose=[
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        frame_id="camera_middle",
        timestamp=10.0,
        source="mock",
        valid=True,
    )

    assert pose.is_fresh(now=11.0, ttl_s=2.0)
    assert not pose.is_fresh(now=13.0, ttl_s=2.0)


def test_commit_is_the_only_effect_application_path():
    state = WorldState(facts={"HandEmpty", "At(pointa)"})

    state.commit(
        step_id="s1",
        produced={"At(pointb)"},
        invalidated={"At(pointa)"},
        updates={"current_location": "pointb"},
    )

    assert state.completed_steps == ["s1"]
    assert "At(pointb)" in state.facts
    assert "At(pointa)" not in state.facts
    assert state.current_location == "pointb"
    assert state.revision == 1


def test_world_state_defaults_to_hand_empty_fact():
    assert WorldState().facts == {"HandEmpty"}
