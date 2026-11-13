import asyncio

import pytest

from robot_agent.agent import ReActAgent
from robot_agent.backends.mock_robot import MockRobotBackend
from robot_agent.llm_adapter import ScriptedDecisionClient
from robot_agent.memory.episodic import EpisodicMemory
from robot_agent.schemas import AgentDecision
from robot_agent.tool_registry import ToolRegistry


def run(mission, verifier, *, faults=None, client=None, memory=None, max_turns=30):
    backend = MockRobotBackend(faults=faults)
    agent = ReActAgent(
        client or ScriptedDecisionClient(),
        ToolRegistry(backend, verifier),
        memory=memory,
        max_turns=max_turns,
    )
    return asyncio.run(agent.run(mission)), backend


def test_complete_mock_mission_follows_live_observations(mission, verifier):
    report, backend = run(mission, verifier)
    assert report.status == "COMPLETED"
    assert report.final_verification.evidence["robot_at_start"] is True
    assert report.final_verification.evidence["object_held"] is True
    assert report.state.current_location == "A"
    assert report.state.grasped_object == "glasses_case"
    assert report.state.current_action is None
    assert backend.calls[:4] == [
        "navigate_to",
        "locate_object",
        "grasp_object",
        "navigate_to",
    ]
    assert report.metrics.llm_calls == 0  # Scripted decisions are not LLM calls.
    assert report.metrics.decision_calls >= 5


@pytest.mark.parametrize(
    "skill,error",
    [
        ("navigate_to", "NAV_TIMEOUT"),
        ("locate_object", "OBJECT_NOT_FOUND"),
        ("grasp_object", "POSE_STALE"),
        ("grasp_object", "GRASP_NOT_HELD"),
        ("grasp_object", "TOOL_EXECUTION_UNKNOWN"),
    ],
)
def test_failure_recovery(mission, verifier, skill, error):
    report, backend = run(mission, verifier, faults={skill: [error]})
    assert report.status == "COMPLETED"
    assert report.metrics.failures >= 1
    assert report.metrics.recoveries >= 1
    if error == "TOOL_EXECUTION_UNKNOWN":
        assert backend.calls.count("grasp_object") == 1
        assert any(
            e["event"] == "decision"
            and e["decision"]["tool_name"] == "observe_robot_state"
            for e in report.trace
        )


def test_persistent_failure_is_bounded(mission, verifier):
    report, backend = run(
        mission, verifier, faults={"locate_object": ["OBJECT_NOT_FOUND"] * 20}
    )
    assert report.status == "REQUEST_HELP"
    assert backend.calls.count("locate_object") == 3
    assert not report.final_verification.verified


def test_recovery_is_saved_and_injected_into_next_mission(mission, verifier, tmp_path):
    with EpisodicMemory(tmp_path / "episodes.sqlite3") as memory:
        report, _ = run(
            mission, verifier, faults={"grasp_object": ["POSE_STALE"]}, memory=memory
        )
        found = memory.retrieve(
            skill="grasp_object",
            failure_type="POSE_STALE",
            object_category="glasses_case",
        )
        assert report.status == "COMPLETED" and found and found[0].verified
        client = ScriptedDecisionClient()
        next_mission = mission.model_copy(update={"mission_id": "m2"})
        second, _ = run(
            next_mission,
            verifier,
            client=client,
            memory=memory,
            faults={"grasp_object": ["POSE_STALE"]},
        )
        assert second.status == "COMPLETED"
        assert client.contexts[0]["episodic_memory"]
        assert any(
            c["episodic_memory"] and c["working_memory"]["last_error"] == "POSE_STALE"
            for c in client.contexts
        )
        assert all(
            "working_memory" in c and "latest_observation" in c["working_memory"]
            for c in client.contexts
        )


def test_premature_finish_never_completes(mission, verifier):
    class AlwaysFinish:
        is_real_llm = False

        async def decide(self, context):
            return AgentDecision(
                action_type="FINISH", decision_summary="I claim success"
            )

    report, _ = run(mission, verifier, client=AlwaysFinish(), max_turns=5)
    assert report.status == "REQUEST_HELP"
    assert report.metrics.finish_rejections > 0
    assert not report.final_verification.verified


def test_untrusted_arguments_are_rejected_before_backend_call(mission, verifier):
    from robot_agent.state import WorkingMemory
    from robot_agent.executor import ToolExecutor

    backend = MockRobotBackend()
    registry = ToolRegistry(backend, verifier)
    state = WorkingMemory(mission=mission)
    decision = AgentDecision(
        action_type="CALL_TOOL",
        tool_name="navigate_to",
        arguments={"target": "B", "speed": 999},
        decision_summary="bad params",
    )
    result = asyncio.run(ToolExecutor(registry).execute(decision, state))
    assert result.error_code == "INVALID_ARGUMENT"
    assert not backend.calls


def test_final_read_detects_lost_object(mission, verifier):
    class DropAtFinish(ScriptedDecisionClient):
        async def decide(self, context):
            d = await super().decide(context)
            if d.action_type == "FINISH":
                backend.held = False
            return d

    backend = MockRobotBackend()
    report = asyncio.run(
        ReActAgent(DropAtFinish(), ToolRegistry(backend, verifier), max_turns=8).run(
            mission
        )
    )
    assert report.status != "COMPLETED"
    assert report.metrics.finish_rejections >= 1


def test_physical_timeout_requires_explicit_reconciliation(mission, verifier):
    from robot_agent.executor import ToolExecutor
    from robot_agent.state import WorkingMemory

    backend = MockRobotBackend(faults={"navigate_to": ["NAV_TIMEOUT"]})
    state = WorkingMemory(mission=mission)
    state.ingest(
        asyncio.run(backend.observe_robot_state(mission)),
        verifier,
        now=__import__("time").time(),
    )
    executor = ToolExecutor(ToolRegistry(backend, verifier))
    call = AgentDecision(
        action_type="CALL_TOOL",
        tool_name="navigate_to",
        arguments={"target": "B"},
        decision_summary="go",
    )
    first = asyncio.run(executor.execute(call, state))
    assert first.execution_uncertain and state.uncertain_action
    blocked = asyncio.run(executor.execute(call, state))
    assert blocked.error_code == "ACTION_UNRESOLVED"
    assert backend.calls.count("navigate_to") == 1
    observe = AgentDecision(
        action_type="CALL_TOOL",
        tool_name="observe_robot_state",
        arguments={},
        decision_summary="reconcile",
    )
    asyncio.run(executor.execute(observe, state))
    assert state.uncertain_action is None
