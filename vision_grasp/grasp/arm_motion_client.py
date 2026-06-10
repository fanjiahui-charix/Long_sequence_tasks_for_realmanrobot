from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence


class ArmMotionError(RuntimeError):
    """Raised when the ROS arm motion interface cannot be used."""


def _as_xyz(values: Sequence[float]) -> list[float]:
    if len(values) != 3:
        raise ArmMotionError(f"Expected 3 position values, got {len(values)}")
    return [float(v) for v in values]


def _as_quaternion(values: Sequence[float]) -> list[float]:
    if len(values) != 4:
        raise ArmMotionError(f"Expected 4 quaternion values, got {len(values)}")
    return [float(v) for v in values]


@dataclass
class ArmMotionClient:
    arm_ns: str = "l_arm"
    auto_init_node: bool = True
    node_name: str = "long_tasks_arm_motion"

    def __post_init__(self) -> None:
        try:
            import rospy
            import tf
            from rm_dual_arm_arm_msgs.msg import MoveJ_P, MoveL, Plan_State
        except ImportError as exc:
            raise ArmMotionError(
                "ROS Python packages or rm_dual_arm_arm_msgs are not available. "
                "Run inside a sourced ROS environment."
            ) from exc

        self.rospy = rospy
        self.tf = tf
        self.MoveJ_P = MoveJ_P
        self.MoveL = MoveL
        self.Plan_State = Plan_State

        self.arm_ns = self.arm_ns.strip("/")
        self.plan_ok = True

        if self.auto_init_node and not rospy.core.is_initialized():
            rospy.init_node(self.node_name, anonymous=True, disable_signals=True)

        self.movejp_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/MoveJ_P_Cmd",
            MoveJ_P,
            queue_size=1,
        )
        self.movel_pub = rospy.Publisher(
            f"/{self.arm_ns}/rm_driver/MoveL_Cmd",
            MoveL,
            queue_size=1,
        )
        rospy.Subscriber(
            f"/{self.arm_ns}/rm_driver/Plan_State",
            Plan_State,
            self._plan_state_cb,
            queue_size=1,
        )

        rospy.sleep(0.5)

    def _plan_state_cb(self, msg) -> None:
        self.plan_ok = bool(msg.state)

    def movej_pose(
        self,
        xyz: Sequence[float],
        quaternion_xyzw: Sequence[float],
        speed: float,
        timeout: float = 20.0,
    ) -> bool:
        return self._publish_pose_command(
            publisher=self.movejp_pub,
            msg_type=self.MoveJ_P,
            xyz=xyz,
            quaternion_xyzw=quaternion_xyzw,
            speed=speed,
            timeout=timeout,
        )

    def movel_pose(
        self,
        xyz: Sequence[float],
        quaternion_xyzw: Sequence[float],
        speed: float,
        timeout: float = 20.0,
    ) -> bool:
        return self._publish_pose_command(
            publisher=self.movel_pub,
            msg_type=self.MoveL,
            xyz=xyz,
            quaternion_xyzw=quaternion_xyzw,
            speed=speed,
            timeout=timeout,
        )

    def movej_rpy(
        self,
        xyz: Sequence[float],
        rpy: Sequence[float],
        speed: float,
        timeout: float = 20.0,
    ) -> bool:
        quaternion = self.tf.transformations.quaternion_from_euler(*[float(v) for v in rpy])
        return self.movej_pose(xyz, quaternion, speed=speed, timeout=timeout)

    def movel_rpy(
        self,
        xyz: Sequence[float],
        rpy: Sequence[float],
        speed: float,
        timeout: float = 20.0,
    ) -> bool:
        quaternion = self.tf.transformations.quaternion_from_euler(*[float(v) for v in rpy])
        return self.movel_pose(xyz, quaternion, speed=speed, timeout=timeout)

    def _publish_pose_command(
        self,
        publisher,
        msg_type,
        xyz: Sequence[float],
        quaternion_xyzw: Sequence[float],
        speed: float,
        timeout: float,
    ) -> bool:
        position = _as_xyz(xyz)
        quaternion = _as_quaternion(quaternion_xyzw)

        msg = msg_type()
        msg.Pose.position.x = position[0]
        msg.Pose.position.y = position[1]
        msg.Pose.position.z = position[2]
        msg.Pose.orientation.x = quaternion[0]
        msg.Pose.orientation.y = quaternion[1]
        msg.Pose.orientation.z = quaternion[2]
        msg.Pose.orientation.w = quaternion[3]
        msg.speed = float(speed)
        msg.trajectory_connect = 0

        self.plan_ok = False
        publisher.publish(msg)
        return self._wait_plan(timeout)

    def _wait_plan(self, timeout: float) -> bool:
        start = time.time()
        while time.time() - start < timeout and not self.rospy.is_shutdown():
            if self.plan_ok:
                return True
            self.rospy.sleep(0.2)
        return False
