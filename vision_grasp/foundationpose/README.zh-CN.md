# FoundationPose 模块中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

这个目录是 `Long_sequence_tasks` 内部使用的 FoundationPose 模块，用于 6D 物体位姿估计。

为了方便整个视觉抓取链路统一开源，它被放在 `vision_grasp/` 目录内部。

英文版说明见：`README.md`

## 这个模块做什么

- 单帧 6D 位姿注册
- 位姿打分与 refine
- 基于 mesh 的渲染支持
- 可选的训练与数据集代码

## 重要文件

- `estimater.py`
  FoundationPose 主估计逻辑
- `Utils.py`
  几何与通用工具函数
- `learning/training/predict_pose_refine.py`
  refine 网络推理逻辑
- `learning/training/predict_score.py`
  score 网络推理逻辑
- `capture_object_rgbd.py`
  当前帧 RGB-D 采集与基于深度的 mask 生成
- `run_demo.py`
  原始 demo 入口

## 当前项目里的机器人适配说明

针对 Jetson Xavier NX 显存和内存限制，这个项目已经对推理链路做了额外优化：

- 更安全的 mesh diameter 计算
- refine 推理分块
- score 推理分块
- 更小的推理 batch

这些改动当前通过下面两个入口使用：

- `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.py`
- `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py`

## 运行环境

FoundationPose 运行在：

```bash
source /home/rm/miniforge3/bin/activate foundationpose
```

## 权重说明

大体积权重文件默认不跟 Git 走。你在实际推理前，需要把模型权重放到 FoundationPose 预期的位置。后续如果你开放仓库，可以单独在 README 里补一段权重下载说明。 
