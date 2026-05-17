# Navigation

This folder contains all mobile-base navigation code for `Long_sequence_tasks`.

## Layout

```text
navigation/
  direct_api/     Direct TCP chassis control
  ros_bridge/     ROS-topic wrappers for debugging and compatibility
  ros_packages/   Vendored rm_dual_arm_agv ROS package
  chassis_client.py
  run_navigation.py
```

## Recommended Entry

For project code and future LLM integration, use the local Python entrypoint:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

Direct marker command:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py marker --name pointc
```

Direct coordinate command:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py location --x 1.0 --y 0.5 --theta 0.0
```

This path uses the chassis TCP API directly and does not require `rostopic pub`.

Verified commands in the current environment:

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py status
```

## ROS Path

If you want to use the vendored ROS navigation package inside
`Long_sequence_tasks`, the runnable path is:

- `ros_bridge/navigation_bridge.py`
- `ros_bridge/run_navigation_demo.py`
- `ros_packages/rm_dual_arm_agv`

### Step 1: Build the navigation ROS workspace

You do not have to create `~/lt_nav_ws`.

There are two ways to run the ROS path.

### Option A: Use your existing ROS workspace

If your current robot workspace already contains `rm_dual_arm_agv`, just use it.

For example:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

Then in another terminal:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```

If you want pure ROS topic commands instead of the helper script:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"
```

### Option B: Create a small dedicated workspace

This is optional. I used it only to keep testing isolated from your main robot workspace.

Run this once:

```bash
bash /home/rm/Long_sequence_tasks/navigation/setup_nav_ws.sh
```

That creates a small catkin workspace:

```text
~/lt_nav_ws
```

### Step 2: Start the navigation ROS package

Open terminal 1:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

This node listens to:

- `/navigation_marker`
- `/navigation_location`
- `/navigation_move_cancel`

and forwards them to the chassis at `192.168.10.10:31001`.

### Step 3: Send a ROS navigation command

Open terminal 2:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```

That helper script is just a small ROS publisher wrapper.

It is equivalent in spirit to:

```bash
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"
```

I kept it because it is easier to integrate into your own Python code later.

### Move to a coordinate through ROS

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py \
  location --x 1.0 --y 0.5 --theta 0.0
```

### Cancel current movement through ROS

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py cancel
```

### Check that the ROS node is alive

If you are unsure whether the ROS package is running:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
rosnode list
rostopic list | grep navigation
```

You should see the chassis driver node and the navigation topics.

### Recommended choice

Use this when:

- you specifically want ROS topics
- you want compatibility with other ROS nodes
- you want your planner to switch to `LONG_TASKS_NAV_BACKEND=ros`

Use `navigation/run_navigation.py` when:

- you want the shortest path
- you do not need ROS in the middle
- you want direct TCP control from your own Python code

For your current setup, the simplest choices are:

1. Direct TCP:
   `python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py marker --name pointc`
2. Existing ROS workspace:
   `source ~/rmc_dual_arm_robot/devel/setup.bash` and then `roslaunch rm_dual_arm_agv agv_start.launch`
