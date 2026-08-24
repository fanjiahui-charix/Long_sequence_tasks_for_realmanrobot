import os

from planner.agent_runtime.models import ExecStatus, FailureCode
from planner.examples.run_long_task import _patch_plan
from planner.examples.run_nav_grasp_json import _extract_machine_result
from planner.skills.navigation_skill import AlignToTableSkill, LocateTableSkill
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

    assert _extract_machine_result(stdout) == {"ok": True, "arm_ns": "r_arm"}


def test_extract_machine_result_rejects_log_only_output():
    try:
        _extract_machine_result("[INFO] no result\n")
    except RuntimeError as exc:
        assert "no JSON object" in str(exc)
    else:
        raise AssertionError("log-only stdout must not be accepted")
