# Long Sequence Tasks

This folder is the standalone open-source workspace for your dual-arm mobile
robot demos and long-sequence task code.

The layout is now grouped by function instead of by implementation layer.

## Layout

```text
Long_sequence_tasks/
  navigation/              All chassis navigation code
  planner/                 LLM planning, executor, skills, configs
  vision_grasp/            Perception, grasp demo, end-effector code
  requirements.txt
```

## Main Entrypoints

- Navigation entry:
  `/home/rm/Long_sequence_tasks/navigation/run_navigation.py`
- Planner / executor code:
  `/home/rm/Long_sequence_tasks/planner/`
- Vision + grasp demo:
  `/home/rm/Long_sequence_tasks/vision_grasp/demo/`

## Quick Start

Send one navigation command directly from this repo:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

List current markers:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
```

Read robot status:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py status
```

The planner skill layer can also use direct TCP navigation by default. For ROS
compatibility, set:

```bash
export LONG_TASKS_NAV_BACKEND=ros
```

See module docs:

- `/home/rm/Long_sequence_tasks/navigation/README.md`
- `/home/rm/Long_sequence_tasks/planner/README.md`
- `/home/rm/Long_sequence_tasks/vision_grasp/README.md`

## Verified Locally

These entrypoints were verified in the current workspace:

- `python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers`
- `python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py status`
- `python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json`
- `bash /home/rm/Long_sequence_tasks/navigation/setup_nav_ws.sh`
- `bash /home/rm/Long_sequence_tasks/vision_grasp/setup_grasp_ws.sh`

The grasp CLI itself is wired and documented, but I did not send a live open or
close command in this pass because that would physically move the end effector.

For the hand side, the vendored low-level arm driver package now lives under:

- `/home/rm/Long_sequence_tasks/vision_grasp/ros_packages/rm_dual_arm_arm_driver`
