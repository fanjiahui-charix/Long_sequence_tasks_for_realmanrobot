# 视觉抓取集成层中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

这个目录是 FoundationPose 模块和机器人抓取执行栈之间的胶水层。

这里的代码不是原始算法实现，而是专门为你这台机器人做的集成层。

## 主要职责

这个目录负责：

- 组织采图流程
- 调用正确的 Python 环境
- 通过深度法或 YOLO-seg 生成 mask
- 把位姿结果写成稳定格式文件
- 把位姿结果交给抓取执行层

## 主要文件

- `foundationpose_bridge.py`
  读取 FoundationPose 的 pose 文件并转成 Python 对象
- `run_foundationpose_single.py`
  单帧推理入口
- `run_foundationpose_single.sh`
  单帧推理的 conda 包装脚本
- `run_yolo_seg_mask.py`
  基于官方 Ultralytics 的 YOLO-seg 掩码生成脚本
- `run_pose_grasp_pipeline.py`
  统一的 `capture -> mask -> FoundationPose -> 可选抓取` 入口

## 推荐用法

### 只感知，不抓取

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

### 感知后真实抓取

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

### 用 YOLO-seg 先分割，再交给 FoundationPose

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

### 只跑一次 YOLO-seg 分割

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_yolo_seg_mask.py \
  --rgb /home/rm/Long_sequence_tasks/vision_grasp/runtime/<run_id>/capture/rgb.png \
  --output-mask /tmp/yolo_seg_mask.png \
  --output-vis /tmp/yolo_seg_mask_vis.png \
  --output-json /tmp/yolo_seg_result.json \
  --weights yolov8n-seg.pt \
  --label person
```

## 模型说明

- 针对 Jetson Xavier NX，当前推荐先用官方轻量模型：
  `yolov8n-seg.pt`
- 选择它的原因是你远程机器人当前已经具备：
  - `/usr/bin/python3`
  - `ultralytics==8.2.103`
  - `torch 2.1.0a0+41361538.nv23.06`
  - CUDA 可用
- 但是要分割你自己的 `glasses_case_box`，通常还是需要你训练一个
  自定义 YOLO-seg 权重，然后把 `--seg-weights` 指向你的 `best.pt`
- 官方 COCO 分割权重更适合先验证
  `YOLO-seg -> mask -> FoundationPose`
  这条代码链能不能跑通

## 关键参数

- `--mask-backend`
  `depth` 或 `yolo-seg`
- `--seg-weights`
  官方或自定义 YOLO-seg 权重路径
- `--seg-label`
  目标分割类别名
- `--seg-conf`
  分割置信度阈值
- `--seg-imgsz`
  YOLO 推理尺寸
- `--seg-device`
  `0` 表示 CUDA，`cpu` 表示 CPU
- `--mask`
  继续保留自动生成 mask 的入口；如果写成
  `--mask /path/to/mask.png`
  就表示直接使用外部 mask 文件

## 典型生产链路

当你自己的 YOLO-seg `best.pt` 准备好以后，正常流程就是：

1. 采一帧 RGB-D
2. 跑 `yolo-seg`
3. 生成 `mask.png`
4. 把这个 mask 交给 FoundationPose
5. 再执行 pose grasp
