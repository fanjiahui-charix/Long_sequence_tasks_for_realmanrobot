# ReAct + Memory Robot Agent

[![Agent software tests](https://github.com/fanjiahui-charix/Long_sequence_tasks_for_realmanrobot/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/fanjiahui-charix/Long_sequence_tasks_for_realmanrobot/actions/workflows/tests.yml)

[简体中文](README.zh-CN.md) · [Architecture](docs/SYSTEM_DESIGN.md) · [Backend API](docs/BACKEND_API.md) · [Evaluation](docs/EVALUATION.md)

Single-agent mobile manipulation: leave A, find/grasp the black glasses case at B, and return while holding it. This replaces the old one-shot planner/runtime with typed ReAct decisions, Working Memory, SQLite Episodic Memory and deterministic verification.

The LLM selects one high-level skill per turn. Only current measured feedback establishes location, usable pose and holding state. FINISH succeeds only after a new check of **at A AND holding the target**. No place/release tool exists.

## Platform demo

![RealMan platform demo at 3× playback speed](docs/media/project-demo.gif)

[Watch or download the original video (51 seconds, MP4)](docs/media/project-demo.mp4).

Existing project footage, shown as a roughly 17-second looping GIF at 3× speed. It illustrates the robot platform and arm motion. The recording's software version has not been mapped to this refactor; the new Agent's validation scope and results are documented in [Evaluation](docs/EVALUATION.md).

## Quick start without hardware or credentials

Use a separate Python **3.10+** environment. Keep existing ROS Noetic and FoundationPose environments.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m robot_agent demo --memory --fault POSE_STALE
python -m robot_agent evaluate --repetitions 3
```

The demo reacquires a stale pose, grasps, returns and verifies both goals. Reports, SQLite and traces go to ignored runtime/. Scripted decisions are explicitly counted as **zero LLM calls** and validate software behavior rather than model quality.

## Qwen API with a mock robot

Copy .env.example to ignored .env and configure your own DashScope key and account-available model. A vision-capable model is required for scene understanding. Each response is Pydantic-validated; a separate vision model can be configured.

```bash
python -m robot_agent demo --llm qwen --image examples/scene_ab.png --memory --fault POSE_STALE --output-dir runtime/qwen-demo
python -m robot_agent evaluate --llm qwen --scenarios pose_stale,execution_unknown --repetitions 2 --output-dir runtime/qwen-evaluation
```

The shipped PNG is a synthetic A/B/table/object schematic, not a physical observation. Replace it and --instruction within the V1 scenario. Actual marker mapping is trusted deployment input, never inferred executable coordinates.

## Robot integration

RobotBackend is a platform-neutral async protocol. Implement it for another robot without changing the core. Optional RealMan adapters reuse navigation/ and vision_grasp/ across their original interpreters.

Real hardware is disabled by default. The shipped configuration intentionally fails until actual width calibration, state/stop ports, goal poses and timing are confirmed:

```bash
python -m robot_agent preflight --hardware-config config/hardware.example.yaml
```

See [hardware deployment](docs/HARDWARE_VALIDATION.md). Missing actual width returns UNKNOWN; target opening is not evidence. The refactor did not certify/recalibrate arm or camera parameters, and development executed no real motion.

## Layout and license

robot_agent/: core, schemas, tools, memory, verifier, backends/adapters and CLI. tests/: automated software checks. navigation/ and vision_grasp/: retained robot/model capabilities. config/: hardware templates and preserved configuration. docs/: architecture, source audit, results and deployment checks.

The new Agent contribution is MIT-licensed; see LICENSE-AGENT and NOTICE.md. Retained third-party/vendor files keep their own licenses. [Audit](docs/AUDIT.md) records provenance, migration and old-agent removal.
