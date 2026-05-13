# Chassis Navigation

Minimal tools for controlling the Yunji/WATER mobile chassis from the AGX
controller.

This robot uses:

- AGX controller IP: `192.168.10.100`
- Chassis IP: `192.168.10.10`
- Web console: `http://192.168.10.10:9001`
- Chassis TCP API: `192.168.10.10:31001`

The web console is still the best place to create maps, correct localization,
and add/edit marker points. The scripts here are for sending navigation commands
after the map and marker points are ready.

## Quick Check

```bash
ping 192.168.10.10
python3 scripts/chassis_api.py status
python3 scripts/chassis_api.py markers
```

## Move To A Marker

Use the marker name shown in the web console, without the `[0]` type suffix.

```bash
python3 scripts/chassis_api.py move-marker pointc
```

Cancel the current move:

```bash
python3 scripts/chassis_api.py cancel
```

## Move To A Coordinate

Coordinates are in the active map frame.

```bash
python3 scripts/chassis_api.py move-location 1.0 0.5 0.0
```

## Add Marker Points

Recommended workflow: add points in the web console because you can see the map
and the orientation arrow.

If you still want to use the API:

```bash
python3 scripts/chassis_api.py insert-current table_1 --type 0
python3 scripts/chassis_api.py insert-pose table_2 --x 1.0 --y 0.5 --theta 0.0 --floor 3 --type 0
```

Delete a marker:

```bash
python3 scripts/chassis_api.py delete-marker table_1
```

## ROS Wrapper Path

The existing robot workspace already has a ROS wrapper:

```bash
cd ~/catkin_ws
source devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

Then publish a marker command from another terminal:

```bash
cd ~/catkin_ws
source devel/setup.bash
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"
```

Useful topics:

- `/navigation_marker`: move to a named marker.
- `/navigation_location`: move to `x, y, theta`.
- `/navigation_multipoint`: move through comma-separated markers.
- `/navigation_move_cancel`: cancel active movement.
- `/navigation_get_robot_status`: query global chassis status.
- `/navigation_feedback`: feedback from the chassis API.

## Startup Checklist

Before sending navigation commands:

- Open `http://192.168.10.10:9001`.
- Confirm the correct map is loaded.
- Confirm the robot icon matches the real robot position and heading.
- Correct localization in the web console if it is wrong.
- Confirm soft stop and hard stop are not active.
- Confirm the target marker exists and is reachable.

Manual correction is not required every boot if the robot starts in the same
place and localization is already accurate. If the real robot and map icon do
not match, correct it before navigating.

