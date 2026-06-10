# Navigation ROS Bridge
[English](./README.md) | [简体中文](./README.zh-CN.md)

`navigation/ros_bridge/` is the ROS-facing navigation adapter layer. It lets
the rest of `Long_sequence_tasks` talk to the chassis through ROS topics rather
than calling the TCP chassis client directly.

## Purpose

Use this directory when you want:

- topic-based navigation integration
- a ROS node that forwards navigation commands to the chassis socket
- quick CLI testing of ROS navigation commands
- planner integration through ROS instead of direct TCP

## Files

- `navigation_bridge.py`
  small Python helper that publishes marker, location, RViz-goal, and cancel
  commands
- `agv_socket_bridge.py`
  ROS node that subscribes to navigation topics and forwards them to the chassis
  TCP API
- `run_navigation_demo.py`
  simple command-line test sender for the ROS navigation path
- `__init__.py`
  package marker

## Topic Contract

Current topics used by this bridge:

- `/navigation_marker`
  string marker command such as `pointc`
- `/long_tasks/navigation_location_json`
  JSON payload with `x`, `y`, `theta`
- `/navigation_move_cancel`
  cancel the current motion
- `/move_base_simple/goal`
  RViz-compatible 2D goal publication
- `/navigation_feedback`
  raw chassis feedback forwarded by the bridge node

## Environment

Run these scripts in a sourced ROS environment:

```bash
source /opt/ros/noetic/setup.bash
```

If your AGV ROS workspace is needed:

```bash
source ~/lt_nav_ws/devel/setup.bash
```

## Main Commands

### Start the ROS-to-chassis bridge

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/agv_socket_bridge.py
```

Effect:

- creates a ROS node
- listens for navigation topics
- forwards marker and location commands to the chassis TCP endpoint

### Send a marker command

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  marker --name pointc
```

Effect:

- publishes one `/navigation_marker` message

### Send a coordinate command

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  location --x 1.0 --y 0.5 --theta 0.0
```

Effect:

- publishes one JSON location command to
  `/long_tasks/navigation_location_json`

### Publish an RViz goal

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  rviz-goal --x 1.0 --y 0.5 --yaw 0.0 --frame-id map
```

Effect:

- publishes a `PoseStamped` message to `/move_base_simple/goal`

### Cancel current navigation

```bash
source /opt/ros/noetic/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py cancel
```

## How It Fits The Project

- `navigation/run_navigation.py`
  is the direct TCP path
- `navigation/ros_bridge/`
  is the ROS topic path
- `planner/skills/navigation_skill.py`
  can use this path when the ROS backend is enabled

## Common Notes

- This bridge does not replace a full ROS navigation stack by itself.
- It is best viewed as a thin adapter between your high-level planner and the
  existing chassis interface.
- RViz goal publication is supported, but whether the robot actually moves from
  `/move_base_simple/goal` depends on what navigation stack is running on the
  robot.
