# Planner

This module contains the long-sequence planning and execution layer.

## Layout

```text
planner/
  configs/     Skill whitelist and runtime config
  examples/    Runnable entrypoints
  executor/    Plan validation and step execution
  llm/         Qwen prompt and API client
  skills/      Navigation, manipulation, perception, human-interaction skills
  tests/       Lightweight validation tests
```

## Main Entry Points

Generate a plan from one image and one task:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_qwen_planner_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple"
```

Execute a saved plan:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py \
  --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json
```

The example runner defaults to:

- `LONG_TASKS_NAV_BACKEND=mock`
- `LONG_TASKS_MANIPULATION_BACKEND=mock`

To run against the real chassis:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py \
  --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json \
  --nav-backend tcp
```

Generate and execute with mock skills:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_full_mock_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple"
```

One-command long-task entry:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple"
```

Use the current RGB image from ROS instead of a saved file:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --camera-name camera_middle \
  --task "go to pointc" \
  --nav-backend tcp \
  --manipulation-backend mock \
  --verbose
```

## Backends

Navigation skill backends:

- `LONG_TASKS_NAV_BACKEND=tcp`
- `LONG_TASKS_NAV_BACKEND=ros`
- `LONG_TASKS_NAV_BACKEND=mock`

Manipulation skill backends:

- `LONG_TASKS_MANIPULATION_BACKEND=mock`
- `LONG_TASKS_MANIPULATION_BACKEND=ros`

When `LONG_TASKS_MANIPULATION_BACKEND=ros`, `pick_object` and `place_object`
use the config in `planner/configs/grasp.yaml`.

## Recommended Modes

Safe dry run:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple" \
  --nav-backend mock \
  --manipulation-backend mock
```

Real navigation, no real grasp:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc" \
  --nav-backend tcp \
  --manipulation-backend mock
```

Real navigation plus real hand close/open through ROS:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and pick the apple" \
  --nav-backend tcp \
  --manipulation-backend ros \
  --pick-mode pick_demo
```

Current limitation:

- `detect_object` is still a stub skill in the executor.
- `pick_demo` is the current path that actually runs local vision detection and
  grasp execution.
- When using `--camera-name`, ROS camera topics must already be running.

## Sample Plan

See:

- `/home/rm/Long_sequence_tasks/planner/examples/sample_plan.json`

Verified local command:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py \
  --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json
```
