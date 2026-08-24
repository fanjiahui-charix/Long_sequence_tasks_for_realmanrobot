# Closed-Loop Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot planner executor with a single contract-grounded, verified, recoverable, suffix-replanning AgentRuntime accepted by deterministic mock fault-injection tests.

**Architecture:** Add a focused `planner.agent_runtime` package whose state machine depends on typed skill, observation, verification, recovery, replanning, clock, and trace interfaces. Keep robot-specific ROS/TCP/FoundationPose behavior behind stateful skill adapters, make verified `WorldState` the only fact source, and route the sole CLI execution path through AgentRuntime.

**Tech Stack:** Python 3.10+ standard library (`dataclasses`, `enum`, `hashlib`, `json`, `concurrent.futures`, `pathlib`, `typing`), PyYAML already present in the repository, pytest.

---

## File Map

**Create**

- `planner/agent_runtime/__init__.py` — public runtime API.
- `planner/agent_runtime/models.py` — plans, results, failures, budgets, mission results, enums.
- `planner/agent_runtime/state.py` — verified object/world state, symbolic facts, stable snapshots/hashes.
- `planner/agent_runtime/contracts.py` — skill contracts and the trusted built-in contract registry.
- `planner/agent_runtime/semantic_validator.py` — schema conversion and symbolic dry-run validation.
- `planner/agent_runtime/executor.py` — timeout-aware invocation and exception normalization.
- `planner/agent_runtime/verifiers.py` — observation provider protocol, skill verifiers, goal verifier.
- `planner/agent_runtime/recovery.py` — deterministic recovery, repeated-failure tracking, budgets.
- `planner/agent_runtime/replanner.py` — suffix repair protocol, Qwen adapter, repaired-plan validation.
- `planner/agent_runtime/trace.py` — append-only JSONL event writer.
- `planner/agent_runtime/runtime.py` — explicit runtime state-machine orchestration.
- `planner/skills/mock_backend.py` — shared stateful mock robot used by CLI mock mode.
- `planner/tests/conftest.py` — reusable plan/result/scripted fixtures.
- `planner/tests/test_phase0_regressions.py` — false-success, marker patch, arrival, subprocess protocol regressions.
- `planner/tests/test_runtime_models.py` — typed results and world-state tests.
- `planner/tests/test_semantic_validator.py` — contract/schema symbolic validation tests.
- `planner/tests/test_executor_and_verifiers.py` — timeout and postcondition tests.
- `planner/tests/test_recovery_and_replanner.py` — safe retry, budgets, suffix immutability tests.
- `planner/tests/test_trace.py` — JSONL validity and event completeness tests.
- `planner/tests/test_agent_runtime.py` — commit, abort, final-goal, and full fault-injection episodes.

**Modify**

- `planner/skills/base.py` — use typed `SkillResult` and add optional observation protocol.
- `planner/skills/navigation_skill.py` — command/arrival separation and unavailable prototype results.
- `planner/skills/perception_skill.py` — fresh pose evidence and unavailable prototype results.
- `planner/skills/manipulation_skill.py` — typed results and stateful mock evidence.
- `planner/skills/human_skill.py` — typed human/abort results.
- `planner/skills/registry.py` — shared mock backend and observable registry.
- `planner/llm/schema.py` — delegate plan parsing/validation to contracts.
- `planner/llm/prompt_builder.py` — intent-only plan schema and compact replan prompt.
- `planner/llm/qwen_client.py` — text-only remaining-plan repair method.
- `planner/examples/run_long_task.py` — sole AgentRuntime CLI and non-destructive marker patch.
- `planner/examples/run_full_mock_demo.py` — invoke the AgentRuntime CLI-compatible path.
- `planner/examples/run_nav_grasp_json.py` — robust machine-result extraction from mixed stdout.
- `planner/README.md` and `planner/README.zh-CN.md` — new runtime, traces, mock acceptance, hardware deferral.

**Delete after migration**

- `planner/executor/task_executor.py`
- `planner/executor/__init__.py`
- `planner/examples/run_executor_demo.py`

## Task 1: Phase 0 Correctness Regressions

**Files:**

- Create: `planner/tests/test_phase0_regressions.py`
- Modify: `planner/examples/run_long_task.py`
- Modify: `planner/examples/run_nav_grasp_json.py`
- Modify: `planner/skills/navigation_skill.py`
- Modify: `planner/skills/perception_skill.py`

- [ ] **Step 1: Write failing regression tests**

Add tests with these exact behaviors:

```python
def test_patch_plan_preserves_remaining_steps():
    plan = {"goal": "pick", "steps": [
        {"id": "s1", "skill": "navigate_to", "args": {"target": "table"}},
        {"id": "s2", "skill": "detect_object", "args": {"object": "mustard"}},
        {"id": "s3", "skill": "pick_object", "args": {"object": "mustard"}},
    ]}
    patched = _patch_plan(plan, "pose_grasp", "go to pointc and pick mustard", "mock")
    assert [step["skill"] for step in patched["steps"]] == [
        "navigate_to", "detect_object", "pick_object"
    ]
    assert patched["steps"][0]["args"]["marker"] == "pointc"
    assert patched["steps"][2]["args"]["mode"] == "pose_grasp"


def test_unconnected_skills_do_not_fake_success():
    assert LocateTableSkill().run(label="1").status is ExecStatus.REJECTED
    assert AlignToTableSkill().run(table="1").failure_code is FailureCode.UNAVAILABLE
    assert LookAtSkill().run(target="table").status is ExecStatus.REJECTED


def test_detect_without_pose_is_rejected(monkeypatch):
    monkeypatch.delenv("LONG_TASKS_FOUNDATIONPOSE_POSE", raising=False)
    result = DetectObjectSkill().run(object="cup")
    assert result.status is ExecStatus.REJECTED
    assert result.failure_code is FailureCode.PERCEPTION_UNAVAILABLE


def test_mixed_log_stdout_extracts_final_json_result():
    stdout = "[INFO] opening hand\n[INFO] moving\n{\"ok\": true, \"arm_ns\": \"r_arm\"}\n"
    assert _extract_machine_result(stdout) == {"ok": True, "arm_ns": "r_arm"}
```

- [ ] **Step 2: Run tests and verify the expected failures**

Run:

```powershell
python -m pytest planner/tests/test_phase0_regressions.py -q
```

Expected: collection/import failures for typed models plus the current marker truncation, prototype false-success, missing-pose false-success, and mixed-output JSON parsing behaviors.

- [ ] **Step 3: Implement only the Phase 0 behavior surface**

Make `_patch_plan` deep-copy the plan, update the first existing `navigate_to` step's `marker`, preserve every step, and apply `pick_mode` only to `pick_object`. Add this parser to `run_nav_grasp_json.py`:

```python
def _extract_machine_result(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    if not candidates:
        raise RuntimeError("grasp subprocess produced no JSON object")
    return candidates[-1]
```

Temporarily import the typed enums/results from Task 2; complete Task 2 before making this test green.

- [ ] **Step 4: Commit the regression tests as the Phase 0 red checkpoint**

```powershell
git add -- planner/tests/test_phase0_regressions.py
git commit -m "test: capture planner false-success regressions"
```

## Task 2: Typed Runtime Models and Verified World State

**Files:**

- Create: `planner/agent_runtime/__init__.py`
- Create: `planner/agent_runtime/models.py`
- Create: `planner/agent_runtime/state.py`
- Create: `planner/tests/test_runtime_models.py`
- Modify: `planner/skills/base.py`

- [ ] **Step 1: Write failing model/state tests**

```python
def test_skill_result_ok_only_for_succeeded():
    assert SkillResult.succeeded({"x": 1}).ok is True
    assert SkillResult.unknown(FailureCode.PROTOCOL_ERROR).ok is False


def test_world_state_hash_is_stable_for_equivalent_state():
    left = WorldState(facts={"HandEmpty", "At(pointa)"})
    right = WorldState(facts={"At(pointa)", "HandEmpty"})
    assert left.stable_hash() == right.stable_hash()


def test_object_pose_freshness_uses_injected_time():
    pose = ObjectPoseState(
        pose=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        frame_id="camera_middle", timestamp=10.0, source="mock", valid=True,
    )
    assert pose.is_fresh(now=11.0, ttl_s=2.0)
    assert not pose.is_fresh(now=13.0, ttl_s=2.0)


def test_commit_is_the_only_effect_application_path():
    state = WorldState()
    state.commit(
        step_id="s1",
        produced={"At(pointb)"},
        invalidated={"At(pointa)"},
        updates={"current_location": "pointb"},
    )
    assert state.completed_steps == ["s1"]
    assert "At(pointb)" in state.facts
    assert state.revision == 1
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_runtime_models.py -q`.

Expected: import failure because `planner.agent_runtime.models/state` do not exist.

- [ ] **Step 3: Implement the typed model API**

Define the exact enums and value objects:

```python
class ExecStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FailureCode(str, Enum):
    UNAVAILABLE = "unavailable"
    INVALID_ARGUMENT = "invalid_argument"
    PRECONDITION_FAILED = "precondition_failed"
    NAVIGATION_FAILED = "navigation_failed"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    PERCEPTION_UNAVAILABLE = "perception_unavailable"
    OBJECT_NOT_FOUND = "object_not_found"
    POSE_INVALID = "pose_invalid"
    POSE_STALE = "pose_stale"
    GRASP_FAILED = "grasp_failed"
    GRASP_AMBIGUOUS = "grasp_ambiguous"
    PLACE_FAILED = "place_failed"
    PROTOCOL_ERROR = "protocol_error"
    SAFETY_VIOLATION = "safety_violation"
    VERIFICATION_FAILED = "verification_failed"
    GOAL_NOT_SATISFIED = "goal_not_satisfied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REPLAN_FAILED = "replan_failed"
    INTERNAL_ERROR = "internal_error"
```

Add dataclasses for `PlanStep`, `MissionPlan`, `SkillResult`, `VerificationResult`, `FailureReport`, `MissionBudgets`, and `MissionResult`, including `from_dict()`/`to_dict()` methods that do not leak enum objects into JSON.

- [ ] **Step 4: Implement world state and fact helpers**

Add `ObjectPoseState`, `ObjectState`, and `WorldState`; serialize sorted facts/object keys, hash canonical UTF-8 JSON with SHA-256, and expose a single `commit()` mutator. Initialize `facts` with `HandEmpty` unless a caller supplies an explicit set.

- [ ] **Step 5: Convert `skills/base.py` to the typed result**

Re-export `SkillResult` from `planner.agent_runtime.models` and define:

```python
class RobotSkill(Protocol):
    name: str
    def run(self, **kwargs: Any) -> SkillResult:
        raise NotImplementedError


class ObservableSkill(RobotSkill, Protocol):
    def observe(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
```

- [ ] **Step 6: Run tests and verify green**

Run:

```powershell
python -m pytest planner/tests/test_runtime_models.py -q
python -m compileall -q planner/agent_runtime planner/skills/base.py
```

Expected: all model tests pass and compile exits 0.

- [ ] **Step 7: Commit Phase 1**

```powershell
git add -- planner/agent_runtime/__init__.py planner/agent_runtime/models.py planner/agent_runtime/state.py planner/skills/base.py planner/tests/test_runtime_models.py
git commit -m "feat: add typed agent runtime state"
```

## Task 3: Skill Contracts and Semantic Validation

**Files:**

- Create: `planner/agent_runtime/contracts.py`
- Create: `planner/agent_runtime/semantic_validator.py`
- Create: `planner/tests/test_semantic_validator.py`
- Modify: `planner/llm/schema.py`
- Modify: `planner/llm/prompt_builder.py`

- [ ] **Step 1: Write failing contract/semantic tests**

```python
def test_pick_without_localization_is_rejected():
    plan = MissionPlan.from_dict({"goal": {"type": "holding_object", "object": "cup"}, "steps": [
        {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
        {"id": "s2", "skill": "pick_object", "args": {"object": "cup"}, "depends_on": ["s1"]},
    ]})
    errors = SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"})
    assert any("ObjectLocalized(cup)" in error for error in errors)


def test_detect_then_pick_is_semantically_valid():
    plan = MissionPlan.from_dict({"goal": {"type": "holding_object", "object": "cup"}, "steps": [
        {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}},
        {"id": "s2", "skill": "pick_object", "args": {"object": "cup"}, "depends_on": ["s1"]},
    ]})
    assert SemanticPlanValidator(default_contracts()).validate(plan, {"HandEmpty"}) == []


def test_plan_cannot_override_runtime_policy():
    errors = validate_plan({"steps": [{
        "id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}, "max_retry": 99
    }]})
    assert any("runtime policy" in error for error in errors)
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_semantic_validator.py -q`.

Expected: missing contract and validator modules.

- [ ] **Step 3: Implement contracts**

Define immutable `SkillContract` with `required_args`, callable fact resolvers, timeout, attempts, retry mode, side-effect flag, verifier, and optional pose TTL. Add contracts for navigation, detection, pick, place, and explicit control skills. Use fact strings `At(value)`, `ObjectLocalized(value)`, `Holding(value)`, `Placed(value)`, and `HandEmpty`.

- [ ] **Step 4: Implement structural and symbolic validation**

Reject unknown skills, duplicate/missing IDs, non-dict args, unknown dependencies, dependencies that do not precede a step, runtime-policy keys, missing contract args, and absent required facts during symbolic simulation. Return deterministic human-readable error strings.

- [ ] **Step 5: Make LLM schema intent-only**

Update `validate_plan()` to parse through `MissionPlan`, invoke `SemanticPlanValidator`, and keep its `list[str]` compatibility. Update the prompt output schema to include `plan_id`, `version`, structured `goal`, steps, and dependencies; explicitly prohibit timeouts/retries/verifiers in output.

- [ ] **Step 6: Run tests and verify green**

Run `python -m pytest planner/tests/test_plan_validator.py planner/tests/test_semantic_validator.py -q`.

Expected: all tests pass.

- [ ] **Step 7: Commit Phase 2**

```powershell
git add -- planner/agent_runtime/contracts.py planner/agent_runtime/semantic_validator.py planner/llm/schema.py planner/llm/prompt_builder.py planner/tests/test_plan_validator.py planner/tests/test_semantic_validator.py
git commit -m "feat: validate plans against skill contracts"
```

## Task 4: Skill Executor and Independent Verifiers

**Files:**

- Create: `planner/agent_runtime/executor.py`
- Create: `planner/agent_runtime/verifiers.py`
- Create: `planner/tests/test_executor_and_verifiers.py`

- [ ] **Step 1: Write failing executor/verifier tests**

```python
def test_executor_timeout_of_side_effect_is_unknown():
    result = SkillExecutor().execute(
        SlowSkill(),
        SkillContract(name="slow", timeout_s=0.01, max_attempts=1,
                      retry_mode=RetryMode.VERIFY_BEFORE_RETRY,
                      side_effecting=True, verifier="always", required_args=()),
        {},
    )
    assert result.status is ExecStatus.UNKNOWN
    assert result.failure_code is FailureCode.PROTOCOL_ERROR


def test_navigation_command_acceptance_is_not_arrival():
    verification = NavigationVerifier().verify(
        step=navigate_step(), execution=SkillResult.succeeded({"command_accepted": True}),
        observation={"target": "pointb", "move_status": "moving", "running_status": "active"},
        state=WorldState(), now=10.0,
    )
    assert verification.status is VerificationStatus.FAILED


def test_perception_rejects_stale_pose():
    verification = PerceptionVerifier(pose_ttl_s=2.0).verify(
        step=detect_step("cup"), execution=SkillResult.succeeded(),
        observation={"object": "cup", "found": True, "pose": identity_pose(),
                     "frame_id": "camera", "timestamp": 7.0, "source": "mock"},
        state=WorldState(), now=10.0,
    )
    assert verification.failure_code is FailureCode.POSE_STALE


def test_grasp_insufficient_evidence_is_unknown():
    verification = GraspVerifier().verify(
        step=pick_step("cup"), execution=SkillResult.succeeded(), observation={},
        state=localized_state("cup"), now=10.0,
    )
    assert verification.status is VerificationStatus.UNKNOWN
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_executor_and_verifiers.py -q`.

Expected: missing executor/verifier modules.

- [ ] **Step 3: Implement `SkillExecutor`**

Use a one-worker `ThreadPoolExecutor`, `future.result(timeout=contract.timeout_s)`, non-waiting shutdown on timeout, and typed exception normalization. Return `UNKNOWN/PROTOCOL_ERROR` when a side-effecting call times out; return `TIMEOUT` for side-effect-free calls.

- [ ] **Step 4: Implement observation and verifier interfaces**

Add `SkillObservationProvider` that calls `skill.observe(**step.args)` when present and returns an empty observation otherwise. Implement `NavigationVerifier`, `PerceptionVerifier`, `GraspVerifier`, `PlaceVerifier`, `ControlVerifier`, `GoalVerifier`, and `VerifierRegistry`. Each returns structured state updates only in `VerificationResult.observations`; it does not mutate `WorldState`.

- [ ] **Step 5: Run tests and verify green**

Run `python -m pytest planner/tests/test_executor_and_verifiers.py -q`.

Expected: all tests pass without warnings.

- [ ] **Step 6: Commit Phase 3/4 foundations**

```powershell
git add -- planner/agent_runtime/executor.py planner/agent_runtime/verifiers.py planner/tests/test_executor_and_verifiers.py
git commit -m "feat: execute and verify robot skills independently"
```

## Task 5: Stateful Mock and Real Skill Adapter Semantics

**Files:**

- Create: `planner/skills/mock_backend.py`
- Modify: `planner/skills/navigation_skill.py`
- Modify: `planner/skills/perception_skill.py`
- Modify: `planner/skills/manipulation_skill.py`
- Modify: `planner/skills/human_skill.py`
- Modify: `planner/skills/registry.py`
- Modify: `planner/tests/test_phase0_regressions.py`

- [ ] **Step 1: Extend failing adapter tests**

```python
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
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_phase0_regressions.py -q`.

Expected: typed constructors/mock backend unavailable and old false-success behavior.

- [ ] **Step 3: Implement shared mock physical state**

`MockRobotBackend` stores location, localized object poses, held object, placed targets, a clock, and per-skill scripted result queues. Skill `run()` mutates mock physical state only when the scripted/current action succeeds; `observe()` reads it independently.

- [ ] **Step 4: Update navigation adapter**

For TCP/ROS, `run()` returns command acceptance only. `observe()` queries TCP robot status (using a factored status parser) or the available ROS status adapter. For mock, use `MockRobotBackend`. Prototype-only locate/path/align skills return `REJECTED/UNAVAILABLE` until connected.

- [ ] **Step 5: Update perception/manipulation adapters**

Detection with no configured real pose returns `REJECTED/PERCEPTION_UNAVAILABLE`; loaded pose observations include file modification time, frame, source, optional confidence, and validity. Pick/place return typed results and expose held/placed evidence through mock observation; real evidence remains unknown when current hardware APIs cannot prove it.

- [ ] **Step 6: Update human/control results and registry**

`ask_human` returns `REJECTED/PRECONDITION_FAILED`; `abort` returns `CANCELLED`. `build_default_skill_registry()` creates one shared mock backend and passes it to core skills.

- [ ] **Step 7: Complete Phase 0 implementation and run tests**

Use `_extract_machine_result()` in `_run_right_arm_grasp`. Run:

```powershell
python -m pytest planner/tests/test_phase0_regressions.py planner/tests/test_executor_and_verifiers.py -q
```

Expected: all Phase 0 and adapter tests pass.

- [ ] **Step 8: Commit adapter migration**

```powershell
git add -- planner/skills planner/examples/run_long_task.py planner/examples/run_nav_grasp_json.py planner/tests/test_phase0_regressions.py
git commit -m "fix: eliminate planner false-success paths"
```

## Task 6: Recovery Policy and Mission Budgets

**Files:**

- Create: `planner/agent_runtime/recovery.py`
- Create: `planner/tests/test_recovery_and_replanner.py`

- [ ] **Step 1: Write failing recovery tests**

```python
def test_unknown_side_effect_never_blind_retries():
    decision = RecoveryPolicy().decide(
        pick_contract(), FailureReport(code=FailureCode.GRASP_AMBIGUOUS, attempts=1),
        VerificationResult.unknown(FailureCode.GRASP_AMBIGUOUS), BudgetTracker(default_budgets()),
    )
    assert decision.action is RecoveryAction.REPLAN


def test_stale_pose_runs_deterministic_perception_recovery():
    decision = RecoveryPolicy().decide(
        pick_contract(), FailureReport(code=FailureCode.POSE_STALE, attempts=0, args={"object": "cup"}),
        VerificationResult.failed(FailureCode.POSE_STALE), BudgetTracker(default_budgets()),
    )
    assert decision.action is RecoveryAction.RUN_SKILL
    assert decision.skill == "detect_object"
    assert decision.args == {"object": "cup"}


def test_repeated_failure_same_state_escalates():
    tracker = FailureLoopDetector(threshold=3)
    for _ in range(2):
        assert not tracker.record("pick_object", {"object": "cup"}, FailureCode.GRASP_FAILED, "same")
    assert tracker.record("pick_object", {"object": "cup"}, FailureCode.GRASP_FAILED, "same")
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_recovery_and_replanner.py -q`.

Expected: recovery module missing.

- [ ] **Step 3: Implement recovery decisions and counters**

Define `RecoveryAction` (`RETRY`, `REOBSERVE`, `RUN_SKILL`, `REPLAN`, `ABORT`), `RecoveryDecision`, `BudgetTracker`, and `FailureLoopDetector`. Map object-not-found to bounded retry, stale pose and definite grasp failure to `detect_object` recovery, ambiguity to replan, and safety/budget failures to abort.

- [ ] **Step 4: Run focused tests and commit**

Run `python -m pytest planner/tests/test_recovery_and_replanner.py -q` and commit:

```powershell
git add -- planner/agent_runtime/recovery.py planner/tests/test_recovery_and_replanner.py
git commit -m "feat: add bounded hierarchical recovery"
```

## Task 7: State-Grounded Suffix Replanning

**Files:**

- Create: `planner/agent_runtime/replanner.py`
- Modify: `planner/llm/prompt_builder.py`
- Modify: `planner/llm/qwen_client.py`
- Modify: `planner/tests/test_recovery_and_replanner.py`

- [ ] **Step 1: Add failing suffix-repair tests**

```python
def test_replan_keeps_committed_prefix_immutable():
    original = mission_plan_with_steps("s1", "s2", "s3")
    repaired = apply_repaired_suffix(
        original=original,
        committed_steps=[original.steps[0]],
        returned_steps=[{"id": "s2r", "skill": "detect_object", "args": {"object": "cup"}},
                        {"id": "s3r", "skill": "pick_object", "args": {"object": "cup"},
                         "depends_on": ["s2r"]}],
        state=WorldState(facts={"HandEmpty", "At(pointb)"}),
        contracts=default_contracts(),
    )
    assert repaired.version == original.version + 1
    assert repaired.parent_version == original.version
    assert [step.id for step in repaired.steps] == ["s2r", "s3r"]


def test_replan_rejects_committed_step_id_reuse():
    original = MissionPlan.from_dict({
        "plan_id": "p1", "version": 1,
        "goal": {"type": "holding_object", "object": "cup"},
        "steps": [
            {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
            {"id": "s2", "skill": "detect_object", "args": {"object": "cup"},
             "depends_on": ["s1"]},
            {"id": "s3", "skill": "pick_object", "args": {"object": "cup"},
             "depends_on": ["s2"]},
        ],
    })
    with pytest.raises(ReplanError, match="committed"):
        apply_repaired_suffix(
            original=original,
            committed_steps=[original.steps[0]],
            returned_steps=[
                {"id": "s1", "skill": "detect_object", "args": {"object": "cup"}}
            ],
            state=WorldState(facts={"HandEmpty", "At(pointb)"}),
            contracts=default_contracts(),
        )
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_recovery_and_replanner.py -q`.

Expected: replanner module missing.

- [ ] **Step 3: Implement replanner protocol and suffix guardrails**

Add `Replanner` protocol, `NoOpReplanner`, `QwenReplanner`, `ReplanError`, compact context serialization, and `apply_repaired_suffix()`. Validate unique IDs, committed-ID exclusion, structured goal equality, version lineage, and semantic validity from current committed facts.

- [ ] **Step 4: Add Qwen text repair transport**

Add `build_replan_prompt()` and `QwenPlannerClient.replan_remaining(context)`. The model output is strict JSON containing only a `steps` array. Reuse `_post_chat_completion`; do not create a second HTTP client.

- [ ] **Step 5: Run tests and commit Phase 6**

Run `python -m pytest planner/tests/test_recovery_and_replanner.py -q` and commit:

```powershell
git add -- planner/agent_runtime/replanner.py planner/llm/prompt_builder.py planner/llm/qwen_client.py planner/tests/test_recovery_and_replanner.py
git commit -m "feat: repair only uncommitted plan suffixes"
```

## Task 8: Structured JSONL Trajectory

**Files:**

- Create: `planner/agent_runtime/trace.py`
- Create: `planner/tests/test_trace.py`

- [ ] **Step 1: Write failing trace test**

```python
def test_trace_is_flush_safe_and_json_serializable(tmp_path):
    path = tmp_path / "mission.jsonl"
    with JsonlTraceWriter(path, mission_id="m1", clock=lambda: 12.5) as trace:
        trace.record("execute_finished", plan_id="p1", plan_version=1, step_id="s1",
                     attempt=1, skill="navigate_to",
                     result=SkillResult.succeeded({"accepted": True}),
                     state=WorldState())
        assert path.read_text(encoding="utf-8").endswith("\n")
    event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert event["timestamp"] == 12.5
    assert event["mission_id"] == "m1"
    assert event["result"]["status"] == "succeeded"
    assert event["state_hash"]
```

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_trace.py -q`.

Expected: trace module missing.

- [ ] **Step 3: Implement canonical event serialization**

Open the path in append text mode, create parents, serialize dataclasses/enums/sets recursively, add mission/timestamp/event fields, include state snapshot/hash when supplied, write one compact JSON object plus newline, and flush after every event.

- [ ] **Step 4: Run and commit Phase 7 foundation**

Run `python -m pytest planner/tests/test_trace.py -q` and commit:

```powershell
git add -- planner/agent_runtime/trace.py planner/tests/test_trace.py
git commit -m "feat: record replayable mission trajectories"
```

## Task 9: AgentRuntime State Machine

**Files:**

- Create: `planner/agent_runtime/runtime.py`
- Create: `planner/tests/conftest.py`
- Create: `planner/tests/test_agent_runtime.py`
- Modify: `planner/agent_runtime/__init__.py`

- [ ] **Step 1: Write the failed-verification commit test**

```python
def test_failed_verification_does_not_commit(runtime_factory):
    runtime, state = runtime_factory(
        plan=single_nav_plan(),
        scripts={"navigate_to": [SkillResult.succeeded()]},
        observations={"navigate_to": [{"target": "pointb", "move_status": "failed"}]},
        replanner=NoOpReplanner(),
    )
    result = runtime.run()
    assert result.status is MissionStatus.ABORTED
    assert state.completed_steps == []
    assert "At(pointb)" not in state.facts
```

- [ ] **Step 2: Write budget and final-goal tests**

```python
def test_retry_budget_prevents_loop(runtime_factory):
    runtime, _ = runtime_factory(
        plan=single_detect_plan(),
        scripts={"detect_object": [SkillResult.failed(FailureCode.OBJECT_NOT_FOUND)] * 10},
        budgets=MissionBudgets(max_total_actions=3, max_replans=0),
    )
    result = runtime.run()
    assert result.status is MissionStatus.ABORTED
    assert result.total_actions <= 3


def test_final_goal_must_be_verified(runtime_factory):
    runtime, state = runtime_factory(plan=single_pick_plan(), goal_observation={"holding_object": None})
    result = runtime.run()
    assert result.status is MissionStatus.ABORTED
    assert result.failure.code is FailureCode.GOAL_NOT_SATISFIED
```

- [ ] **Step 3: Write the complete fault-injection episode first**

Create a plan `navigate(pointb) -> detect(cup) -> pick(cup) -> navigate(pointa)` and scripted adapters where detection fails once then succeeds, pick fails once, deterministic detect recovery succeeds, pick succeeds, return navigation succeeds, and goal observation reports holding `cup`. Assert `MissionStatus.SUCCEEDED`, all plan step IDs committed once, at least one recovery event, zero committed effects from failed attempts, and a parseable trajectory.

- [ ] **Step 4: Run and verify red**

Run `python -m pytest planner/tests/test_agent_runtime.py -q`.

Expected: runtime module missing.

- [ ] **Step 5: Implement the orchestrator in small methods**

`AgentRuntime.run()` performs validation and drives explicit phase transitions. Keep separate methods `_precheck`, `_execute_and_verify`, `_commit`, `_recover`, `_run_recovery_skill`, `_replan`, `_verify_goal`, `_check_mission_budget`, and `_abort`. Inject state, contracts, skill registry, executor, observation provider, verifiers, recovery policy, replanner, trace, monotonic clock, and wall clock.

Required semantics:

```python
if verification.status is VerificationStatus.VERIFIED:
    self._commit(step, contract, verification)
elif self._recovery_can_continue(step, contract, failure, verification):
    self._recover(step, contract, failure, verification)
else:
    return self._abort(failure)
```

Only `_commit()` calls `WorldState.commit()`. Count every physical/recovery skill execution against `max_total_actions`. Check deadline before every action and replan. Record every state transition.

- [ ] **Step 6: Run focused tests and verify green**

Run:

```powershell
python -m pytest planner/tests/test_agent_runtime.py -q
python -m pytest planner/tests/test_recovery_and_replanner.py planner/tests/test_trace.py -q
```

Expected: all runtime/recovery/trace tests pass.

- [ ] **Step 7: Commit the closed-loop runtime**

```powershell
git add -- planner/agent_runtime/__init__.py planner/agent_runtime/runtime.py planner/tests/conftest.py planner/tests/test_agent_runtime.py
git commit -m "feat: run missions through verified closed loop"
```

## Task 10: Sole CLI Migration and Legacy Removal

**Files:**

- Modify: `planner/examples/run_long_task.py`
- Modify: `planner/examples/run_full_mock_demo.py`
- Modify: `planner/skills/registry.py`
- Delete: `planner/executor/task_executor.py`
- Delete: `planner/executor/__init__.py`
- Delete: `planner/examples/run_executor_demo.py`
- Modify: `planner/tests/test_agent_runtime.py`

- [ ] **Step 1: Add failing CLI construction test**

Test a `build_runtime(plan, args, *, trace_path, planner_client=None)` helper with mock backends and a temporary trace path. Assert it returns `AgentRuntime`, supplies default budgets, and never imports/references `TaskExecutor`. Add an AST/text assertion that `run_long_task.py` contains no `legacy` runtime option.

- [ ] **Step 2: Run and verify red**

Run `python -m pytest planner/tests/test_agent_runtime.py -q`.

Expected: `build_runtime` absent and current entry point imports `TaskExecutor`.

- [ ] **Step 3: Migrate the CLI**

Add flags `--mission-timeout`, `--max-total-actions`, `--max-replans`, `--failure-repeat-threshold`, and `--trajectory`. Parse the Qwen result as `MissionPlan`, construct state/contracts/registry/verifiers/recovery/replanner/trace, run AgentRuntime, and save a JSON-safe `MissionResult`. Use Qwen replanning only when an API key exists; otherwise use `NoOpReplanner` and abort cleanly after deterministic recovery.

- [ ] **Step 4: Migrate full mock demo and remove legacy files**

Route `run_full_mock_demo.py` through the same construction helper. Delete the executor package files and `run_executor_demo.py`. Search for stale references:

```powershell
rg -n "TaskExecutor|planner\.executor|--runtime legacy" planner
```

Expected: only historical design/plan documentation mentions remain.

- [ ] **Step 5: Run migration tests and commit**

Run:

```powershell
python -m pytest planner/tests -q
python -m compileall -q planner
```

Expected: all tests pass and compile exits 0.

Commit only migrated paths:

```powershell
git add -- planner/examples/run_long_task.py planner/examples/run_full_mock_demo.py planner/skills/registry.py planner/tests/test_agent_runtime.py planner/executor planner/examples/run_executor_demo.py
git commit -m "refactor: replace legacy executor with agent runtime"
```

## Task 11: Documentation, Full Verification, and Rollback Ledger

**Files:**

- Modify: `planner/README.md`
- Modify: `planner/README.zh-CN.md`
- Create: `planner/docs/agent-runtime-rollout.md`

- [ ] **Step 1: Update operator documentation**

Document the only runtime path, mock and real adapter modes, typed outcomes, verified commits, budgets, JSONL trajectory location, Qwen suffix replanning behavior, and the explicit statement that physical hardware verification is deferred.

- [ ] **Step 2: Add the rollback ledger**

Record the feature branch, design commit, plan commit, every implementation phase commit, files deleted, default CLI changes, known hardware-integration gaps, and commands for inspecting or reverting a single phase with `git revert <commit>`.

- [ ] **Step 3: Run fresh complete verification**

Run all of:

```powershell
python -m pytest planner/tests -q
python -m compileall -q planner
git diff --check HEAD
rg -n "TaskExecutor|planner\.executor|SkillResult\(ok=" planner --glob '!docs/**'
```

Expected:

- pytest exits 0 with no failures;
- compileall exits 0;
- diff check emits no errors;
- stale runtime/legacy result patterns have no code matches.

- [ ] **Step 4: Review acceptance requirements line by line**

Confirm the test names cover marker preservation, arrival verification, unavailable skills, missing/stale pose, semantic rejection, unknown side effects, failed verification/no commit, suffix-only replan, all budgets, final goal verification, mixed stdout JSON, trace validity, and the full recovery episode. Record any deferred item only if it requires physical hardware.

- [ ] **Step 5: Commit documentation and final verified state**

```powershell
git add -- planner/README.md planner/README.zh-CN.md planner/docs/agent-runtime-rollout.md
git commit -m "docs: document agent runtime rollout and rollback"
```

Do not stage unrelated repository changes. Re-run `git status --short` and list the feature's commits with:

```powershell
git log --oneline --decorate main..feat/closed-loop-agent-runtime
```
