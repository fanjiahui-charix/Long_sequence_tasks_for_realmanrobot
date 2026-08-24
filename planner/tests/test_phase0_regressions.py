from planner.agent_runtime.models import ExecStatus, FailureCode
from planner.agent_runtime.protocol import extract_machine_result
from planner.examples.run_long_task import _patch_plan
from planner.skills.mock_backend import MockRobotBackend
from planner.skills.navigation_skill import AlignToTableSkill, LocateTableSkill, NavigateToSkill
from planner.skills.perception_skill import DetectObjectSkill, LookAtSkill


def test_patch_plan_preserves_remaining_steps(monkeypatch):
    monkeypatch.setattr(
        "planner.examples.run_long_task._candidate_markers",
        lambda _backend: {"pointc"},
    )
    plan = {
        "goal": "pick",
        "steps": [
            {"id": "s1", "skill": "navigate_to", "args": {"target": "table"}},
            {"id": "s2", "skill": "detect_object", "args": {"object": "mustard"}},
            {"id": "s3", "skill": "pick_object", "args": {"object": "mustard"}},
        ],
    }

    patched = _patch_plan(plan, "pose_grasp", "go to pointc and pick mustard", "mock")

    assert [step["skill"] for step in patched["steps"]] == [
        "navigate_to",
        "detect_object",
        "pick_object",
    ]
    assert patched["steps"][0]["args"]["marker"] == "pointc"
    assert patched["steps"][0]["args"]["target"] == "pointc"
    assert patched["steps"][2]["args"]["mode"] == "pose_grasp"


def test_unconnected_skills_do_not_fake_success():
    locate = LocateTableSkill().run(label="1")
    align = AlignToTableSkill().run(table="1")
    look = LookAtSkill().run(target="table")

    assert locate.status is ExecStatus.REJECTED
    assert align.status is ExecStatus.REJECTED
    assert align.failure_code is FailureCode.UNAVAILABLE
    assert look.status is ExecStatus.REJECTED


def test_detect_without_pose_is_rejected(monkeypatch):
    monkeypatch.delenv("LONG_TASKS_FOUNDATIONPOSE_POSE", raising=False)
    monkeypatch.delenv("LONG_TASKS_PERCEPTION_BACKEND", raising=False)

    result = DetectObjectSkill().run(object="cup")

    assert result.status is ExecStatus.REJECTED
    assert result.failure_code is FailureCode.PERCEPTION_UNAVAILABLE


def test_mixed_log_stdout_extracts_final_json_result():
    stdout = (
        "[INFO] opening hand\n"
        "[INFO] moving\n"
        '{"ok": true, "arm_ns": "r_arm"}\n'
    )

    assert extract_machine_result(stdout) == {"ok": True, "arm_ns": "r_arm"}


def test_extract_machine_result_rejects_log_only_output():
    try:
        extract_machine_result("[INFO] no result\n")
    except RuntimeError as exc:
        assert "no JSON object" in str(exc)
    else:
        raise AssertionError("log-only stdout must not be accepted")


def test_mock_navigation_separates_send_from_observe(monkeypatch):
    monkeypatch.setenv("LONG_TASKS_NAV_BACKEND", "mock")
    backend = MockRobotBackend()
    skill = NavigateToSkill(mock_backend=backend)

    result = skill.run(target="pointb")

    assert result.data["command_accepted"] is True
    assert "arrived" not in result.data
    assert skill.observe(target="pointb")["arrived"] is True


def test_mock_detect_produces_fresh_pose_without_fake_confidence(monkeypatch):
    monkeypatch.setenv("LONG_TASKS_PERCEPTION_BACKEND", "mock")
    backend = MockRobotBackend(clock=lambda: 12.0)
    skill = DetectObjectSkill(mock_backend=backend)

    assert skill.run(object="cup").ok
    observation = skill.observe(object="cup")

    assert observation["timestamp"] == 12.0
    assert observation["confidence"] is None
    assert observation["source"] == "mock"
