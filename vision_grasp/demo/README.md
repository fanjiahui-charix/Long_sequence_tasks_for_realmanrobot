# Vision Grasp Demo

This folder contains a self-contained ROS1 demo for:

- D435 image + depth capture
- YOLO object detection
- camera-to-base TF conversion
- single-arm grasp execution
- Inspire two-finger gripper open/close
- dexterous hand open/close through the arm driver topics

For project use, prefer the repository entrypoint instead of calling the
individual smoke-test scripts directly:

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py open
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py close
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py pick-demo
```

It does not import the existing `robot_actions` or `robot_recognition` code.
The vendored ROS wrappers it uses live under:

- `/home/rm/Long_sequence_tasks/vision_grasp/ros_packages/rm_dual_arm_arm_msgs`
- `/home/rm/Long_sequence_tasks/vision_grasp/ros_packages/robot_end_effector`

It only relies on:

- ROS Noetic
- the running robot drivers and TF tree
- `rm_dual_arm_arm_msgs` from `Long_sequence_tasks/vision_grasp/ros_packages`
- `cv_bridge`
- `ultralytics`

## End Effector Modes

This folder now supports both:

- `inspire_gripper`: two-finger gripper
- `dexterous_hand`: five-finger hand through:
  - `/<arm>/rm_driver/Hand_SetAngle`
  - `/<arm>/rm_driver/Hand_SetSpeed`
  - `/<arm>/rm_driver/Hand_SetForce`

Your photo shows a five-finger hand, so for your robot you should use:

```text
end_effector_type: dexterous_hand
```

## Files

- `scripts/simple_vision_grasp_demo.py`
  Runs one local detect-and-grasp cycle.
- `scripts/gripper_smoke_test.py`
  Opens or closes the Inspire two-finger gripper only.
- `scripts/dexterous_hand_smoke_test.py`
  Opens or closes the five-finger dexterous hand only.
- `config/grasp_config.example.yaml`
  Example ROS parameters for the grasp demo.

## Vendored ROS Packages

To keep this repository readable without `rmc_dual_arm_robot`, the ROS wrapper
packages used by this demo were copied into:

```text
/home/rm/Long_sequence_tasks/vision_grasp/ros_packages
```

Build them in one grasp workspace:

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/setup_grasp_ws.sh
cd ~/lt_grasp_ws
source devel/setup.bash
```

If your robot already has the same packages installed elsewhere, this copy is
mainly for open-source completeness and code visibility.

## Startup

Start the robot drivers, TF tree, and camera first. A typical stack is:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
roslaunch robot_actions robot_actions_driver.launch end_effector:=inspire_gripper Arm_Type:=RM65 Arm_Dof:=6
```

Adjust `Arm_Type` and `Arm_Dof` if your robot is RM75 / 7 DOF.

The current demo still expects a running arm driver, TF tree, and camera stack.
What was removed is the source-code dependency on `rmc_dual_arm_robot` for
messages and end-effector wrappers.

## Gripper Test

Open:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/gripper_smoke_test.py _arm_ns:=l_arm _open:=true
```

Close:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/gripper_smoke_test.py _arm_ns:=l_arm _open:=false
```

## Dexterous Hand Test

Open:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/dexterous_hand_smoke_test.py _arm_ns:=l_arm _open:=true
```

Close:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/dexterous_hand_smoke_test.py _arm_ns:=l_arm _open:=false
```

If the preset does not match your hardware exactly, you can override the joint
array:

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/dexterous_hand_smoke_test.py \
  _arm_ns:=l_arm \
  _angles:="[0,0,0,0,0,1000]"
```

## Vision Grasp Demo

Example:

```bash
cd ~/rmc_dual_arm_robot
source devel/setup.bash
rosparam load /home/rm/Long_sequence_tasks/vision_grasp/demo/config/grasp_config.example.yaml /vision_grasp_demo
python3 /home/rm/Long_sequence_tasks/vision_grasp/demo/scripts/simple_vision_grasp_demo.py
```

The default behavior is:

1. Move the arm to a safe pre-grasp pose.
2. Open the gripper.
3. Detect the first matching object in the camera image.
4. Convert the detected 3D point from camera frame to base frame.
5. Move above the object.
6. Descend.
7. Close the gripper.
8. Lift the object.

## Important Notes

- This script does not include chassis motion.
- It uses a fixed grasp orientation from config.
- It assumes the object is reachable and roughly upright.
- It is safest to test with a soft object first.
- If the arm or camera TF is wrong, do not keep retrying blindly.

For the dexterous hand path, the default open/close joint arrays are a practical
starting point, not a universal truth. If the hand shape is wrong, tune the
arrays in `grasp_config.example.yaml`.
