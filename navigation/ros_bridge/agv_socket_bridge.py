from __future__ import annotations

import json
import socket


CHASSIS_HOST = "192.168.10.10"
CHASSIS_PORT = 31001


def main() -> None:
    try:
        import rospy
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit(
            "ROS Python packages are not available. "
            "Run inside a sourced ROS environment."
        ) from exc

    chassis_host = rospy.get_param("~chassis_host", CHASSIS_HOST)
    chassis_port = int(rospy.get_param("~chassis_port", CHASSIS_PORT))

    rospy.init_node("long_tasks_agv_socket_bridge", anonymous=True)
    rospy.loginfo("Connecting to chassis %s:%s", chassis_host, chassis_port)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((chassis_host, chassis_port))

    feedback_pub = rospy.Publisher("/navigation_feedback", String, queue_size=10)

    def send_command(command: str) -> None:
        client.send(command.encode("utf-8"))
        rospy.loginfo("sent chassis command: %s", command)

    def on_marker(msg: String) -> None:
        marker = msg.data.strip()
        if not marker:
            rospy.logwarn("ignore empty marker")
            return
        send_command(f"/api/move?marker={marker}")

    def on_location_json(msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            x = float(payload["x"])
            y = float(payload["y"])
            theta = float(payload["theta"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            rospy.logerr("bad location payload: %s (%s)", msg.data, exc)
            return

        send_command(f"/api/move?location={x},{y},{theta}")

    def on_cancel(msg: String) -> None:
        del msg
        send_command("/api/move/cancel")

    rospy.Subscriber("/navigation_marker", String, on_marker)
    rospy.Subscriber("/long_tasks/navigation_location_json", String, on_location_json)
    rospy.Subscriber("/navigation_move_cancel", String, on_cancel)

    client.settimeout(0.2)

    while not rospy.is_shutdown():
        try:
            part = client.recv(1024).decode()
            if part:
                feedback_pub.publish(part)
                rospy.loginfo("recv chassis feedback: %s", part.strip())
        except socket.timeout:
            continue


if __name__ == "__main__":
    main()
