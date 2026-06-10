# Long Sequence Tasks

Chinese version: `README.zh-CN.md`

This repository is the unified workspace for long-horizon mobile manipulation on
the robot. It groups the project by capability instead of by implementation
layer:

- `navigation/`: chassis motion and AGV integration
- `planner/`: text-to-plan, plan validation, and task execution
- `vision_grasp/`: camera capture, FoundationPose 6D estimation, and grasp
  execution

The repository is organized so it can be published as a single open-source
project. Third-party pose estimation code is now managed inside
`vision_grasp/foundationpose/` as an internal module, and the robot-specific
integration layer lives beside it.

## Architecture

The full demo path is:

1. Start hardware and ROS dependencies with the layered bringup scripts.
2. Use `planner/` to turn a text task into a structured long-sequence plan.
3. Use `navigation/` to move the base to the target waypoint or table.
4. Use `vision_grasp/` to capture the current camera frame, generate or supply
   a mask, run FoundationPose, transform the pose into the arm base frame, and
   execute the grasp.

The three main modules are intentionally separable:

- `navigation/` can be tested without perception or grasp.
- `planner/` can run with mock backends.
- `vision_grasp/` can do perception-only or perception-plus-grasp.

## Repository Layout

```text
Long_sequence_tasks/
  navigation/          Mobile base code and ROS bridges
  planner/             LLM planning and executor layer
  vision_grasp/        Camera, grasp, FoundationPose, and integration code
  scripts/             One-command bringup, stop, and health-check helpers
  .env.example         Environment variable template
  README.md            Project-level guide
```

See module guides:

- `/home/rm/Long_sequence_tasks/navigation/README.md`
- `/home/rm/Long_sequence_tasks/planner/README.md`
- `/home/rm/Long_sequence_tasks/vision_grasp/README.md`

## Environments

This project uses two Python environments:

- ROS / hardware control:
  `/usr/bin/python3` with `source /opt/ros/noetic/setup.bash`
- FoundationPose inference:
  `conda activate foundationpose`

The grasp and camera subprocesses are launched with ROS's system Python. The
FoundationPose integration scripts call the `foundationpose` conda environment
for pose estimation.

## Bringup

Use the unified bringup entrypoint:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
```

`--mode minimal` starts:

- `roscore`
- mobile base driver
- head camera
- 6-DOF arm driver and end effector driver

Use the fuller mode when you also want the AGV ROS bridge process:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode full
```

Stop all processes started by the bringup script:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_stop.sh
```

Check current nodes, topics, and key TF relations:

```bash
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

## Demo Paths

### 1. Navigation only

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

Effect:

- `markers`: prints known navigation markers
- `target --name table_2`: sends the chassis to the named target

### 2. Planner only

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and check whether there is an apple" \
  --nav-backend mock \
  --manipulation-backend mock
```

Effect:

- uses the Qwen planner path
- outputs and executes a long-sequence plan with mock backends
- safe for dry-run validation

### 3. Vision pose only

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/foundationpose/demo_data/mustard0/mesh/textured_simple.obj \
  --object-label mustard \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  --mask
```

Effect:

- captures one current RGB-D frame
- auto-generates a mask from the current depth image
- runs FoundationPose
- writes `foundationpose_pose.json` and `pipeline_result.json`
- does not move hardware unless `--execute-grasp` is added

### 4. Vision pose + real grasp

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/foundationpose/demo_data/mustard0/mesh/textured_simple.obj \
  --object-label mustard \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  --mask \
  --execute-grasp
```

Effect:

- runs the same perception chain as above
- consumes the FoundationPose output
- transforms camera pose into arm base frame
- executes `home -> pregrasp -> grasp -> close -> retreat`

## Key Config Files

- `/home/rm/Long_sequence_tasks/.env.example`
  environment variables for planner and global paths
- `/home/rm/Long_sequence_tasks/planner/configs/*.yaml`
  planner prompts, skills, task scene templates, nav targets
- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`
  grasp frames, end-effector parameters, retreat offsets, and pose-grasp
  settings

## Common Problems

### `tf2.LookupException: "base_left" passed to lookupTransform argument target_frame does not exist`

Meaning:

- the arm driver or TF publisher is not running, or
- bringup finished only partially, or
- the configured base frame does not match the active robot graph

Recommended checks:

```bash
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

Meaning:

- a ROS-dependent script was launched in the wrong Python environment without
  ROS setup sourced

Fix:

- use the new pipeline and bringup scripts
- they already force ROS subprocesses to use `/usr/bin/python3`

## Publishing Notes

The repository is prepared for GitHub publication. Runtime outputs and large
FoundationPose artifacts should stay out of version control:

- `vision_grasp/runtime/`
- `vision_grasp/foundationpose/weights/`
- `.run/`
