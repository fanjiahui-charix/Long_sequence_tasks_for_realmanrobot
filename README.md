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
- `/home/rm/Long_sequence_tasks/vision_grasp/README.md`
