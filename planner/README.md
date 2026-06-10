# Planner

Chinese version: `README.zh-CN.md`

`planner/` is the long-sequence reasoning and execution layer. It converts a
task description plus scene context into a structured plan, and it can execute
that plan through navigation and manipulation backends.

## Core Purpose

Use this module when you need:

- text-to-plan generation
- plan validation
- skill-based task execution
- a safe mock mode before connecting to real hardware

## Architecture

```text
planner/
  configs/         Runtime config, scene templates, skill and backend settings
  examples/        Runnable demos and entrypoints
  executor/        Plan execution and validation
  llm/             Qwen client, schemas, prompt builder
  skills/          Navigation, perception, manipulation, human-interaction skills
  tests/           Lightweight planner validation tests
```

### File Responsibilities

- `examples/run_long_task.py`
  one-command long-task demo runner
- `examples/run_qwen_planner_demo.py`
  plan generation from one image and one task string
- `examples/run_executor_demo.py`
  executor test from a saved plan JSON
- `executor/task_executor.py`
  executes the generated plan step by step
- `llm/qwen_client.py`
  model client for Qwen-compatible APIs
- `llm/prompt_builder.py`
  assembles the planner prompt
- `skills/navigation_skill.py`
  wraps navigation actions
- `skills/perception_skill.py`
  wraps perception results, including FoundationPose pose-file loading
- `skills/manipulation_skill.py`
  wraps grasp and hand actions

## Environments

- Planner itself:
  `python3`
- When using ROS manipulation:
  source the ROS workspace first

## Main Demo Commands

### Generate a plan from an image

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_qwen_planner_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple"
```

Effect:

- calls the LLM planner
- writes or prints a structured long-sequence plan

### Execute a saved plan

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py \
  --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json
```

Effect:

- loads a plan file
- runs it through the executor and registered skills

### Full mock demo

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_full_mock_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and inspect the table"
```

Effect:

- end-to-end dry run
- no real chassis or grasp hardware is commanded

### One-command long task

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and pick the mustard bottle" \
  --nav-backend tcp \
  --manipulation-backend ros \
  --pick-mode pose_grasp
```

Effect:

- plans the task
- executes navigation through the chosen backend
- executes grasp through the chosen manipulation backend

## Backends

### Navigation backend

- `mock`
  no hardware motion
- `tcp`
  direct chassis control
- `ros`
  ROS topic path

### Manipulation backend

- `mock`
  no hardware motion
- `ros`
  real end effector and pose-grasp execution

## Key Parameters

### `run_long_task.py`

- `--image`
  scene image path
- `--camera-name`
  capture current image from ROS instead of using a saved file
- `--task`
  natural-language task
- `--nav-backend`
  `mock`, `tcp`, or `ros`
- `--manipulation-backend`
  `mock` or `ros`
- `--pick-mode`
  `as_planned`, `close_only`, `pick_demo`, or `pose_grasp`
- `--verbose`
  print extra planner and executor information

## Config Files

- `configs/lab_scene_template.yaml`
  scene structure template
- `configs/nav_targets.yaml`
  named navigation targets
- `configs/skills.yaml`
  enabled skill registry and skill metadata
- `configs/llm.yaml`
  planner model settings

Manipulation now uses the canonical config in:

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

You can override it with:

```bash
export LONG_TASKS_GRASP_CONFIG=/custom/path/grasp_config.yaml
```

## Safe Usage Patterns

### Dry run

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc" \
  --nav-backend mock \
  --manipulation-backend mock
```

### Real base, fake grasp

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc" \
  --nav-backend tcp \
  --manipulation-backend mock
```

### Real base, real pose grasp

Before this mode, run the project bringup:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
```

Then run:

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --camera-name camera_middle \
  --task "go to pointc and pick the mustard bottle" \
  --nav-backend tcp \
  --manipulation-backend ros \
  --pick-mode pose_grasp \
  --verbose
```
