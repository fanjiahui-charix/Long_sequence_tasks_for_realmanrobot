# Vision Grasp

This folder contains all perception, grasp-demo, and end-effector related code.

## Layout

```text
vision_grasp/
  demo/           Vision grasp demo scripts, configs, weights, docs
  ros_packages/   Vendored arm message and end-effector ROS packages
  end_effector_client.py
  run_grasp.py
```

Main demo documentation:

- `/home/rm/Long_sequence_tasks/vision_grasp/demo/README.md`

Recommended end-effector entry:

```bash
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py open
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py close
python3 /home/rm/Long_sequence_tasks/vision_grasp/run_grasp.py pick-demo
```
