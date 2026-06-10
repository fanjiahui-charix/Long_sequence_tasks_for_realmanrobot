# 视觉抓取集成层中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

这个目录是 FoundationPose 模块和机器人抓取执行栈之间的胶水层。

这里的代码不是原始算法实现，而是专门为你这台机器人做的集成层。

英文版说明见：`README.md`

## 主要职责

这个目录负责：

- 组织采图流程
- 调用正确的 Python 环境
- 把位姿结果写成稳定格式文件
- 把位姿结果交给抓取执行层

## 主要文件

- `foundationpose_bridge.py`
  读取 FoundationPose 的 pose 文件并转成 Python 对象
- `run_foundationpose_single.py`
  单帧推理入口
- `run_foundationpose_single.sh`
  单帧推理的 conda 包装脚本
- `run_pose_grasp_pipeline.py`
  统一的 `capture -> pose -> 可选抓取` 入口

## 推荐用法

### 只感知，不抓取

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

### 感知后真实抓取

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

## 说明

- `--mask`
  不带路径时，表示自动根据当前帧生成 mask
- `--mask /path/to/mask.png`
  表示使用外部分割模块或手工生成的 mask
- `--execute-grasp`
  是安全开关，不加时只输出 pose，不会真的驱动机械臂
