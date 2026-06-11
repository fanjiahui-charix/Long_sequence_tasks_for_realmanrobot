# Vision Grasp Segmentation
[English](./README.md) | [简体中文](./README.zh-CN.md)

`vision_grasp/segmentation/` contains the neural segmentation layer used before
FoundationPose.

Its job is simple:

- read the current RGB frame
- run YOLO-seg
- write a clean `mask.png`
- hand that mask to FoundationPose

This is the right place to look when you want to:

- change segmentation models
- train a custom glasses-case segmentation model
- debug why the generated mask is wrong

## Main Files

- `run_yolo_seg_mask.py`
  one-frame segmentation inference
- `train_yolo_seg.py`
  training entrypoint for a custom YOLO-seg model
- `capture_seg_dataset.py`
  interactive RGB-D dataset collection tool with snapshot and video modes
- `datasets/glasses_case_box_seg_example.yaml`
  example dataset config for a custom glasses case class

## Recommended Model on the Current Robot

For your Jetson Xavier NX, the current recommended official baseline is:

- `yolov8n-seg.pt`

This is a good fit because the remote robot already has:

- `/usr/bin/python3`
- `ultralytics==8.2.103`
- `torch 2.1.0a0+41361538.nv23.06`
- CUDA available

Important:

- `yolov8n-seg.pt` is suitable for code-path and runtime verification
- it does **not** know your custom `glasses_case_box` class
- for stable real grasping, you should train your own YOLO-seg `best.pt`

## Inference Command

```bash
/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/run_yolo_seg_mask.py \
  --rgb /home/rm/Long_sequence_tasks/vision_grasp/runtime/<run_id>/capture/rgb.png \
  --output-mask /tmp/yolo_seg_mask.png \
  --output-vis /tmp/yolo_seg_mask_vis.png \
  --output-json /tmp/yolo_seg_result.json \
  --weights /home/rm/yolov8n-seg.pt \
  --label person
```

Outputs:

- binary `mask.png`
- visualization image with the chosen instance
- JSON metadata for debugging

## Dataset Capture on the Robot

This repository also includes an interactive dataset capture tool:

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash

/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/capture_seg_dataset.py \
  --camera-name camera_middle \
  --dataset-name glasses_case_box \
  --mode snapshot
```

Two modes are supported:

- `--mode snapshot`
  open a live preview and save RGB-D frames with key presses
- `--mode video`
  record RGB video and optionally auto-extract frames after recording stops

Keyboard:

- `s` or `Space`
  save current RGB-D snapshot
- `r`
  start or stop recording in `video` mode
- `h`
  print help
- `q` or `Esc`
  quit

Output layout:

```text
vision_grasp/segmentation/datasets/<dataset_name>/
  raw/
    <session_name>/
      camera/
        cam_K.txt
        camera_info.json
      snapshots/
        rgb/
        depth/
        meta/
      videos/
        rgb_video_000001.mp4
        meta/
        extracted_frames/
```

## Pipeline Command

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask-backend yolo-seg \
  --seg-weights /home/rm/yolov8n-seg.pt \
  --seg-label glasses_case_box \
  --mask
```

## Dataset Layout

For a custom segmentation model, prepare your dataset like this:

```text
vision_grasp/segmentation/datasets/glasses_case_box/
  images/
    train/
    val/
  labels/
    train/
    val/
```

Notes:

- labels must follow the Ultralytics YOLO-seg polygon format
- class id `0` should map to `glasses_case_box`
- the example YAML file can be copied and edited directly

## Training Command

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

By default, training outputs are written to:

- `vision_grasp/weights/yolo_seg_runs/`

That directory is already ignored by Git.

## After Training

Once your training finishes, the normal path is:

1. take the produced `best.pt`
2. point `--seg-weights` at that file
3. set `--seg-label glasses_case_box`
4. rerun the visual grasp pipeline
