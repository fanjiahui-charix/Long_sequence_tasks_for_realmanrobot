# Navigation ROS Packages

This folder contains the vendored ROS navigation package used by this
repository:

- `rm_dual_arm_agv`

You do not have to create `~/lt_nav_ws`.

If your existing robot workspace already has `rm_dual_arm_agv`, you can simply:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

Then send `pointc` from another terminal:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```

Or use pure ROS:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"
```

If you want an isolated workspace for just this vendored package, build it with:

```bash
bash /home/rm/Long_sequence_tasks/navigation/setup_nav_ws.sh
```

Then start it in terminal 1:

```bash
cd ~/lt_nav_ws
source devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

Then send `pointc` from terminal 2:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_nav_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/navigation/ros_bridge/run_navigation_demo.py marker --name pointc
```
