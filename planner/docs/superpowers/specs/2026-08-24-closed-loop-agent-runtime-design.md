# Closed-Loop Agent Runtime Design

## Objective

Replace the planner's one-shot `TaskExecutor` execution path with a single,
general closed-loop `AgentRuntime` for long-sequence robot tasks. The first
delivery is accepted against deterministic mock episodes and failure injection;
real chassis, perception, and manipulation adapters remain compatible for later
hardware integration.

The runtime must implement contract-grounded execution, verified state
transitions, hierarchical recovery, state-grounded suffix replanning, bounded
execution, and replayable JSONL trajectories.

## Scope

The implementation covers Phase 0 through Phase 7 from the supplied system
proposal:

1. Correct known false-success and plan-patching bugs.
2. Introduce typed runtime results and world state.
3. Define skill contracts and semantic plan validation.
4. Implement the explicit closed-loop runtime state machine.
5. Add independent skill and goal verifiers.
6. Add deterministic recovery, budgets, and loop detection.
7. Add state-grounded remaining-plan repair.
8. Record structured JSONL trajectories and support replay-oriented testing.

The old `planner/executor/task_executor.py` path and its executor-only demo will
be removed. `AgentRuntime` becomes the only execution architecture. Existing
navigation, FoundationPose, arm, hand, ROS, and TCP implementations are not
rewritten; they remain behind skill and observation adapters.

## Non-Goals

- No LangGraph, AutoGen, CrewAI, MCP migration, multi-agent system, MCTS, or
  agentic reinforcement learning.
- No rewrite of navigation, FoundationPose, RM65, gripper, or camera stacks.
- No hardware acceptance test in this delivery.
- No LLM-defined timeout, retry, verifier, recovery, or safety policy.
- No full DAG scheduler. Plans remain ordered steps with validated dependencies.
- No fabricated confidence values or success from unavailable hardware.

## Architecture

```text
Qwen Planner
    |
    v
Mission Plan (intent only)
    |
    v
Schema Validation + Contract Semantic Dry-Run
    |
    v
AgentRuntime
    PRECHECK -> EXECUTE -> OBSERVE/VERIFY -> COMMIT
                      |          |
                      +---- failure ----+
                                       v
                             deterministic recovery
                                       |
                              bounded safe retry
                                       |
                              suffix-only replan
                                       |
                                  ABORT/HUMAN
```

`AgentRuntime` knows contracts and abstract skill, observation, verifier,
replanner, clock, and trace interfaces. It does not know ROS topics, TCP
payloads, FoundationPose file formats, or arm controller details.

## Package Layout

```text
planner/
  agent_runtime/
    __init__.py
    models.py
    state.py
    contracts.py
    semantic_validator.py
    executor.py
    verifiers.py
    recovery.py
    replanner.py
    trace.py
    runtime.py
  skills/
    base.py
    registry.py
    navigation_skill.py
    perception_skill.py
    manipulation_skill.py
    human_skill.py
  llm/
    qwen_client.py
    prompt_builder.py
    schema.py
  examples/
    run_long_task.py
  tests/
    ...
```

Responsibilities are intentionally narrow:

- `models.py`: immutable/shared plan and execution value types.
- `state.py`: verified world state, symbolic facts, snapshots, and stable hashes.
- `contracts.py`: trusted runtime policy and built-in skill contracts.
- `semantic_validator.py`: structural validation and symbolic plan simulation.
- `executor.py`: bounded skill invocation and exception/result normalization.
- `verifiers.py`: postcondition evidence evaluation and final goal verification.
- `recovery.py`: deterministic decisions, budgets, and repeated-failure checks.
- `replanner.py`: compact context construction and Qwen/mock suffix repair.
- `trace.py`: append-only JSONL runtime events.
- `runtime.py`: state-machine orchestration only.

## Mission Plan

The plan expresses intent, not runtime policy:

```json
{
  "plan_id": "p001",
  "version": 1,
  "parent_version": null,
  "goal": {"type": "holding_object", "object": "glasses_case_box"},
  "steps": [
    {"id": "s1", "skill": "navigate_to", "args": {"target": "pointb"}},
    {
      "id": "s2",
      "skill": "detect_object",
      "args": {"object": "glasses_case_box"},
      "depends_on": ["s1"]
    }
  ]
}
```

Plans cannot override contract timeouts, retry modes, attempt budgets,
verifiers, or safety behavior. Replanning increments `version`, records
`parent_version`, preserves committed history, and replaces only the uncommitted
suffix.

## Typed Runtime Data

`ExecStatus` contains `SUCCEEDED`, `FAILED`, `UNKNOWN`, `REJECTED`, `TIMEOUT`,
and `CANCELLED`.

`SkillResult` contains status, data, optional `FailureCode`, a retryability hint,
and a message. A read-only `ok` property is retained for adapter convenience,
but the runtime branches on the full status.

`VerificationResult` contains a verification status (`VERIFIED`, `FAILED`, or
`UNKNOWN`), optional confidence, optional failure code, observations, and a
message. Execution results and verification evidence remain separate.

`WorldState` is the only runtime fact source. It records location, robot pose,
object states, held object, symbolic facts, committed step IDs, last failure,
and revision. Object poses include value, frame, timestamp, source, optional
confidence, and validity. Confidence remains `None` when the adapter cannot
provide a meaningful value.

## Skill Contracts

Each contract defines:

- name and argument validation;
- timeout and maximum attempts;
- retry mode: `SAFE`, `VERIFY_BEFORE_RETRY`, or `NEVER`;
- whether execution has physical side effects;
- required facts;
- produced and invalidated facts;
- verifier name.

The first contract set covers `navigate_to`, `detect_object`, `pick_object`, and
`place_object`. Human/abort behavior remains explicit control flow rather than a
fake successful physical action.

Semantic validation performs a symbolic dry-run from declared initial facts.
For example, `pick_object(cup)` is rejected if no preceding step can establish
`ObjectLocalized(cup)` and `HandEmpty`.

## Runtime State Machine

The explicit mission states are `PRECHECK`, `EXECUTE`, `VERIFY`, `COMMIT`,
`RECOVER`, `REPLAN`, `DONE`, and `ABORT`.

For every step:

1. `PRECHECK` verifies dependencies, arguments, required committed facts, safety
   constraints, and pose freshness.
2. `EXECUTE` invokes the skill through the executor, applying a contract timeout
   and mapping exceptions/protocol ambiguity to typed results.
3. `VERIFY` obtains independent observations and evaluates the contract's
   postconditions.
4. `COMMIT` atomically applies produced/invalidated facts and structured state
   updates, then records the step as completed.

A successful skill return never commits a step by itself. A failed or unknown
verification never updates planned effects. After all steps commit, a separate
`GoalVerifier` re-observes the goal predicate; mission success requires that
final verification.

## Verification

- `NavigationVerifier` requires evidence that the requested target was reached
  and the platform is no longer active. Command acceptance alone is insufficient.
- `PerceptionVerifier` checks object pose presence, shape, frame, validity, and
  freshness. It does not impose a confidence threshold when confidence is absent.
- `GraspVerifier` distinguishes arm trajectory completion from evidence that the
  object is held. Insufficient evidence returns `UNKNOWN`.
- `PlaceVerifier` requires evidence that the held-object predicate was cleared
  and the target placement predicate was established.
- `GoalVerifier` evaluates structured goal predicates against a fresh observation
  and the verified world state.

Verifiers use injected observation providers, allowing identical runtime logic
for scripted mocks and later real robot status sources.

## Recovery and Safety

Recovery is hierarchical:

1. Re-observe and verify ambiguous physical state.
2. Apply deterministic failure-specific recovery such as re-perception.
3. Retry only when the contract mode and remaining budget permit it.
4. Invoke the replanner after local recovery is exhausted.
5. Abort or request human action for safety violations, exhausted mission
   budgets, or irreducible ambiguity.

`UNKNOWN` from a side-effecting skill cannot be retried until observation proves
the retry is safe. Safety violations are never blind-retried.

The runtime enforces mission deadline, maximum total actions, maximum replans,
per-step attempts, and repeated-failure thresholds. Repetition is keyed by
`(skill, normalized_args, failure_code, world_state_hash)`. Crossing the
threshold escalates instead of looping.

## Replanning

The replanner receives only:

- original structured goal;
- compact verified world state;
- immutable committed steps;
- remaining plan;
- structured current failure;
- available skill contracts.

It never receives the entire stdout or chat history. Qwen plan repair reuses the
existing client transport. A deterministic scripted replanner is injected in
tests. Every repaired suffix passes structural and semantic validation before
execution. A repair that repeats committed effects, changes the committed
prefix, or exceeds budgets is rejected.

## Trace and Rollback Records

Every significant transition appends a JSON object to a mission trajectory.
Events contain timestamp, mission ID, plan ID/version, step ID, attempt,
event type, skill, execution result, verification result, recovery decision,
and compact state snapshot/hash as applicable.

Writes are flush-on-event and machine-readable even after interruption. Default
runtime output lives under `runtime/trajectories/`, configurable from the CLI.
Tests use temporary paths.

Implementation work occurs on `feat/closed-loop-agent-runtime`. The design,
implementation plan, and each phase are committed separately with only relevant
paths staged. Existing unrelated and hardware-related working-tree changes are
not included. This yields explicit rollback points without discarding current
user work.

## CLI and Compatibility

`examples/run_long_task.py` becomes the sole primary entry point and always uses
`AgentRuntime`. There is no `--runtime legacy` mode. It supports real or mock
skill adapters, mission budgets, trajectory output, saved plan/result, and
injected test configuration.

The explicit-marker patch may modify matching `navigate_to` arguments but must
not replace or truncate remaining plan steps. Prototype or unconnected skills
return `REJECTED/UNAVAILABLE`. Missing perception pose returns failure rather
than success. Navigation adapters separate command acceptance from arrival
observation.

The obsolete `TaskExecutor` and executor-only demo are removed after the new
entry point and tests use `AgentRuntime`.

## Test Strategy and Acceptance

All behavioral changes follow red-green-refactor. Tests are deterministic and do
not require network, ROS, a chassis, a camera, or an arm.

Required regression and unit coverage includes:

- explicit-marker patch preserves all remaining steps;
- navigation does not succeed before arrival verification;
- unconnected prototype skills cannot report success;
- detection without a valid pose fails;
- semantic validation rejects pick without localization;
- stale object pose blocks pick;
- unknown side effects require observation before retry;
- failed verification cannot commit;
- replan preserves the committed prefix and only replaces the suffix;
- retry/action/replan/deadline budgets prevent loops;
- final mission success requires goal verification;
- mixed subprocess logs cannot corrupt the machine result protocol;
- every important state transition produces a valid JSONL trace event.

At least one complete scripted episode must demonstrate:

```text
navigate success
-> perception fails once
-> deterministic re-observation/retry
-> perception succeeds
-> grasp fails once
-> re-perception and safe retry
-> grasp succeeds
-> navigation succeeds
-> final goal verification succeeds
-> MISSION_SUCCEEDED
```

Additional episodes cover stale pose, navigation timeout, protocol ambiguity,
ambiguous grasp, repeated failure, invalid replan, and final goal failure.

Acceptance requires the complete planner test suite and Python compile check to
pass on the mock environment. Hardware behavior is explicitly deferred to a
later integration session, using the preserved adapters and recorded traces.

