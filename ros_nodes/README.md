# ROS Integration Notes

## Three layers

1. `/opt/ros/noetic/...`
   Official ROS packages installed by apt, such as `rviz`, `map_server`, `amcl`, `rospy`.
   You normally do not edit these files directly.

2. `/home/rm/catkin_ws/src/...`
   Your robot workspace packages, such as:
   - `rm_dual_arm_agv`
   - `rm_dual_arm_description`
   - `rm_dual_arm_moveit`

3. `/home/rm/Long sequence tasks/...`
   Your high-level planning and execution code.
   This folder should hold the LLM planner, task executor, and thin ROS wrappers.

## What this folder now contains

- `navigation_bridge.py`
  Publish navigation commands to the existing AGV topics.
- `run_navigation_demo.py`
  A quick command-line test sender.
- `agv_socket_bridge.py`
  A self-contained ROS-to-chassis bridge moved into `Long sequence tasks`.

## Recommended implementation path

### Phase 1: First make navigation usable

Use the self-contained AGV bridge in this folder:

```bash
source /opt/ros/noetic/setup.bash
roscore
python "/home/rm/Long sequence tasks/ros_nodes/agv_socket_bridge.py"
```

Then test one marker command from this folder:

```bash
python "/home/rm/Long sequence tasks/ros_nodes/run_navigation_demo.py" marker --name dianA
```

Or test one coordinate command:

```bash
python "/home/rm/Long sequence tasks/ros_nodes/run_navigation_demo.py" location --x 1.0 --y 0.5 --theta 0.0
```

### Phase 2: RViz visualization

You already have a robot RViz launch:

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws/devel/setup.bash
roslaunch rm_dual_arm_description load_robot.launch
```

This gives you robot model visualization in RViz.

Important:
The self-contained bridge in this folder uses:
- `/navigation_marker`
- `/long_tasks/navigation_location_json`
- `/navigation_move_cancel`

That is still different from the standard ROS navigation stack.
So RViz can show the robot model now, but RViz's `2D Nav Goal` only becomes a full navigation tool
when you also have a standard stack listening to `/move_base_simple/goal`.

### Phase 3: Mapping and standard ROS navigation

For your current workspace, the fastest MVP is:

1. Use the vendor web mapping / saved marker points for real robot movement.
2. Use RViz for visualization.
3. Use `Long sequence tasks` to send the high-level navigation command.

That is the shortest path to a working robot demo.

If later you want full ROS SLAM + `2D Nav Goal` + `map_server` + `amcl`, you need a complete navigation stack package.
Those runtime packages may be installed under `/opt/ros/noetic`, but you still need the robot-specific launch and config files
in your own workspace.

## Independence from `catkin_ws`

You asked to reduce dependency on `/home/rm/catkin_ws`.

Current status:

- Navigation command bridge:
  now can run directly from `Long sequence tasks`
- High-level planner / executor:
  already lives in `Long sequence tasks`
- RViz robot model:
  still depends on your robot description package in `catkin_ws`
- Full SLAM / move_base / amcl stack:
  still depends on ROS packages and robot-specific configs

So this folder can become the standalone high-level package,
but RViz model and full navigation stack are not fully portable yet.

## Skill integration

`skills/navigation_skill.py` can now call ROS directly when you enable:

```bash
export LONG_TASKS_USE_ROS_NAV=1
```

It reads target-to-marker mappings from:

```text
/home/rm/Long sequence tasks/configs/nav_targets.yaml
```

Edit that file so your semantic targets match your real marker names.

## Suggested next steps

1. Confirm marker navigation works through `run_navigation_demo.py`.
2. Edit `configs/nav_targets.yaml` to match your real map markers.
3. Run the task executor with `LONG_TASKS_USE_ROS_NAV=1`.
4. After that, decide whether to keep using the vendor map as MVP or add a full ROS SLAM/navigation stack.
