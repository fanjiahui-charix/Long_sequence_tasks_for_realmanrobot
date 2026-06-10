# Vision Grasp

Chinese version: `README.zh-CN.md`

`vision_grasp/` contains the full visual grasping stack:

- camera capture
- mask generation or mask override
- FoundationPose 6D pose estimation
- pose-to-grasp transformation
- arm and hand execution

It is now organized so the algorithm module and the robot integration layer are
in one place.

## Architecture

```text
vision_grasp/
  foundationpose/    Internal FoundationPose module
  integration/       FoundationPose wrappers and robot-facing pipelines
  grasp/             Arm and end-effector execution layer
  camera/            RGB / RGB-D capture helpers
  bringup/           Workspace setup and arm-driver launch helpers
  configs/           Canonical grasp config
  demo/              Older local vision-grasp demo scripts
  ros_packages/      Vendored arm driver and end-effector ROS packages
  runtime/           Per-run outputs, logs, pose files
```

## Submodule Responsibilities

### `foundationpose/`

Contains the internal FoundationPose codebase used for single-frame 6D pose
estimation.

Main contents:

- `estimater.py`
- `Utils.py`
- `learning/`
- `bundlesdf/`
- `mycpp/`
- `run_demo.py`
- `capture_object_rgbd.py`

### `integration/`

Contains the robot-specific wrappers around FoundationPose.

Main files:

- `run_foundationpose_single.py`
  one-frame FoundationPose inference entry
- `run_foundationpose_single.sh`
  conda-env wrapper for the inference entry
- `foundationpose_bridge.py`
  loads pose JSON/TXT into structured Python objects
- `run_pose_grasp_pipeline.py`
  one-command `capture -> mask -> pose -> optional grasp`

### `grasp/`

Contains hardware execution code.

See also:

- `/home/rm/Long_sequence_tasks/vision_grasp/grasp/README.md`
- `/home/rm/Long_sequence_tasks/vision_grasp/grasp/README.zh-CN.md`

Main files:

- `arm_motion_client.py`
  MoveJ_P / MoveL publishers
- `end_effector_client.py`
  gripper / dexterous hand control
- `pose_grasp.py`
  camera-pose to base-frame grasp execution
- `run_grasp.py`
  main CLI for open, close, pick-demo, and pose-grasp

### `camera/`

Contains frame acquisition helpers.

Main files:

- `ros_image_capture.py`
  capture one RGB frame
- `capture_rgb_image.py`
  CLI around RGB capture
- `capture_rgbd_frame.py`
  capture RGB, depth, and intrinsics without generating a mask

### `bringup/`

Contains grasp-side ROS workspace and driver launch helpers.

- `setup_grasp_ws.sh`
- `start_hand_driver.sh`

## Canonical Entry Points

The new canonical paths are:

- Pose-only or pose+grasp pipeline:
  `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py`
- Raw pose inference:
  `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.sh`
- Grasp execution:
  `/home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py`

For compatibility, top-level wrappers still exist at:

- `/home/rm/Long_sequence_tasks/vision_grasp/run_pose_grasp_pipeline.py`
- `/home/rm/Long_sequence_tasks/vision_grasp/run_foundationpose_single.sh`
- `/home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py`

## Environments

### ROS control side

Used for:

- camera capture
- TF lookup
- arm motion
- hand motion

Requirements:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash
```

### FoundationPose side

Used for:

- neural inference
- CUDA rendering
- pose refinement and scoring

Requirements:

```bash
source /home/rm/miniforge3/bin/activate foundationpose
```

The pipeline scripts already split these environments correctly.

## Main Commands

### Build the grasp ROS workspace

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/bringup/setup_grasp_ws.sh
```

Effect:

- creates or updates `~/lt_grasp_ws`
- links the vendored ROS packages from this repo
- runs `catkin_make`

### Start only the arm / hand driver

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/bringup/start_hand_driver.sh RM65 6 aoyi_hand
```

Parameters:

- `RM65`: arm model
- `6`: degrees of freedom
- `aoyi_hand`: active end-effector backend

### Open the end effector

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  open
```

Effect:

- opens the current gripper or dexterous hand

### Close the end effector

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  close
```

### One-frame FoundationPose inference

```bash
/home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.sh \
  --mesh /path/to/object.obj \
  --rgb /path/to/rgb.png \
  --depth /path/to/depth.png \
  --mask /path/to/mask.png \
  --k-file /path/to/cam_K.txt \
  --camera-frame camera_middle \
  --object-label mustard \
  --output /tmp/foundationpose_pose.json
```

Effect:

- runs one-frame pose estimation
- writes a JSON pose file and a sidecar TXT matrix

### Unified capture -> pose -> optional grasp

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

Meaning of the important arguments:

- `--camera-name`
  ROS camera namespace, for example `camera_middle`
- `--camera-frame`
  TF frame written into the pose result and used for pose-grasp
- `--mesh`
  object mesh path
- `--object-label`
  label stored into the pose result
- `--config`
  grasp config path
- `--mask`
  with no file path, auto-generate a mask from the current RGB-D frame
- `--mask /path/to/mask.png`
  use a manual or segmentation-generated mask file instead
- `--execute-grasp`
  actually move the hardware after pose estimation

### Real pose grasp from an existing pose file

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pose-grasp \
  --pose-file /tmp/foundationpose_pose.json
```

Effect:

- loads a FoundationPose pose file
- looks up `base_frame <- camera_frame`
- computes grasp, pregrasp, and retreat poses
- executes the motion sequence

## Runtime Outputs

Per-run outputs are stored in:

```text
vision_grasp/runtime/<run_id>/
  capture/
    rgb.png
    depth.png
    mask.png
    cam_K.txt
    mask_vis.png
  foundationpose_debug/
  foundationpose_pose.json
  foundationpose_pose.txt
  pipeline_result.json
```

## Config File

Canonical config:

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

Key parameters:

- `base_frame`
  arm base frame used for TF lookup and motion execution
- `camera_frame`
  source frame for the FoundationPose output
- `arm_ns`
  target arm namespace
- `end_effector_type`
  `inspire_gripper` or `dexterous_hand`
- `home_pose_xyz`, `home_pose_rpy`
  approach-safe home pose
- `pose_grasp_rpy`
  fixed grasp orientation when using `fixed_rpy`
- `pregrasp_offset_local`, `retreat_offset_local`
  offsets applied in local grasp coordinates

## Common Errors

### `base_left does not exist`

Meaning:

- the arm driver is not up, or
- TF publishing is incomplete

Fix:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

Meaning:

- ROS code was launched inside the wrong Python environment

Fix:

- use the unified pipeline and bringup scripts
- they force ROS subprocesses to use `/usr/bin/python3`
