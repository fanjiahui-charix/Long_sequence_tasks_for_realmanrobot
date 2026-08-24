import json

from planner.agent_runtime.models import SkillResult, VerificationResult
from planner.agent_runtime.state import WorldState
from planner.agent_runtime.trace import JsonlTraceWriter


def test_trace_is_flush_safe_and_json_serializable(tmp_path):
    path = tmp_path / "mission.jsonl"
    state = WorldState(current_location="pointa", facts={"At(pointa)", "HandEmpty"})

    with JsonlTraceWriter(path, mission_id="m1", clock=lambda: 12.5) as trace:
        trace.record(
            "execute_finished",
            plan_id="p1",
            plan_version=1,
            step_id="s1",
            attempt=1,
            skill="navigate_to",
            result=SkillResult.succeeded({"accepted": True}),
            verification=VerificationResult.verified({"arrived": True}),
            state=state,
        )
        assert path.read_text(encoding="utf-8").endswith("\n")

    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["timestamp"] == 12.5
    assert event["mission_id"] == "m1"
    assert event["event_type"] == "execute_finished"
    assert event["result"]["status"] == "succeeded"
    assert event["verification"]["status"] == "verified"
    assert event["state_hash"] == state.stable_hash()
    assert event["state"]["facts"] == ["At(pointa)", "HandEmpty"]


def test_trace_appends_multiple_events_without_overwriting(tmp_path):
    path = tmp_path / "mission.jsonl"

    with JsonlTraceWriter(path, mission_id="m1", clock=lambda: 1.0) as trace:
        trace.record("mission_started")
        trace.record("mission_finished")

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == [
        "mission_started",
        "mission_finished",
    ]
