# Vision Grasp 中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

`vision_grasp/` 是完整的视觉抓取模块，覆盖从图像采集到机械臂执行抓取的整条链路。

它包含：

- 相机采集
- mask 生成或手动覆盖
- FoundationPose 6D 位姿估计
- 位姿到抓取位姿的转换
- 机械臂与末端执行器控制

英文版说明见：`README.md`

## 目录结构

```text
vision_grasp/
  foundationpose/    内部 FoundationPose 模块
  integration/       FoundationPose 与机器人之间的集成层
  grasp/             机械臂与末端执行器执行层
  camera/            RGB / RGB-D 采集工具
  bringup/           抓取相关工作空间与驱动启动脚本
  configs/           统一抓取配置
  demo/              较旧的本地 demo 脚本
  ros_packages/      机械臂与末端 ROS 包
  runtime/           每次运行的输出结果
```

## 子模块职责

### `foundationpose/`

内部 FoundationPose 算法模块，用于单帧 6D 位姿估计。

主要内容：

- `estimater.py`
- `Utils.py`
- `learning/`
- `bundlesdf/`
- `mycpp/`
- `run_demo.py`
- `capture_object_rgbd.py`

### `integration/`

机器人侧的 FoundationPose 包装层。

主要文件：

- `run_foundationpose_single.py`
  单帧位姿估计入口
- `run_foundationpose_single.sh`
  FoundationPose conda 环境封装
- `foundationpose_bridge.py`
  读取 pose JSON/TXT 并转成结构化对象
- `run_pose_grasp_pipeline.py`
  一条命令完成 `capture -> mask -> pose -> 可选抓取`
- `run_yolo_seg_mask.py`
  基于官方 Ultralytics 的单帧 YOLO-seg 掩码生成脚本

### `grasp/`

硬件执行层。

另见：

- `/home/rm/Long_sequence_tasks/vision_grasp/grasp/README.md`
- `/home/rm/Long_sequence_tasks/vision_grasp/grasp/README.zh-CN.md`

主要文件：

- `arm_motion_client.py`
  MoveJ_P / MoveL 动作发布
- `end_effector_client.py`
  夹爪或灵巧手控制
- `pose_grasp.py`
  相机位姿到基座位姿的抓取执行
- `run_grasp.py`
  打开、关闭、pick-demo、pose-grasp 的主 CLI

### `camera/`

图像采集层。

主要文件：

- `ros_image_capture.py`
  抓取一张 RGB 图
- `capture_rgb_image.py`
  RGB 抓图命令行工具
- `capture_rgbd_frame.py`
  采 RGB、depth、相机内参，不生成 mask

### `bringup/`

抓取相关的工作空间与驱动启动工具。

- `setup_grasp_ws.sh`
- `start_hand_driver.sh`

## 统一入口

当前推荐使用的新入口是：

- 感知或感知加抓取：
  `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py`
- 纯单帧位姿推理：
  `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.sh`
- 纯抓取执行：
  `/home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py`

为了兼容旧路径，顶层 wrapper 仍然保留：

- `/home/rm/Long_sequence_tasks/vision_grasp/run_pose_grasp_pipeline.py`
- `/home/rm/Long_sequence_tasks/vision_grasp/run_foundationpose_single.sh`
- `/home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py`

## 运行环境

### ROS 控制环境

用于：

- 相机采集
- TF 查询
- 机械臂运动
- 末端控制

需要：

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash
```

### FoundationPose 推理环境

用于：

- 神经网络推理
- CUDA 渲染
- 位姿 refine 和打分

需要：

```bash
source /home/rm/miniforge3/bin/activate foundationpose
```

pipeline 脚本已经帮你拆好了这两套环境。

## Mask 后端

`run_pose_grasp_pipeline.py` 现在支持两种自动 mask 后端：

- `depth`
  传统深度阈值前景分割
- `yolo-seg`
  基于官方 Ultralytics YOLO-seg 的神经网络实例分割

针对你当前这台 Jetson Xavier NX，当前推荐先用：

- 官方轻量模型：`yolov8n-seg.pt`
- 执行环境：`/usr/bin/python3`
- 已验证的远程依赖栈：
  - `ultralytics==8.2.103`
  - `torch 2.1.0a0+41361538.nv23.06`
  - CUDA 可用

注意：

- 官方 COCO 权重 `yolov8n-seg.pt` 更适合先验证
  `YOLO-seg -> mask -> FoundationPose`
  这条代码链和运行兼容性
- 如果要稳定分割你自己的 `glasses_case_box`，通常仍然需要你后续训练一个自定义
  YOLO-seg `best.pt`
- 到那一步时，你只需要替换 `--seg-weights` 和 `--seg-label`

## 常用命令

### 构建抓取 ROS 工作空间

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/bringup/setup_grasp_ws.sh
```

作用：

- 创建或更新 `~/lt_grasp_ws`
- 链接仓库里的 ROS 包
- 执行 `catkin_make`

### 仅启动机械臂和手部驱动

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/bringup/start_hand_driver.sh RM65 6 aoyi_hand
```

参数：

- `RM65`
  机械臂型号
- `6`
  自由度
- `aoyi_hand`
  当前末端执行器后端

### 打开末端执行器

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  open
```

作用：

- 打开当前夹爪或灵巧手

### 关闭末端执行器

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  close
```

### 单帧 FoundationPose 推理

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

作用：

- 执行单帧 6D 位姿估计
- 输出 JSON 位姿文件和 TXT 矩阵文件

### 一条命令完成采图、定位、可选抓取

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

关键参数说明：

- `--camera-name`
  ROS 相机命名空间，例如 `camera_middle`
- `--camera-frame`
  写入 pose 结果并用于 pose-grasp 的 TF 坐标系
- `--mesh`
  目标物体 mesh 路径
- `--object-label`
  输出结果里的物体标签
- `--config`
  抓取配置文件路径
- `--mask`
  不带文件路径时，表示对当前帧自动生成 mask
- `--mask /path/to/mask.png`
  使用手工 mask 或分割模块生成的 mask
- `--execute-grasp`
  真正驱动机械臂执行抓取

### 用 YOLO-seg 先分割，再交给 FoundationPose

```bash
source /home/rm/miniforge3/bin/activate foundationpose

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

作用：

- 先采当前 RGB-D
- 用 YOLO-seg 生成 `mask.png`
- 再把这个 mask 交给 FoundationPose
- 最终把位姿结果写到 runtime 目录

### 从已有 pose 文件执行真实抓取

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pose-grasp \
  --pose-file /tmp/foundationpose_pose.json
```

作用：

- 读取 FoundationPose 输出的 pose 文件
- 查询 `base_frame <- camera_frame`
- 计算 pregrasp、grasp、retreat
- 执行动作序列

## 运行输出

每次运行的结果会放在：

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

## 配置文件

统一抓取配置：

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

关键参数：

- `base_frame`
  机械臂基座坐标系
- `camera_frame`
  FoundationPose 输出使用的相机坐标系
- `arm_ns`
  目标机械臂命名空间
- `end_effector_type`
  `inspire_gripper` 或 `dexterous_hand`
- `home_pose_xyz`, `home_pose_rpy`
  安全 home 位姿
- `pose_grasp_rpy`
  固定抓取姿态时使用的姿态角
- `pregrasp_offset_local`, `retreat_offset_local`
  以局部抓取坐标系定义的接近和退让偏移

## 常见报错

### `base_left does not exist`

含义：

- 机械臂驱动没有起来
- TF 发布不完整

建议：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

含义：

- ROS 代码被错误地放在了 conda 环境里跑

建议：

- 优先使用统一 pipeline 和 bringup 脚本
- 它们会强制让 ROS 子进程走 `/usr/bin/python3`
