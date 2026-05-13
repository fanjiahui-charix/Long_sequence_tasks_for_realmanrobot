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

## ROS Path

The ROS bridge is still here for debugging or compatibility:

- `ros_bridge/navigation_bridge.py`
- `ros_bridge/run_navigation_demo.py`
- `ros_packages/rm_dual_arm_agv`
