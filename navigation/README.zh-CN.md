# Navigation 中文说明
[English](./README.md) | [简体中文](./README.zh-CN.md)

`navigation/` 是长序列任务里的底盘运动层，负责把上层目标转成底盘移动命令。

这个模块提供两条控制路径：

- 直接通过 TCP 与底盘控制器通信
- 通过 ROS 封装层接入机器人整体系统

英文版说明见：`README.md`

## 核心作用

你在这些场景下会用到它：

- 移动到某个命名点位
- 移动到某个桌子或目标区域
- 移动到显式给定的 `(x, y, theta)` 坐标
- 从 Python 查询底盘当前状态

## 代码结构

```text
navigation/
  chassis_client.py          底盘 TCP 客户端
  run_navigation.py          主 CLI 入口
  ros_bridge/                ROS 桥接与发布代码
  ros_packages/              AGV 相关 ROS 包
  setup_nav_ws.sh            导航工作空间构建脚本
```

### 文件职责

- `chassis_client.py`
  最底层 TCP 通信接口，负责发 marker、目标点、坐标命令
- `run_navigation.py`
  面向使用者的主入口脚本
- `ros_bridge/navigation_bridge.py`
  ROS 侧导航命令发布封装
- `ros_bridge/agv_socket_bridge.py`
  把 ROS 导航命令转发到底盘 TCP 接口
- `ros_bridge/README.md`
  ROS 桥接层说明和话题约定
- `ros_packages/rm_dual_arm_agv`
  项目内置的 AGV ROS 包
- `setup_nav_ws.sh`
  创建并构建 `~/lt_nav_ws`

## 运行环境

- 直接 TCP 路径：
  `python3`
- ROS 路径：
  `/usr/bin/python3`
  同时 `source /opt/ros/noetic/setup.bash`

## 常用命令

### 查看所有标记点

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
```

作用：

- 打印当前配置里的导航标记点

### 查看底盘状态

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py status
```

作用：

- 通过 TCP 读取当前底盘状态

### 移动到命名目标

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

参数：

- `--name`
  导航目标别名

作用：

- 让底盘移动到指定命名点

### 移动到 marker

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py marker --name pointc
```

作用：

- 通过底盘接口按 marker 导航

### 移动到显式坐标

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py \
  location --x 1.0 --y 0.5 --theta 0.0
```

参数：

- `--x`
  地图坐标系 x
- `--y`
  地图坐标系 y
- `--theta`
  偏航角，单位是弧度

## ROS 启动路径

如果你希望走 ROS 集成路径：

```bash
bash /home/rm/Long_sequence_tasks/navigation/setup_nav_ws.sh
```

然后：

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

### ROS 导航示例

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```

作用：

- 通过 ROS 话题发布导航命令，而不是直接 TCP 发命令

## 什么时候用哪条路径

优先用直接 TCP，当你：

- 只想用最简单的控制链路
- 不想经过 ROS 话题中间层
- 直接从 Python 集成导航功能

优先用 ROS，当你：

- 需要和其他 ROS 节点联动
- 想让其他节点观察或复用导航动作
- 当前 bringup 本来就依赖 AGV ROS 节点
