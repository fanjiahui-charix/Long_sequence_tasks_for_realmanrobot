# Grasp Execution
[English](./README.md) | [简体中文](./README.zh-CN.md)

`vision_grasp/grasp/` contains the robot-side execution layer for grasping. It
takes pose outputs or direct commands and turns them into arm motion and
end-effector control.

## Purpose

Use this directory when you need:

- open or close the end effector
- send raw dexterous-hand angles
- run a one-shot local pick demo
- execute a pose-based grasp from a FoundationPose result

## Files

- `arm_motion_client.py`
  publishes arm motion commands such as `MoveJ_P` and `MoveL`
- `end_effector_client.py`
  controls the current end effector, including gripper and dexterous hand
- `pose_grasp.py`
  loads a pose result, looks up TF, computes grasp/pregrasp/retreat poses, and
  executes the sequence
- `run_grasp.py`
  main CLI entrypoint for grasp-related actions

## Environment

Run grasp execution in a sourced ROS environment:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash
```

## Main Commands

### Open the end effector

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  open
```

### Close the end effector

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  close
```

### Set raw dexterous-hand angles

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  set-angles --angles "[0,0,0,0,0,1000]"
```

### Run the older local pick demo

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pick-demo --target-label mustard
```

### Execute pose grasp from a FoundationPose pose file

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pose-grasp \
  --pose-file /tmp/foundationpose_pose.json
```

Effect:

- reads the object pose
- resolves `base_frame <- camera_frame` through TF
- computes pregrasp, grasp, and retreat poses
- executes the full motion sequence

## Important Parameters

### Global flags

- `--config`
  grasp config file path
- `--arm-ns`
  arm namespace such as `l_arm`
- `--end-effector-type`
  `inspire_gripper` or `dexterous_hand`

### `pose-grasp`

- `--pose-file`
  FoundationPose JSON or TXT pose file
- `--target-label`
  optional object label override
- `--camera-frame`
  optional camera frame override

## Motion Logic

The pose-grasp path currently executes:

1. move to home pose
2. open the end effector
3. move to pregrasp
4. move linearly to grasp
5. close the end effector
6. retreat

## Config Dependency

Canonical config:

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

The most important fields are:

- `base_frame`
- `camera_frame`
- `arm_ns`
- `end_effector_type`
- `home_pose_xyz`, `home_pose_rpy`
- `pose_grasp_orientation_mode`
- `pose_grasp_rpy`
- `pregrasp_offset_local`
- `retreat_offset_local`
- `object_grasp_transform`

## Common Errors

### `base_left does not exist`

Meaning:

- arm TF is not available yet
- bringup is incomplete

Fix:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

Meaning:

- the script was launched in the wrong environment

Fix:

- source ROS first
- run the script with the system Python path, not inside an isolated env that
  lacks ROS packages
