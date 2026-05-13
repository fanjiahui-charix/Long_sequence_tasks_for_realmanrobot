# Chassis Notes

The current platform matches the local dual-arm robot documentation, not the
Woosh `169.254.128.2:8080` data sheet.

Confirmed active endpoints:

- `192.168.10.10:9001`: web monitor and map UI.
- `192.168.10.10:9090`: rosbridge websocket used by the web UI.
- `192.168.10.10:31001`: TCP chassis API used by `rm_dual_arm_agv`.

Closed or not used on this platform:

- `192.168.10.10:8080`
- `192.168.10.10:5001`
- `169.254.128.2:8080`

Important API commands:

- `/api/robot_status`
- `/api/markers/query_list`
- `/api/markers/query_brief`
- `/api/markers/insert?name=NAME&type=0`
- `/api/markers/insert_by_pose?name=NAME&x=X&y=Y&theta=THETA&floor=FLOOR&type=0`
- `/api/markers/delete?name=NAME`
- `/api/move?marker=NAME`
- `/api/move?location=X,Y,THETA`
- `/api/move?markers=M1,M2,M3&distance_tolerance=0.5&count=1`
- `/api/move/cancel`

Marker setup is safer in the web UI because the operator can inspect the map
position and arrow heading directly.

