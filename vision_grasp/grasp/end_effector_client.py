from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


class EndEffectorControlError(RuntimeError):
    """Raised when the ROS end-effector interface cannot be used."""


def _clamp_1_1000(value: int) -> int:
    return int(max(1, min(1000, value)))


def _clamp_hand_angle(value: int) -> int:
    return int(max(-1, min(1000, value)))


@dataclass
class EndEffectorClient:
    arm_ns: str = "l_arm"
    end_effector_type: str = "dexterous_hand"
    auto_init_node: bool = True
    node_name: str = "long_tasks_end_effector"

    def __post_init__(self) -> None:
        try:
            import rospy
            from rm_dual_arm_arm_msgs.msg import (
                Gripper_Pick,
                Gripper_Set,
                Hand_Angle,
                Hand_Force,
                Hand_Speed,
            )
        except ImportError as exc:
            raise EndEffectorControlError(
                "ROS Python packages or rm_dual_arm_arm_msgs are not available. "
                "Run inside a sourced ROS environment."
            ) from exc

        self.rospy = rospy
        self.Gripper_Pick = Gripper_Pick
        self.Gripper_Set = Gripper_Set
        self.Hand_Angle = Hand_Angle
        self.Hand_Force = Hand_Force
        self.Hand_Speed = Hand_Speed

        self.arm_ns = self.arm_ns.strip("/")
        self.end_effector_type = self.end_effector_type.strip()

        if self.auto_init_node and not rospy.core.is_initialized():
            rospy.init_node(self.node_name, anonymous=True, disable_signals=True)

        self.gripper_set_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/Gripper_Set", Gripper_Set, queue_size=1
        )
        self.gripper_pick_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/Gripper_Pick", Gripper_Pick, queue_size=1
        )
        self.hand_angle_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/Hand_SetAngle", Hand_Angle, queue_size=1
        )
        self.hand_speed_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/Hand_SetSpeed", Hand_Speed, queue_size=1
        )
        self.hand_force_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/Hand_SetForce", Hand_Force, queue_size=1
        )

        rospy.sleep(0.5)

    def open(
        self,
        open_position: int = 1000,
        hand_speed: int = 400,
        hand_force: int = 300,
        hand_open_angles: Iterable[int] = (0, 0, 0, 0, 0, 1000),
    ) -> dict:
        if self.end_effector_type == "inspire_gripper":
            msg = self.Gripper_Set()
            msg.position = _clamp_1_1000(open_position)
            self.gripper_set_pub.publish(msg)
            self.rospy.loginfo("Published gripper open command to /%s/rm_driver/Gripper_Set", self.arm_ns)
            return {
                "backend": "ros",
                "arm_ns": self.arm_ns,
                "end_effector_type": self.end_effector_type,
                "action": "open",
                "position": msg.position,
            }

        if self.end_effector_type == "dexterous_hand":
            self._publish_hand_speed_force(hand_speed, hand_force)
            angles = self._publish_hand_angles(hand_open_angles)
            return {
                "backend": "ros",
                "arm_ns": self.arm_ns,
                "end_effector_type": self.end_effector_type,
                "action": "open",
                "angles": angles,
                "speed": _clamp_1_1000(hand_speed),
                "force": _clamp_1_1000(hand_force),
            }

        raise EndEffectorControlError(f"Unsupported end_effector_type: {self.end_effector_type}")

    def close(
        self,
        pick_speed: int = 400,
        pick_force: int = 300,
        hand_speed: int = 400,
        hand_force: int = 300,
        hand_close_angles: Iterable[int] = (1000, 1000, 1000, 1000, 1000, 0),
    ) -> dict:
        if self.end_effector_type == "inspire_gripper":
            msg = self.Gripper_Pick()
            msg.speed = _clamp_1_1000(pick_speed)
            msg.force = _clamp_1_1000(pick_force)
            self.gripper_pick_pub.publish(msg)
            self.rospy.loginfo("Published gripper close command to /%s/rm_driver/Gripper_Pick", self.arm_ns)
            return {
                "backend": "ros",
                "arm_ns": self.arm_ns,
                "end_effector_type": self.end_effector_type,
                "action": "close",
                "speed": msg.speed,
                "force": msg.force,
            }

        if self.end_effector_type == "dexterous_hand":
            self._publish_hand_speed_force(hand_speed, hand_force)
            angles = self._publish_hand_angles(hand_close_angles)
            return {
                "backend": "ros",
                "arm_ns": self.arm_ns,
                "end_effector_type": self.end_effector_type,
                "action": "close",
                "angles": angles,
                "speed": _clamp_1_1000(hand_speed),
                "force": _clamp_1_1000(hand_force),
            }

        raise EndEffectorControlError(f"Unsupported end_effector_type: {self.end_effector_type}")

    def set_hand_angles(
        self,
        angles: Iterable[int],
        hand_speed: int = 400,
        hand_force: int = 300,
    ) -> dict:
        if self.end_effector_type != "dexterous_hand":
            raise EndEffectorControlError("set_hand_angles() only applies to dexterous_hand")
        self._publish_hand_speed_force(hand_speed, hand_force)
        clamped = self._publish_hand_angles(angles)
        return {
            "backend": "ros",
            "arm_ns": self.arm_ns,
            "end_effector_type": self.end_effector_type,
            "action": "set_angles",
            "angles": clamped,
            "speed": _clamp_1_1000(hand_speed),
            "force": _clamp_1_1000(hand_force),
        }

    def _publish_hand_speed_force(self, hand_speed: int, hand_force: int) -> None:
        speed_msg = self.Hand_Speed()
        force_msg = self.Hand_Force()
        speed_msg.hand_speed = _clamp_1_1000(hand_speed)
        force_msg.hand_force = _clamp_1_1000(hand_force)
        self.hand_speed_pub.publish(speed_msg)
        self.hand_force_pub.publish(force_msg)
        self.rospy.sleep(0.3)

    def _publish_hand_angles(self, angles: Iterable[int]) -> List[int]:
        values = [_clamp_hand_angle(int(v)) for v in list(angles)]
        if len(values) != 6:
            raise EndEffectorControlError(f"Dexterous hand angle array must have 6 entries, got {len(values)}")
        msg = self.Hand_Angle()
        msg.hand_angle = values
        self.hand_angle_pub.publish(msg)
        self.rospy.loginfo(
            "Published dexterous hand command to /%s/rm_driver/Hand_SetAngle with angles=%s",
            self.arm_ns,
            values,
        )
        return values
