# Vision-Grasp Integration

Chinese version: `README.zh-CN.md`

This directory contains the glue code between the FoundationPose module and the
robot execution stack.

## Purpose

These files are not the original algorithm implementation. They are the robot
integration layer responsible for:

- capture orchestration
- calling the correct Python environment
- packaging pose outputs into stable files
- forwarding pose results into the grasp executor

## Main Files

- `foundationpose_bridge.py`
  loads FoundationPose pose files into typed Python objects
- `run_foundationpose_single.py`
  one-frame inference entrypoint
- `run_foundationpose_single.sh`
  conda wrapper for the inference entrypoint
- `run_pose_grasp_pipeline.py`
  `capture -> pose -> optional grasp` unified command

## Recommended Usage

Perception only:

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

Perception plus real grasp:

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
