import pytest
from pydantic import ValidationError

from robot_agent.schemas import AgentDecision, Observation, PoseReference
from robot_agent.state import WorkingMemory
from robot_agent.verifier import DeterministicVerifier


def test_decision_is_one_high_level_tool():
    with pytest.raises(ValidationError):
        AgentDecision(
            action_type="CALL_TOOL",
            tool_name="joint_move",
            arguments={"joints": [1]},
            decision_summary="bad",
        )
    with pytest.raises(ValidationError):
        AgentDecision(
            action_type="FINISH",
            tool_name="navigate_to",
            arguments={},
            decision_summary="bad",
        )
    with pytest.raises(ValidationError):
        AgentDecision(
            action_type="CALL_TOOL",
            tool_name="navigate_to",
            arguments={},
            decision_summary="bad",
            steps=[],
        )


def test_only_measured_stable_calibrated_width_can_confirm_grasp(verifier, measured):
    obs = measured()
    assert verifier.grasp(obs, now=100).grasp_state == "HELD"
    assert verifier.grasp(measured(width=0), now=100).grasp_state == "NOT_HELD"
    assert verifier.grasp(measured(width=10), now=100).grasp_state == "UNKNOWN"
    assert verifier.grasp(obs, now=200).grasp_state == "UNKNOWN"
    obs.gripper_samples[0].measured = False
    assert verifier.grasp(obs, now=100).grasp_state == "UNKNOWN"
    assert (
        DeterministicVerifier(None, base_frame="mock_base")
        .grasp(measured(), now=100)
        .grasp_state
        == "UNKNOWN"
    )


def test_width_needs_post_retreat_samples(verifier, measured):
    obs = measured()
    obs.retreat_complete = False
    assert verifier.grasp(obs, now=100).grasp_state == "UNKNOWN"
    obs.retreat_complete = True
    obs.gripper_samples[0].width_mm = 30
    assert verifier.grasp(obs, now=100).grasp_state == "UNKNOWN"


def test_navigation_ack_or_idle_alone_is_not_arrival(verifier):
    obs = Observation(timestamp=100, source="ack", navigation_status="IDLE")
    assert not verifier.navigation(obs, target="B", now=100).verified
    obs.robot_location = "B"
    assert not verifier.navigation(obs, target="B", now=100).verified
    obs.localization_confirmed = True
    assert not verifier.navigation(obs, target="B", now=100).verified
    obs.motion_settled = True
    assert verifier.navigation(obs, target="B", now=100).verified
    assert not verifier.navigation(obs, target="A", now=100).verified


def test_pose_ttl_frame_location_epoch_and_rigid_transform(verifier):
    pose = PoseReference(
        pose_id="p",
        object_category="glasses_case",
        captured_at=100,
        reference_frame="mock_base",
        robot_location="B",
        motion_epoch=1,
        matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    )
    assert verifier.pose(pose, now=101, location="B", motion_epoch=1).verified
    assert not verifier.pose(pose, now=111, location="B", motion_epoch=1).verified
    assert not verifier.pose(pose, now=101, location="A", motion_epoch=1).verified
    assert not verifier.pose(pose, now=101, location="B", motion_epoch=2).verified
    assert not verifier.pose(
        pose.model_copy(update={"reference_frame": "camera"}),
        now=101,
        location="B",
        motion_epoch=1,
    ).verified
    with pytest.raises(ValidationError):
        PoseReference(
            pose_id="bad",
            object_category="glasses_case",
            captured_at=100,
            reference_frame="base",
            robot_location="B",
            motion_epoch=1,
            matrix=[[2, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        )


def test_final_goal_requires_fresh_location_and_verified_target_identity(
    mission, verifier, measured
):
    state = WorkingMemory(mission=mission)
    state.ingest(measured(), verifier, now=100)
    assert not verifier.final_goal(state, now=100).verified
    state.grasped_object = "glasses_case"
    assert verifier.final_goal(state, now=100).verified
    assert not verifier.final_goal(state, now=110).verified
    obs = measured()
    obs.robot_location = "B"
    state.ingest(obs, verifier, now=100)
    assert not verifier.final_goal(state, now=100).verified
    state.ingest(
        Observation(timestamp=101, source="feedback_missing"), verifier, now=101
    )
    assert state.current_location is None
    assert state.grasp_state == "UNKNOWN"


def test_evidence_boolean_strings_are_not_accepted():
    with pytest.raises(ValidationError):
        Observation(timestamp=100, source="bad", localization_confirmed="true")


def test_repeated_same_sensor_sample_is_not_stability_evidence(verifier, measured):
    obs = measured()
    obs.gripper_samples = [obs.gripper_samples[0]] * 3
    assert verifier.grasp(obs, now=100).grasp_state == "UNKNOWN"
