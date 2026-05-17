# Vision Grasp

This folder contains all perception, grasp-demo, and end-effector related code.

## Layout

```text
vision_grasp/
  demo/           Vision grasp demo scripts, configs, weights, docs
  ros_packages/   Vendored arm driver, message, and end-effector ROS packages
  end_effector_client.py
  run_grasp.py
  start_hand_driver.sh
```

Main demo documentation:

- `/home/rm/Long_sequence_tasks/vision_grasp/demo/README.md`

Recommended end-effector entry:

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py open
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py close
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py pick-demo
```

Capture one current RGB image from ROS:

```bash
source /opt/ros/noetic/setup.bash
source ~/rmc_dual_arm_robot/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/capture_rgb_image.py \
  --camera-name camera_middle \
  --output /tmp/long_tasks_current_rgb.jpg
```

For safe verification without moving hardware, the ROS package build path was
checked with:

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/setup_grasp_ws.sh
```

If you want to use only `Long_sequence_tasks` to bring up the low-level hand
path, start the vendored arm driver from this repository:

```bash
bash /home/rm/Long_sequence_tasks/vision_grasp/start_hand_driver.sh RM65 6 aoyi_hand
```

Then in another terminal:

```bash
source /opt/ros/noetic/setup.bash
source ~/lt_grasp_ws/devel/setup.bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py \
  --end-effector-type dexterous_hand \
  open

python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py \
  --end-effector-type dexterous_hand \
  set-angles --angles "[0,0,0,0,0,1000]"


```
