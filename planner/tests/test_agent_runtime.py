import json
from collections import defaultdict, deque
from types import SimpleNamespace

from planner.agent_runtime.contracts import default_contracts
from planner.agent_runtime.executor import SkillExecutor
from planner.agent_runtime.models import (
    FailureCode,
    MissionBudgets,
    MissionPlan,
    MissionStatus,
    SkillResult,
)
from planner.agent_runtime.recovery import RecoveryPolicy
from planner.agent_runtime.replanner import NoOpReplanner
from planner.agent_runtime.runtime import AgentRuntime
from planner.agent_runtime.state import ObjectPoseState, ObjectState, WorldState
from planner.agent_runtime.trace import JsonlTraceWriter
from planner.agent_runtime.verifiers import GoalVerifier, VerifierRegistry
from planner.skills.mock_backend import MockRobotBackend
from planner.skills.registry import build_default_skill_registry


def test_agent_runtime_is_available_from_public_package():
    from planner.agent_runtime import AgentRuntime as PublicAgentRuntime

    assert PublicAgentRuntime is AgentRuntime


def test_cli_builds_only_agent_runtime(tmp_path, monkeypatch):
    from planner.examples.run_long_task import build_runtime

    monkeypatch.setenv("LONG_TASKS_NAV_BACKEND", "mock")
    monkeypatch.setenv("LONG_TASKS_PERCEPTION_BACKEND", "mock")
    monkeypatch.setenv("LONG_TASKS_MANIPULATION_BACKEND", "mock")
    args = SimpleNamespace(
        mission_id="cli-test",
        mission_timeout=60.0,
        max_total_actions=10,
        max_replans=0,
        failure_repeat_threshold=3,
    )
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "at_location", "location": "pointb"},
            "steps": [
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}}
            ],
        }
    )

    runtime = build_runtime(
        plan,
        args,
        trace_path=tmp_path / "cli.jsonl",
        planner_client=None,
    )

    assert isinstance(runtime, AgentRuntime)
    assert runtime.budgets.max_total_actions == 10
    runtime.trace.close()


def test_cli_source_has_no_legacy_executor_path():
    from pathlib import Path
    import planner.examples.run_long_task as entry

    source = Path(entry.__file__).read_text(encoding="utf-8")
    assert "TaskExecutor" not in source
    assert "--runtime" not in source
    assert "legacy" not in source.lower()


def test_no_python_entrypoint_references_task_executor():
    from pathlib import Path

    planner_root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in planner_root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        if "TaskExecutor" in path.read_text(encoding="utf-8") or "planner.executor" in path.read_text(
            encoding="utf-8"
        ):
            offenders.append(path.relative_to(planner_root).as_posix())
    assert offenders == []


class ScriptedSkill:
    def __init__(self, name, results):
        self.name = name
        self.results = deque(results)

    def run(self, **_kwargs):
        if self.results:
            return self.results.popleft()
        return SkillResult.failed(FailureCode.INTERNAL_ERROR, message="script exhausted")


class ScriptedObservationProvider:
    def __init__(self, observations):
        self.observations = defaultdict(deque)
        for skill, values in observations.items():
            self.observations[skill].extend(values)

    def observe(self, *, step, execution, state):
        del execution, state
        if self.observations[step.skill]:
            return self.observations[step.skill].popleft()
        return {}


def make_runtime(
    *,
    plan,
    skills,
    observation_provider,
    state=None,
    budgets=None,
    goal_observer=None,
    trace=None,
    now=100.0,
):
    return AgentRuntime(
        mission_id="m1",
        plan=plan,
        state=state or WorldState(),
        contracts=default_contracts(),
        skill_registry=skills,
        executor=SkillExecutor(),
        observation_provider=observation_provider,
        verifiers=VerifierRegistry(),
        goal_verifier=GoalVerifier(),
        recovery_policy=RecoveryPolicy(),
        replanner=NoOpReplanner(),
        budgets=budgets or MissionBudgets(max_replans=0),
        trace=trace,
        monotonic_clock=lambda: now,
        wall_clock=lambda: now,
        goal_observer=goal_observer or (lambda _goal, _state: {}),
    )


def test_failed_verification_does_not_commit(tmp_path):
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "at_location", "location": "pointb"},
            "steps": [
                {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}}
            ],
        }
    )
    state = WorldState()
    trace = JsonlTraceWriter(tmp_path / "failed.jsonl", mission_id="m1", clock=lambda: 100.0)
    runtime = make_runtime(
        plan=plan,
        state=state,
        skills={"navigate_to": ScriptedSkill("navigate_to", [SkillResult.succeeded()])},
        observation_provider=ScriptedObservationProvider(
            {
                "navigate_to": [
                    {"target": "pointb", "move_status": "failed", "running_status": "idle"}
                ]
            }
        ),
        trace=trace,
    )

    result = runtime.run()

    assert result.status is MissionStatus.ABORTED
    assert state.completed_steps == []
    assert "At(pointb)" not in state.facts


def test_retry_budget_prevents_loop():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}}
            ],
        }
    )
    failures = [SkillResult.failed(FailureCode.OBJECT_NOT_FOUND, retryable=True)] * 10
    runtime = make_runtime(
        plan=plan,
        skills={"detect_object": ScriptedSkill("detect_object", failures)},
        observation_provider=ScriptedObservationProvider(
            {"detect_object": [{"object": "cup", "found": False}] * 10}
        ),
        budgets=MissionBudgets(max_total_actions=3, max_replans=0),
    )

    result = runtime.run()

    assert result.status is MissionStatus.ABORTED
    assert result.total_actions <= 3


def test_final_goal_must_be_verified():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}}
            ],
        }
    )
    observation = {
        "object": "cup",
        "found": True,
        "pose": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        "frame_id": "camera",
        "timestamp": 100.0,
        "source": "script",
    }
    runtime = make_runtime(
        plan=plan,
        skills={"detect_object": ScriptedSkill("detect_object", [SkillResult.succeeded()])},
        observation_provider=ScriptedObservationProvider({"detect_object": [observation]}),
        goal_observer=lambda _goal, _state: {"holding_object": None},
    )

    result = runtime.run()

    assert result.status is MissionStatus.ABORTED
    assert result.failure.code is FailureCode.GOAL_NOT_SATISFIED


def test_unknown_side_effect_commits_only_if_world_verifies():
    plan = MissionPlan.from_dict(
        {
            "goal": {"type": "holding_object", "object": "cup"},
            "steps": [
                {"id": "s1", "skill": "pick_object", "args": {"object": "cup"}}
            ],
        }
    )
    state = WorldState(
        facts={"HandEmpty", "ObjectLocalized(cup)"},
        objects={
            "cup": ObjectState(
                name="cup",
                visible=True,
                pose=ObjectPoseState(
                    pose=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                    frame_id="camera",
                    timestamp=100.0,
                    source="script",
                    valid=True,
                ),
            )
        },
    )
    runtime = make_runtime(
        plan=plan,
        state=state,
        skills={
            "pick_object": ScriptedSkill(
                "pick_object",
                [SkillResult.unknown(FailureCode.PROTOCOL_ERROR)],
            )
        },
        observation_provider=ScriptedObservationProvider(
            {"pick_object": [{"holding_object": "cup", "grasped": True}]}
        ),
        goal_observer=lambda _goal, _state: {"holding_object": "cup"},
    )

    result = runtime.run()

    assert result.status is MissionStatus.SUCCEEDED
    assert state.completed_steps == ["s1"]
    assert state.holding_object == "cup"


def test_complete_mock_fault_injection_episode(tmp_path, monkeypatch):
    monkeypatch.setenv("LONG_TASKS_NAV_BACKEND", "mock")
    monkeypatch.setenv("LONG_TASKS_PERCEPTION_BACKEND", "mock")
    monkeypatch.setenv("LONG_TASKS_MANIPULATION_BACKEND", "mock")
    backend = MockRobotBackend(clock=lambda: 100.0)
    backend.script(
        "detect_object",
        [SkillResult.failed(FailureCode.OBJECT_NOT_FOUND, retryable=True), SkillResult.succeeded()],
    )
    backend.script(
        "pick_object",
        [SkillResult.failed(FailureCode.GRASP_FAILED, retryable=True), SkillResult.succeeded()],
    )
    registry = build_default_skill_registry(backend)
    plan = MissionPlan.from_dict(
        {
            "plan_id": "episode",
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
                {
                    "id": "s4",
                    "skill": "navigate_to",
                    "args": {"target": "pointa"},
                    "depends_on": ["s3"],
                },
            ],
        }
    )
    trace_path = tmp_path / "episode.jsonl"
    trace = JsonlTraceWriter(trace_path, mission_id="m1", clock=lambda: 100.0)
    runtime = make_runtime(
        plan=plan,
        skills=registry,
        observation_provider=__import__(
            "planner.agent_runtime.verifiers", fromlist=["SkillObservationProvider"]
        ).SkillObservationProvider(registry),
        goal_observer=lambda _goal, _state: {
            "holding_object": backend.holding_object,
            "current_location": backend.location,
            "placed_target": backend.placed_target,
        },
        budgets=MissionBudgets(max_total_actions=12, max_replans=0),
        trace=trace,
    )

    result = runtime.run()

    assert result.status is MissionStatus.SUCCEEDED
    assert result.state["completed_steps"] == ["s1", "s2", "s3", "s4"]
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["event_type"] == "recovery_decision" for event in events)
    assert [event["step_id"] for event in events if event["event_type"] == "step_committed"] == [
        "s1",
        "s2",
        "s3",
        "s4",
    ]
