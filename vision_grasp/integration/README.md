# Vision-Grasp Integration
[English](./README.md) | [简体中文](./README.zh-CN.md)

This directory contains the glue code between the FoundationPose module and the
robot execution stack.

## Purpose

These files are not the original algorithm implementation. They are the robot
integration layer responsible for:

- capture orchestration
- calling the correct Python environment
- generating masks through depth or YOLO-seg
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
  unified `capture -> mask -> FoundationPose -> optional grasp` command

YOLO-seg now lives in:

- `/home/rm/Long_sequence_tasks/vision_grasp/segmentation/`

## Recommended Usage

### Perception only

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask
```

### Perception plus real grasp

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask \
  --execute-grasp
```

### YOLO-seg mask plus FoundationPose

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask-backend yolo-seg \
  --seg-weights yolov8n-seg.pt \
  --seg-label glasses_case_box \
  --mask
```

### Segmentation-only smoke test

```bash
/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/run_yolo_seg_mask.py \
  --rgb /home/rm/Long_sequence_tasks/vision_grasp/runtime/<run_id>/capture/rgb.png \
  --output-mask /tmp/yolo_seg_mask.png \
  --output-vis /tmp/yolo_seg_mask_vis.png \
  --output-json /tmp/yolo_seg_result.json \
  --weights /home/rm/yolov8n-seg.pt \
  --label person
```

### Train a custom YOLO-seg model

```bash
/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/train_yolo_seg.py \
  --data /home/rm/Long_sequence_tasks/vision_grasp/segmentation/datasets/glasses_case_box_seg_example.yaml \
  --model /home/rm/yolov8n-seg.pt \
  --epochs 100 \
  --imgsz 640 \
  --batch 8 \
  --device 0 \
  --name glasses_case_box_seg
```

## Notes About Models

- Recommended official lightweight model for Jetson Xavier NX:
  `yolov8n-seg.pt`
- This is a good official baseline because your remote robot already has:
  - `/usr/bin/python3`
  - `ultralytics==8.2.103`
  - `torch 2.1.0a0+41361538.nv23.06`
  - CUDA available
- For your actual `glasses_case_box` workflow, you will usually need a custom
  YOLO-seg weight that contains that class. The official COCO weights are
  useful for pipeline verification, but they do not know your custom glasses
  case class.

## Important Arguments

- `--mask-backend`
  `depth` or `yolo-seg`
- `--seg-weights`
  official or custom YOLO-seg weight path
- `--seg-label`
  target segmentation class label
- `--seg-conf`
  segmentation confidence threshold
- `--seg-imgsz`
  YOLO inference image size
- `--seg-device`
  `0` for CUDA or `cpu` for CPU
- `--mask`
  keep this enabled for auto-mask mode; use `--mask /path/to/mask.png` for a
  manual mask file instead

## Typical Next Step

Once your custom YOLO-seg `best.pt` is ready, the normal production path is:

1. capture RGB-D
2. run `yolo-seg`
3. write `mask.png`
4. run FoundationPose with that mask
5. execute pose grasp
