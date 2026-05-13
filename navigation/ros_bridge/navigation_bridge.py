from __future__ import annotations

import json
import math
from typing import Dict, Optional


class RosNavigationError(RuntimeError):
    """Raised when ROS navigation integration cannot be used."""


class RosNavigationBridge:
    """Small helper around the existing AGV ROS topics."""

    def __init__(
        self,
        node_name: str = "long_tasks_navigation_bridge",
        auto_init_node: bool = True,
    ) -> None:
        try:
            import rospy
            from geometry_msgs.msg import PoseStamped
            from std_msgs.msg import String
        except ImportError as exc:
            raise RosNavigationError(
                "ROS Python packages are not available. "
                "Run inside a sourced ROS environment."
            ) from exc

        self.rospy = rospy
        self.String = String
        self.PoseStamped = PoseStamped

        if auto_init_node and not rospy.core.is_initialized():
            rospy.init_node(node_name, anonymous=True, disable_signals=True)

        self.marker_pub = rospy.Publisher("/navigation_marker", String, queue_size=10)
        self.location_pub = rospy.Publisher("/long_tasks/navigation_location_json", String, queue_size=10)
        self.cancel_pub = rospy.Publisher("/navigation_move_cancel", String, queue_size=10)
        self.goal_pub = rospy.Publisher("/move_base_simple/goal", PoseStamped, queue_size=10)

        rospy.sleep(0.3)

    def _yaw_to_quaternion(self, yaw: float) -> Dict[str, float]:
        half_yaw = yaw * 0.5
        return {
            "x": 0.0,
            "y": 0.0,
            "z": math.sin(half_yaw),
            "w": math.cos(half_yaw),
        }

    def navigate_to_marker(self, marker: str) -> Dict[str, object]:
        if not marker:
            raise RosNavigationError("marker must be a non-empty string")

        self.marker_pub.publish(self.String(data=marker))
        self.rospy.loginfo("Published /navigation_marker: %s", marker)
        return {"mode": "marker", "marker": marker}

    def navigate_to_location(self, x: float, y: float, theta: float) -> Dict[str, object]:
        payload = {
            "x": float(x),
            "y": float(y),
            "theta": float(theta),
        }

        self.location_pub.publish(self.String(data=json.dumps(payload)))
        self.rospy.loginfo(
            "Published /navigation_location: x=%.3f y=%.3f theta=%.3f",
            payload["x"],
            payload["y"],
            payload["theta"],
        )
        return {"mode": "location", "x": payload["x"], "y": payload["y"], "theta": payload["theta"]}

    def publish_rviz_goal(
        self,
        x: float,
        y: float,
        yaw: float,
        frame_id: str = "map",
    ) -> Dict[str, object]:
        msg = self.PoseStamped()
        msg.header.frame_id = frame_id
        msg.header.stamp = self.rospy.Time.now()
        msg.pose.position.x = float(x)
        msg.pose.position.y = float(y)
        msg.pose.position.z = 0.0

        quat = self._yaw_to_quaternion(float(yaw))
        msg.pose.orientation.x = quat["x"]
        msg.pose.orientation.y = quat["y"]
        msg.pose.orientation.z = quat["z"]
        msg.pose.orientation.w = quat["w"]

        self.goal_pub.publish(msg)
        self.rospy.loginfo(
            "Published /move_base_simple/goal: frame=%s x=%.3f y=%.3f yaw=%.3f",
            frame_id,
            msg.pose.position.x,
            msg.pose.position.y,
            yaw,
        )
        return {
            "mode": "rviz_goal",
            "frame_id": frame_id,
            "x": msg.pose.position.x,
            "y": msg.pose.position.y,
            "yaw": float(yaw),
        }

    def cancel_navigation(self, reason: Optional[str] = None) -> Dict[str, object]:
        self.cancel_pub.publish(self.String(data=reason or "cancel"))
        self.rospy.loginfo("Published /navigation_move_cancel")
        return {"mode": "cancel", "reason": reason or "cancel"}
