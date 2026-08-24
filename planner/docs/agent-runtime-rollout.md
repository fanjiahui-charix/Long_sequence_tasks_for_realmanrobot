# Agent Runtime Rollout and Rollback Ledger

## Delivery Baseline

- Design branch: `feat/closed-loop-agent-runtime`
- Implementation branch: `feat/closed-loop-agent-runtime-impl`
- Acceptance target: deterministic complete Mock fault-injection loop
- Deferred target: physical chassis, camera, arm, and hand integration
- Only execution path: `planner.agent_runtime.AgentRuntime`

The implementation branch was created from the approved design and plan commits.
Only explicit planner paths were staged for phase commits. Unrelated working-tree
changes and Windows worktree checkout artifacts were not included.

## Phase Commits

| Commit | Rollback boundary |
| --- | --- |
| `eb1f25c` | Approved architecture and acceptance design |
| `1aa9b3b` | Test-driven Phase 0–7 implementation plan |
| `13c2f60` | False-success regression RED checkpoint |
| `8f5b6bb` | Typed results and verified world state |
| `d428a71` | Skill contracts and semantic plan dry-run |
| `22bd229` | Timeout-aware executor and independent verifiers |
| `29a667a` | False-success fixes and stateful Mock adapters |
| `eacc650` | Hierarchical recovery and mission budgets |
| `2fd9393` | State-grounded suffix-only replanning |
| `73d5a19` | Flush-safe JSONL trajectories |
| `9093a2d` | Closed-loop AgentRuntime state machine |
| `dfb8b0b` | Sole CLI migration and legacy executor removal |
| `b1ba4c5` | Stale-pose and explicit-marker acceptance closure |
| `2869323` | Verified held-object requirement for placement |
| `d537c3c` | Operator documentation and rollback ledger |
| `2e9437b` | Mixed-log grasp runner machine-result integration |

Inspect the exact sequence with:

```powershell
git log --oneline --decorate eb1f25c..feat/closed-loop-agent-runtime
```

## Rollback

Rollback one phase while preserving later history:

```powershell
git revert <phase-commit>
```

Create an inspection branch at a known boundary:

```powershell
git switch -c inspect/pre-runtime 73d5a19
```

Return to the approved design/plan baseline without changing existing branches:

```powershell
git switch -c rollback/agent-runtime-plan 1aa9b3b
```

Do not use `git reset --hard` in the original working tree because it contains
unrelated, uncommitted robot integration work.

## Behavioral Changes

- `TaskExecutor` and `run_executor_demo.py` were removed.
- `run_long_task.py` always builds `AgentRuntime`.
- Explicit marker correction updates navigation arguments but never truncates
  perception/manipulation steps.
- Prototype and unavailable skills return typed rejection instead of success.
- TCP navigation command acceptance is separated from arrival verification.
- Missing/stale perception and insufficient grasp/place evidence cannot commit.
- Replanning replaces only the uncommitted suffix and increments plan version.
- Final mission success requires a fresh goal observation.

## Hardware Integration Checklist

The Mock acceptance suite is complete. During the physical session:

1. Verify TCP `robot_status` keys and arrival states against the deployed chassis
   firmware.
2. Implement the ROS navigation `observe()` status adapter if ROS navigation is
   used instead of TCP.
3. Confirm FoundationPose result timestamps and camera frames; the file adapter
   currently uses result-file modification time.
4. Connect real gripper/hand or visual evidence to `PickObjectSkill.observe()`.
5. Connect real release/placement evidence to `PlaceObjectSkill.observe()`.
6. Run with conservative action/replan budgets and inspect the JSONL trajectory
   after every episode.
7. Add each hardware-discovered failure as a failing Mock regression before
   changing recovery policy.

Until evidence adapters are connected, real grasp/place verification returns
insufficient evidence and prevents a false mission success.

## Verification Commands

```powershell
python -m pytest planner/tests -q
python -m compileall -q planner
git diff --check HEAD
rg -n "TaskExecutor|planner\.executor|SkillResult\(ok=" planner --glob "*.py"
```

The final command may match assertions in tests that explicitly ensure the old
patterns are absent; it must not match production modules.
