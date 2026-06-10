# Navigation
[English](./README.md) | [简体中文](./README.zh-CN.md)

`navigation/` contains the base-motion layer for long-sequence tasks. It gives
you two ways to command the chassis:

- direct TCP control through the chassis API
- ROS-compatible wrappers and publishers for integration with the robot stack

## Core Purpose

Use this module when the task is:

- move to a named marker
- move to a target table or point
- move to an explicit `(x, y, theta)` pose
- inspect chassis status from Python

## Architecture

```text
navigation/
  chassis_client.py          Direct TCP client to the AGV controller
  run_navigation.py          Main CLI entrypoint
  ros_bridge/                ROS publishers / helper bridge nodes
  ros_packages/              Vendored AGV ROS package
  setup_nav_ws.sh            Build helper for the local nav workspace
```

### File Responsibilities

- `chassis_client.py`
  lowest-level TCP API for marker and coordinate commands
- `run_navigation.py`
  main user entrypoint for direct navigation
- `ros_bridge/navigation_bridge.py`
  helper class for publishing navigation commands into ROS topics
- `ros_bridge/agv_socket_bridge.py`
  ROS node that forwards AGV ROS commands to the TCP chassis socket
- `ros_bridge/README.md`
  ROS bridge usage and topic contract
- `ros_packages/rm_dual_arm_agv`
  vendored ROS package for AGV control
- `setup_nav_ws.sh`
  creates and builds `~/lt_nav_ws`

## Environments

- Direct TCP path:
  plain `python3`
- ROS path:
  `/usr/bin/python3` plus `source /opt/ros/noetic/setup.bash`

## Main Commands

### List markers

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
```

Effect:

- prints all known markers from the configured target set

### Query chassis status

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py status
```

Effect:

- reads the current base status through the direct TCP path

### Move to a named target

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

Parameters:

- `--name`: target alias defined in your navigation targets

Effect:

- sends the base to the named waypoint

### Move to a marker

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py marker --name pointc
```

Effect:

- uses marker-based movement through the chassis interface

### Move to explicit coordinates

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py \
  location --x 1.0 --y 0.5 --theta 0.0
```

Parameters:

- `--x`: map-frame x position
- `--y`: map-frame y position
- `--theta`: yaw in radians

## ROS Bringup Path

If you want ROS-based navigation integration:

```bash
bash /home/rm/Long_sequence_tasks/navigation/setup_nav_ws.sh
```

Then:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

### ROS navigation command demo

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```

Effect:

- publishes a ROS navigation command instead of using direct TCP

## Backend Choice

Use direct TCP when:

- you want the simplest path
- you do not need ROS topics in the middle
- you are integrating directly from Python

Use the ROS path when:

- you want topic-based integration
- you want other ROS nodes to observe or publish navigation actions
- your bringup already depends on the AGV ROS node
