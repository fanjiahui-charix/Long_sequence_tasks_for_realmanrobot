#!/usr/bin/env bash
set -euo pipefail

cd ~/catkin_ws
source devel/setup.bash

# Start this in one terminal:
# roslaunch rm_dual_arm_agv agv_start.launch

# Move to one marker:
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"

# Move to a map coordinate:
# rostopic pub -1 /navigation_location rm_dual_arm_agv/NavigationLocation "{x: 1.0, y: 0.5, theta: 0.0}"

# Cancel active navigation:
# rostopic pub -1 /navigation_move_cancel std_msgs/String "data: ''"

# Query status:
# rostopic pub -1 /navigation_get_robot_status std_msgs/String "data: ''"

