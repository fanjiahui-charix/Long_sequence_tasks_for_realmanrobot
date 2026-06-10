# Navigation ROS 桥接层中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

`navigation/ros_bridge/` 是导航模块的 ROS 适配层。它让 `Long_sequence_tasks` 的其他模块可以通过 ROS 话题发导航命令，而不是直接调用底盘 TCP 客户端。

英文版说明见：`README.md`

## 作用

这个目录主要用于：

- 通过 ROS 话题接入导航
- 提供一个 ROS 节点，把导航命令转发到底盘 TCP 接口
- 用命令行快速测试 ROS 导航命令
- 让 planner 走 ROS 后端而不是直接 TCP

## 文件说明

- `navigation_bridge.py`
  一个轻量 Python 封装，用来发布 marker、location、RViz goal 和 cancel
- `agv_socket_bridge.py`
  ROS 节点，订阅导航话题并转发到底盘 TCP API
- `run_navigation_demo.py`
  ROS 导航路径的命令行测试脚本
- `__init__.py`
  Python 包标记文件

## 当前话题约定

这个桥接层当前使用的话题有：

- `/navigation_marker`
  marker 导航命令，例如 `pointc`
- `/long_tasks/navigation_location_json`
  带 `x`、`y`、`theta` 的 JSON 坐标命令
- `/navigation_move_cancel`
  取消当前导航
- `/move_base_simple/goal`
  RViz 兼容的 2D Goal 话题
- `/navigation_feedback`
  从底盘转发回来的原始反馈

## 运行环境

这些脚本需要在 source 过的 ROS 环境里运行：

```bash
source /opt/ros/noetic/setup.bash
```

如果还需要 AGV 的 ROS 工作空间：

```bash
source ~/lt_nav_ws/devel/setup.bash
```

## 常用命令

### 启动 ROS 到底盘的桥接节点

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/agv_socket_bridge.py
```

作用：

- 启动一个 ROS 节点
- 监听导航话题
- 把 marker 和坐标命令转发到底盘 TCP 接口

### 发送 marker 导航命令

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  marker --name pointc
```

作用：

- 发布一条 `/navigation_marker` 消息

### 发送坐标导航命令

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  location --x 1.0 --y 0.5 --theta 0.0
```

作用：

- 向 `/long_tasks/navigation_location_json` 发布一条 JSON 坐标命令

### 发布 RViz 目标点

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  rviz-goal --x 1.0 --y 0.5 --yaw 0.0 --frame-id map
```

作用：

- 向 `/move_base_simple/goal` 发布一个 `PoseStamped`

### 取消当前导航

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py cancel
```

## 它在整个项目里的位置

- `navigation/run_navigation.py`
  是直接 TCP 路径
- `navigation/ros_bridge/`
  是 ROS 话题路径
- `planner/skills/navigation_skill.py`
  开启 ROS 后端时会走这一套路径

## 补充说明

- 这个桥接层本身不是完整 ROS 导航栈。
- 更准确地说，它是“高层规划模块”和“现有底盘接口”之间的一层轻量适配。
- 它支持 RViz goal 发布，但机器人是否真的会因为 `/move_base_simple/goal` 动起来，还取决于机器上是否有完整的导航栈在监听。 
