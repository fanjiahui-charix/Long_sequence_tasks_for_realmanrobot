# ReAct + Memory Robot Agent V1

## Architecture

A single agent chooses one high-level action per turn. It never emits trajectories, joint angles, velocity, forces, calibration or executable commands. The old planner/runtime is removed without a compatibility path.

```mermaid
flowchart TD
    U[Instruction + annotated image] --> M[Qwen vision: MissionDraft]
    M --> MS[Validated MissionSpec]
    T[Trusted operator marker mapping] --> MS
    MS --> A[Single ReAct decision]
    W[Working Memory] --> A
    E[SQLite verified recovery episodes] --> A
    A --> R[Typed Tool Registry]
    R --> X[Fresh precheck / execution / timeout]
    X --> B[Platform-neutral RobotBackend]
    B --> N[Navigation]
    B --> P[RGB-D / segmentation / FoundationPose / TF]
    B --> G[Grasp / actual state reader]
    N --> O[Independent Observation]
    P --> O
    G --> O
    O --> V[Deterministic Verifier]
    V --> W
    V --> E
    A --> F[FINISH requests fresh feedback]
    F --> C{At A AND holding target?}
    C -->|both verified| D[COMPLETED]
    C -->|false or unknown| A
```

| Module | Responsibility |
|---|---|
| schemas.py / mission.py | Pydantic contracts, image-grounded mission facts, immutable success rules and trusted mapping |
| llm_adapter.py / prompts | Qwen-compatible HTTP, optional compatible/Ollama transports, server JSON mode and mandatory local schema validation |
| agent.py | One decision → one tool → observation → state/memory update → next decision |
| tool_registry.py / executor.py | Argument allowlists, preconditions, fresh execution-boundary telemetry, deadlines and cancellation |
| deadlines.py | Cancellation-preserving deadline waits across Python 3.10+, including simultaneous completion/cancel races |
| state.py | Current mission/location/object/pose/holding state, actions, errors, retries, motion epoch and uncertainty latch |
| verifier.py | Deterministic navigation, perception, measured-width and final-goal checks |
| memory/episodic.py | SQLite filtering, event/state persistence and verified recovery promotion |
| backends/base.py | RobotBackend protocol with no ROS/CUDA imports |
| adapters / hardware_worker.py | Optional existing RealMan capabilities across their existing interpreters |
| trace.py / evaluation.py | Structured traces, metrics and A/B API-level evaluation |

## Decisions and tools

AgentDecision is CALL_TOOL, FINISH, ABORT or REQUEST_HELP, with a short decision summary. A CALL_TOOL contains exactly one high-level call:

- navigate_to(target): trusted mission location label only, no arbitrary coordinates or speed.
- locate_object(object_category): new RGB-D, configured segmentation, FoundationPose and camera-to-base transformation; returns opaque pose_id.
- grasp_object(object_category, pose_reference): only the current verified pose_id; internally reuses home/pregrasp/grasp/close/retreat.
- observe_robot_state(): read-only current feedback; state is also collected automatically at skill boundaries.

No release/place tool exists. Every result is independently checked; backend success flags are insufficient.

A pose retains its original acquisition lower-bound timestamp. Model latency cannot refresh it. Base movement and grasp attempts invalidate it. Frame, current source location, object category and motion epoch must match; matrices must be finite rigid SE(3) transforms. Segmentation and FoundationPose scores must be finite before applying configured thresholds.

## Working Memory

A Pydantic object holds MissionSpec, mission status, location, detection/pose, held-target identity, actual width and HELD/NOT_HELD/UNKNOWN, completed/current actions, latest observation/error, retries, turn count, motion epoch and unresolved physical action. Each decision sees a bounded structured summary, rather than complete logs/images.

Only verified tool evidence installs a pose or held-target identity. Missing/stale observations invalidate previous physical claims. Grasp width must be measured, fresh, stable over distinct samples and, for HELD, observed after retreat using a category-specific calibration. Commanded opening is never evidence.

FINISH always acquires new feedback and checks current start location AND held target. UNKNOWN fails the final gate. The agent cannot write COMPLETED itself through a tool argument or model response.

## Episodic Memory

SQLite contains episodes, skill_events and missions. Episodes save task/category/skill/failure, failure observation, recovery strategy, verification result and verified flag. Every skill event and mission snapshot is persisted when memory is enabled.

Retrieve at mission start and on failure, using bound SQL metadata filters by task type, category, skill and failure type. Inject at most three verified successful recoveries. Prompt projections exclude historical poses and raw instructions; memory is advisory context rather than current physical truth.

Failure episodes begin unverified. Promotion requires the original postconditions: navigation must reach its original target, and a carrying navigation must still hold the same target. Observing arrival while empty cannot verify recovery from object loss. Recovery may be saved before mission completion if it has independently succeeded.

## Execution uncertainty

Physical skills run serially. Timeout, cancelled coroutine and terminated process do not establish that hardware stopped. A dispatched ambiguous action sets uncertain_action. Further physical calls are blocked until an explicit observation turn provides fresh settled navigation/arm feedback; grasp reconciliation also requires actual post-retreat holding evidence.

Cancellation attempts an independent configured stop and retains uncertainty until feedback resolves it. POSIX workers own a process group. Windows workers start suspended, join a kill-on-close Job, then resume; descendants remain owned if their parent exits. Killing workers never substitutes for robot state verification.

Three repeated same skill/failure events, a global turn bound, repeated invalid model output and rejected FINISH attempts lead to REQUEST_HELP. ABORT remains available.

## Environments and deployment

Agent: independent Python >=3.10, Pydantic, PyYAML and stdlib SQLite/HTTP/asyncio. ROS workers retain the ROS Noetic system interpreter. FoundationPose retains its own Conda interpreter and model dependencies. No ROS/CUDA/PyTorch upgrade or environment merge is performed.

Real motion requires explicit enablement and a passing confirmed config: actual width calibration, state/stop ports, waypoint tolerances, localization validity and sensor/TF timing. See HARDWARE_VALIDATION.md. Retained arm/camera parameters are inputs preserved from the original project, not new calibration evidence.
