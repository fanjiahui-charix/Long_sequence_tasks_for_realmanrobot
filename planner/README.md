# Closed-Loop Planner and Agent Runtime

[English](./README.md) | [简体中文](./README.zh-CN.md)

`planner/` turns a structured mission into verified robot state transitions. It
uses one execution architecture: `AgentRuntime`. A skill returning success is
not enough to complete a step; the runtime observes the world, verifies the
contract postcondition, and commits the effect only after verification.

## Execution Model

```text
Qwen mission plan (intent only)
        |
schema + contract semantic validation
        |
PRECHECK -> EXECUTE -> OBSERVE/VERIFY -> COMMIT
                    |        failure
                    v
       deterministic recovery -> bounded retry
                    |
       verified-state suffix replanning
                    |
                ABORT/HUMAN
```

Runtime safety policy is code-owned. Qwen cannot define timeouts, retry budgets,
verifiers, recovery actions, or safety thresholds.

## Main Components

- `agent_runtime/models.py`: typed execution, verification, failure, plan, and
  mission results.
- `agent_runtime/state.py`: timestamped object state and the verified
  `WorldState` fact source.
- `agent_runtime/contracts.py`: trusted preconditions, effects, retry modes,
  timeouts, and verifiers.
- `agent_runtime/semantic_validator.py`: symbolic dry-run before execution.
- `agent_runtime/executor.py`: bounded skill invocation and result normalization.
- `agent_runtime/verifiers.py`: independent navigation, perception, grasp,
  placement, and final-goal verification.
- `agent_runtime/recovery.py`: deterministic recovery, attempt limits, mission
  budgets, and repeated-failure detection.
- `agent_runtime/replanner.py`: Qwen repair of the uncommitted suffix only.
- `agent_runtime/trace.py`: flush-on-event JSONL trajectories.
- `agent_runtime/runtime.py`: the explicit runtime state machine.
- `skills/`: mock, TCP, ROS, FoundationPose, and manipulation adapters.

The former `TaskExecutor` path has been removed.

## Mock Acceptance

The deterministic suite requires no network, ROS, camera, chassis, or arm:

```powershell
python -m pytest planner/tests -q
python -m compileall -q planner
```

It covers navigation arrival verification, missing and stale poses, ambiguous
physical outcomes, verified commits, deterministic recovery, suffix repair,
loop budgets, final-goal verification, JSON protocol extraction, trajectory
events, and a complete injected-failure episode.

## Run a Mission

Generate a plan with Qwen and run all adapters in mock mode:

```bash
python3 planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointb, pick the glasses case, and return to pointa" \
  --nav-backend mock \
  --perception-backend mock \
  --manipulation-backend mock \
  --trajectory runtime/trajectories/mock-mission.jsonl
```

Real adapter selection for the later hardware session:

```bash
python3 planner/examples/run_long_task.py \
  --camera-name camera_middle \
  --task "go to pointb and pick the glasses case" \
  --nav-backend tcp \
  --perception-backend foundationpose \
  --manipulation-backend ros \
  --pick-mode pose_grasp
```

Important mission limits:

- `--mission-timeout` (default `900` seconds)
- `--max-total-actions` (default `50`)
- `--max-replans` (default `3`)
- `--failure-repeat-threshold` (default `3`)
- `--trajectory` for an explicit JSONL output path

If no Qwen API key is available, the runtime still performs deterministic local
recovery but aborts cleanly when an LLM suffix repair is required.

## Verified State Rules

- `SkillResult` reports what the executor knows about command execution.
- `VerificationResult` reports whether observed reality satisfies the expected
  postcondition.
- `WorldState` changes only through verified commit.
- Object poses carry frame, timestamp, source, validity, and optional confidence.
- A side-effecting `UNKNOWN` cannot be blindly retried.
- Replanning cannot change committed steps or repeat committed step IDs.
- Mission success requires a fresh final-goal observation.

## Trajectory Records

Each JSONL event may include mission/plan version, step, attempt, phase, skill
result, verification evidence, recovery decision, and the verified state
snapshot/hash. Events are flushed immediately and remain parseable after an
interruption. The default directory is `runtime/trajectories/`.

## Hardware Integration Status

This delivery is accepted against the complete Mock fault-injection loop. TCP
navigation exposes real status observations. The ROS navigation status adapter
and real grasp/place evidence adapters intentionally return insufficient
evidence until they are connected during the physical robot session; they do
not fabricate success.

See [agent-runtime-rollout.md](./docs/agent-runtime-rollout.md) for phase commits,
rollback commands, and the hardware integration checklist.
