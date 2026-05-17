# Vision Grasp ROS Packages

This folder contains the vendored ROS packages used by the grasp side:

- `rm_dual_arm_arm_driver`
- `rm_dual_arm_arm_msgs`
- `robot_end_effector`

Build them with:

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/setup_grasp_ws.sh
cd ~/lt_grasp_ws
source devel/setup.bash
```

To start the arm driver and end-effector node from the vendored packages:

```bash
roslaunch rm_dual_arm_arm_driver rm_dual_arm_arm_driver.launch \
  Arm_Type:=RM65 Arm_Dof:=6 end_effector:=aoyi_hand
```
