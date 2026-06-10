# 抓取执行层中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

`vision_grasp/grasp/` 是抓取模块的机器人执行层。它负责把位姿结果或直接控制命令，转换成机械臂动作和末端执行器控制。

英文版说明见：`README.md`

## 作用

这个目录主要用于：

- 打开或关闭末端执行器
- 发送灵巧手原始角度
- 运行较老的一次性本地抓取 demo
- 根据 FoundationPose 的位姿结果执行 pose grasp

## 文件说明

- `arm_motion_client.py`
  负责发布机械臂动作命令，例如 `MoveJ_P`、`MoveL`
- `end_effector_client.py`
  负责控制当前末端执行器，包括夹爪和灵巧手
- `pose_grasp.py`
  负责读取位姿结果、查询 TF、计算 grasp/pregrasp/retreat，并执行动作序列
- `run_grasp.py`
  抓取相关功能的主命令行入口

## 运行环境

抓取执行需要在 source 过的 ROS 环境里运行：

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash
```

## 常用命令

### 打开末端执行器

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  open
```

### 关闭末端执行器

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  close
```

### 设置灵巧手原始角度

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  set-angles --angles "[0,0,0,0,0,1000]"
```

### 运行旧版本地抓取 demo

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pick-demo --target-label mustard
```

### 根据 FoundationPose 位姿文件执行抓取

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/grasp/run_grasp.py \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  pose-grasp \
  --pose-file /tmp/foundationpose_pose.json
```

作用：

- 读取物体位姿
- 查询 `base_frame <- camera_frame`
- 计算 pregrasp、grasp、retreat
- 执行完整动作序列

## 重要参数

### 全局参数

- `--config`
  抓取配置文件路径
- `--arm-ns`
  机械臂命名空间，例如 `l_arm`
- `--end-effector-type`
  `inspire_gripper` 或 `dexterous_hand`

### `pose-grasp` 子命令

- `--pose-file`
  FoundationPose 输出的 JSON 或 TXT 位姿文件
- `--target-label`
  可选的物体标签覆盖
- `--camera-frame`
  可选的相机坐标系覆盖

## 动作逻辑

当前 pose grasp 的执行顺序是：

1. 回到 home 位姿
2. 打开末端执行器
3. 运动到 pregrasp
4. 直线插补到 grasp
5. 关闭末端执行器
6. retreat 退回

## 配置依赖

统一抓取配置：

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

最关键的字段包括：

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

## 常见报错

### `base_left does not exist`

含义：

- 机械臂 TF 还没起来
- bringup 不完整

建议：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

含义：

- 脚本运行在错误环境里

建议：

- 先 source ROS
- 用系统 Python 运行，而不是在缺少 ROS 包的隔离环境里直接运行
