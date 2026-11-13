import asyncio
import time

from robot_agent.agent import ReActAgent
from robot_agent.backends.mock_robot import MockRobotBackend
from robot_agent.executor import ToolExecutor
from robot_agent.memory.episodic import EpisodicMemory
from robot_agent.schemas import AgentDecision, SkillReply
from robot_agent.state import WorkingMemory
from robot_agent.tool_registry import ToolRegistry


def test_executor_refreshes_expired_telemetry_before_actuation(mission, verifier):
    backend = MockRobotBackend()
    state = WorkingMemory(mission=mission)
    obs = asyncio.run(backend.observe_robot_state(mission))
    state.ingest(obs, verifier, now=time.time())
    state.last_observation.timestamp -= 10
    result = asyncio.run(
        ToolExecutor(ToolRegistry(backend, verifier)).execute(
            AgentDecision(
                action_type="CALL_TOOL",
                tool_name="navigate_to",
                arguments={"target": "B"},
                decision_summary="safe request",
            ),
            state,
        )
    )
    assert result.status == "SUCCEEDED"
    assert backend.calls == ["navigate_to"]


def test_navigation_to_another_target_cannot_verify_failed_recovery(
    mission, verifier, tmp_path
):
    class WrongRecovery:
        is_real_llm = False

        def __init__(self):
            self.turn = 0

        async def decide(self, context):
            self.turn += 1
            if self.turn <= 2:
                return AgentDecision(
                    action_type="CALL_TOOL",
                    tool_name="navigate_to",
                    arguments={"target": "B" if self.turn == 1 else "A"},
                    decision_summary="test target-scoped recovery",
                )
            return AgentDecision(action_type="REQUEST_HELP", decision_summary="stop")

    backend = MockRobotBackend(faults={"navigate_to": ["NAV_FAILED"]})
    with EpisodicMemory(tmp_path / "memory.sqlite3") as store:
        report = asyncio.run(
            ReActAgent(
                WrongRecovery(), ToolRegistry(backend, verifier), memory=store
            ).run(mission)
        )
        assert report.metrics.recoveries == 0
        assert store.retrieve(failure_type="NAV_FAILED") == []


def test_coroutine_timeout_leaves_physical_interlock(mission, verifier):
    class SlowRobot(MockRobotBackend):
        async def navigate_to(self, target, mission):
            self.settled = False
            self.navigation_status = "MOVING"
            await asyncio.sleep(5)
            return SkillReply()

    backend = SlowRobot()
    executor = ToolExecutor(
        ToolRegistry(backend, verifier, timeouts={"navigate_to": 0.01})
    )
    state = WorkingMemory(mission=mission)
    state.ingest(
        asyncio.run(backend.observe_robot_state(mission)), verifier, now=time.time()
    )
    result = asyncio.run(
        executor.execute(
            AgentDecision(
                action_type="CALL_TOOL",
                tool_name="navigate_to",
                arguments={"target": "B"},
                decision_summary="timeout test",
            ),
            state,
        )
    )
    assert result.status == "TIMEOUT" and state.uncertain_action
    observe = AgentDecision(
        action_type="CALL_TOOL",
        tool_name="observe_robot_state",
        arguments={},
        decision_summary="read still moving",
    )
    asyncio.run(executor.execute(observe, state))
    assert state.uncertain_action == "navigate_to"


def test_external_cancellation_calls_stop_but_keeps_unknown_state(mission, verifier):
    class CancellableRobot(MockRobotBackend):
        def __init__(self):
            super().__init__()
            self.cancel_calls = 0

        async def navigate_to(self, target, mission):
            self.settled = False
            await asyncio.sleep(5)

        async def cancel_current_action(self):
            self.cancel_calls += 1

    async def exercise():
        backend = CancellableRobot()
        state = WorkingMemory(mission=mission)
        state.ingest(
            await backend.observe_robot_state(mission), verifier, now=time.time()
        )
        executor = ToolExecutor(ToolRegistry(backend, verifier))
        decision = AgentDecision(
            action_type="CALL_TOOL",
            tool_name="navigate_to",
            arguments={"target": "B"},
            decision_summary="cancel test",
        )
        task = asyncio.create_task(executor.execute(decision, state))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert backend.cancel_calls == 1
        assert state.uncertain_action == "navigate_to"
        assert state.last_error == "MISSION_CANCELLED"

    asyncio.run(exercise())


def test_cancellation_during_post_action_observation_keeps_interlock(mission, verifier):
    class Robot(MockRobotBackend):
        def __init__(self):
            super().__init__()
            self.action_returned = False
            self.stops = 0

        async def navigate_to(self, target, mission):
            result = await super().navigate_to(target, mission)
            self.action_returned = True
            return result

        async def observe_robot_state(self, mission):
            if self.action_returned:
                await asyncio.sleep(5)
            return await super().observe_robot_state(mission)

        async def cancel_current_action(self):
            self.stops += 1

    async def check():
        backend = Robot()
        state = WorkingMemory(mission=mission)
        state.ingest(
            await backend.observe_robot_state(mission), verifier, now=time.time()
        )
        executor = ToolExecutor(ToolRegistry(backend, verifier))
        decision = AgentDecision(
            action_type="CALL_TOOL",
            tool_name="navigate_to",
            arguments={"target": "B"},
            decision_summary="test observation interruption",
        )
        task = asyncio.create_task(executor.execute(decision, state))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert state.uncertain_action == "navigate_to" and backend.stops == 1

    asyncio.run(check())


def test_navigation_carry_postcondition_detects_a_dropped_object(mission, verifier):
    from robot_agent.llm_adapter import ScriptedDecisionClient

    backend = MockRobotBackend(faults={"navigate_to": [None, "DROP_OBJECT"]})
    report = asyncio.run(
        ReActAgent(ScriptedDecisionClient(), ToolRegistry(backend, verifier)).run(
            mission
        )
    )
    errors = [e["result"]["error_code"] for e in report.trace if e["event"] == "tool"]
    assert "OBJECT_LOST_DURING_NAVIGATION" in errors
    assert report.status == "COMPLETED" and backend.calls.count("grasp_object") == 2


def test_arrival_without_held_object_cannot_verify_a_carry_recovery(
    mission, verifier, tmp_path
):
    from robot_agent.llm_adapter import ScriptedDecisionClient

    class ObserveThenAbort(ScriptedDecisionClient):
        async def decide(self, context):
            wm = context["working_memory"]
            if wm["last_error"] == "OBJECT_LOST_DURING_NAVIGATION":
                if wm["completed_actions"][-1]["tool"] == "observe_robot_state":
                    return AgentDecision(
                        action_type="ABORT", decision_summary="target was lost"
                    )
                return AgentDecision(
                    action_type="CALL_TOOL",
                    tool_name="observe_robot_state",
                    arguments={},
                    decision_summary="check actual holding",
                )
            return await super().decide(context)

    backend = MockRobotBackend(faults={"navigate_to": [None, "DROP_OBJECT"]})
    with EpisodicMemory(tmp_path / "memory.sqlite3") as memory:
        report = asyncio.run(
            ReActAgent(
                ObserveThenAbort(), ToolRegistry(backend, verifier), memory=memory
            ).run(mission)
        )
        assert report.metrics.recoveries == 0
        assert memory.retrieve(failure_type="OBJECT_LOST_DURING_NAVIGATION") == []
