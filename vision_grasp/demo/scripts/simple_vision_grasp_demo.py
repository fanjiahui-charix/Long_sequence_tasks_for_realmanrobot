#!/usr/bin/env python3
"""Single-arm local YOLO + depth grasp demo for the Inspire gripper."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import rospy
import tf
import tf2_ros
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, Pose
from rm_dual_arm_arm_msgs.msg import (
    Gripper_Pick,
    Gripper_Set,
    Hand_Angle,
    Hand_Force,
    Hand_Speed,
    MoveJ_P,
    MoveL,
    Plan_State,
)
from sensor_msgs.msg import CameraInfo, Image
from ultralytics import YOLO


@dataclass
class Detection3D:
    label: str
    confidence: float
    point_camera: list[float]


class ArmClient:
    def __init__(self, arm_ns: str, end_effector_type: str):
        self.arm_ns = arm_ns.strip("/")
        self.end_effector_type = end_effector_type
        self.plan_ok = True

        self.movejp_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/MoveJ_P_Cmd", MoveJ_P, queue_size=1)
        self.movel_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/MoveL_Cmd", MoveL, queue_size=1)
        self.gripper_set_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/Gripper_Set", Gripper_Set, queue_size=1)
        self.gripper_pick_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/Gripper_Pick", Gripper_Pick, queue_size=1)
        self.hand_angle_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/Hand_SetAngle", Hand_Angle, queue_size=1)
        self.hand_speed_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/Hand_SetSpeed", Hand_Speed, queue_size=1)
        self.hand_force_pub = rospy.Publisher(f"/{self.arm_ns}/rm_driver/Hand_SetForce", Hand_Force, queue_size=1)

        rospy.Subscriber(f"/{self.arm_ns}/rm_driver/Plan_State", Plan_State, self._plan_state_cb, queue_size=1)

    def _plan_state_cb(self, msg: Plan_State) -> None:
        self.plan_ok = msg.state

    def open_gripper(self, position: int) -> None:
        if self.end_effector_type == "dexterous_hand":
            raise RuntimeError("open_gripper() was called for dexterous_hand.")
        msg = Gripper_Set()
        msg.position = max(1, min(1000, position))
        self.gripper_set_pub.publish(msg)
        rospy.sleep(2.0)

    def close_gripper(self, speed: int, force: int) -> None:
        if self.end_effector_type == "dexterous_hand":
            raise RuntimeError("close_gripper() was called for dexterous_hand.")
        msg = Gripper_Pick()
        msg.speed = max(1, min(1000, speed))
        msg.force = max(1, min(1000, force))
        self.gripper_pick_pub.publish(msg)
        rospy.sleep(2.0)

    def set_hand_speed_force(self, speed: int, force: int) -> None:
        speed_msg = Hand_Speed()
        force_msg = Hand_Force()
        speed_msg.hand_speed = max(1, min(1000, speed))
        force_msg.hand_force = max(1, min(1000, force))
        self.hand_speed_pub.publish(speed_msg)
        self.hand_force_pub.publish(force_msg)
        rospy.sleep(0.5)

    def set_hand_angles(self, angles: list[int]) -> None:
        msg = Hand_Angle()
        if len(angles) != 6:
            raise ValueError("Dexterous hand angle array must have 6 entries.")
        msg.hand_angle = [int(max(-1, min(1000, angle))) for angle in angles]
        self.hand_angle_pub.publish(msg)
        rospy.sleep(2.0)

    def movej_p(self, xyz: list[float], rpy: list[float], speed: float, timeout: float = 20.0) -> bool:
        msg = MoveJ_P()
        msg.Pose.position.x = xyz[0]
        msg.Pose.position.y = xyz[1]
        msg.Pose.position.z = xyz[2]
        qx, qy, qz, qw = tf.transformations.quaternion_from_euler(rpy[0], rpy[1], rpy[2])
        msg.Pose.orientation.x = qx
        msg.Pose.orientation.y = qy
        msg.Pose.orientation.z = qz
        msg.Pose.orientation.w = qw
        msg.speed = speed
        msg.trajectory_connect = 0

        self.plan_ok = False
        self.movejp_pub.publish(msg)
        return self._wait_plan(timeout)

    def movel(self, xyz: list[float], rpy: list[float], speed: float, timeout: float = 20.0) -> bool:
        msg = MoveL()
        msg.Pose.position.x = xyz[0]
        msg.Pose.position.y = xyz[1]
        msg.Pose.position.z = xyz[2]
        qx, qy, qz, qw = tf.transformations.quaternion_from_euler(rpy[0], rpy[1], rpy[2], axes="rxyz")
        msg.Pose.orientation.x = qx
        msg.Pose.orientation.y = qy
        msg.Pose.orientation.z = qz
        msg.Pose.orientation.w = qw
        msg.speed = speed
        msg.trajectory_connect = 0

        self.plan_ok = False
        self.movel_pub.publish(msg)
        return self._wait_plan(timeout)

    def _wait_plan(self, timeout: float) -> bool:
        start = time.time()
        while time.time() - start < timeout and not rospy.is_shutdown():
            if self.plan_ok:
                return True
            rospy.sleep(0.2)
        return False


class YoloDepthDetector:
    def __init__(self, weights_path: str, confidence: float, annotated_topic: str):
        self.bridge = CvBridge()
        self.model = YOLO(weights_path)
        self.confidence = confidence
        self.annotated_pub = rospy.Publisher(annotated_topic, Image, queue_size=1)

    def detect(self, camera_name: str, target_label: str, timeout: float) -> Optional[Detection3D]:
        color_topic = f"/{camera_name}/color/image_raw"
        depth_topic = f"/{camera_name}/aligned_depth_to_color/image_raw"
        info_topic = f"/{camera_name}/color/camera_info"

        camera_info = rospy.wait_for_message(info_topic, CameraInfo, timeout=2.0)
        fx = camera_info.K[0]
        fy = camera_info.K[4]
        cx = camera_info.K[2]
        cy = camera_info.K[5]

        deadline = time.time() + timeout
        while time.time() < deadline and not rospy.is_shutdown():
            color_msg = rospy.wait_for_message(color_topic, Image, timeout=1.0)
            depth_msg = rospy.wait_for_message(depth_topic, Image, timeout=1.0)

            color = self.bridge.imgmsg_to_cv2(color_msg, "bgr8")
            depth = self.bridge.imgmsg_to_cv2(depth_msg, "16UC1")
            results = self.model.predict(color, conf=self.confidence, verbose=False)
            if not results:
                continue

            result = results[0]
            annotated = result.plot()
            self.annotated_pub.publish(self.bridge.cv2_to_imgmsg(annotated, "bgr8"))

            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                label = str(result.names[cls_id])
                score = float(boxes.conf[i].item())
                if target_label and label != target_label:
                    continue

                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                u = int((x1 + x2) / 2)
                v = int((y1 + y2) / 2)
                if not (0 <= v < depth.shape[0] and 0 <= u < depth.shape[1]):
                    continue

                depth_mm = int(depth[v, u])
                if depth_mm <= 0:
                    continue

                z = depth_mm / 1000.0
                x = (u - cx) * z / fx
                y = (v - cy) * z / fy
                return Detection3D(label=label, confidence=score, point_camera=[x, y, z])

        return None


class VisionGraspDemo:
    def __init__(self):
        self.arm_ns = rospy.get_param("~arm_ns", "l_arm")
        self.base_frame = rospy.get_param("~base_frame", "base_left")
        self.camera_name = rospy.get_param("~camera_name", "camera_middle")
        self.end_effector_type = rospy.get_param("~end_effector_type", "dexterous_hand")
        self.target_label = rospy.get_param("~target_label", "")
        self.weights_path = rospy.get_param("~weights_path")
        self.detection_confidence = float(rospy.get_param("~detection_confidence", 0.45))
        self.detection_timeout = float(rospy.get_param("~detection_timeout", 20.0))
        self.annotated_topic = rospy.get_param("~annotated_topic", "/vision_grasp_demo/detect_image")

        self.grasp_rpy = list(rospy.get_param("~grasp_rpy"))
        self.home_pose_xyz = list(rospy.get_param("~home_pose_xyz"))
        self.home_pose_rpy = list(rospy.get_param("~home_pose_rpy"))
        self.pregrasp_offset_xyz = np.array(rospy.get_param("~pregrasp_offset_xyz"), dtype=float)
        self.grasp_offset_xyz = np.array(rospy.get_param("~grasp_offset_xyz"), dtype=float)
        self.retreat_offset_xyz = np.array(rospy.get_param("~retreat_offset_xyz"), dtype=float)
        self.arm_speed = float(rospy.get_param("~arm_speed", 0.1))
        self.gripper_open_position = int(rospy.get_param("~gripper_open_position", 1000))
        self.gripper_pick_speed = int(rospy.get_param("~gripper_pick_speed", 400))
        self.gripper_pick_force = int(rospy.get_param("~gripper_pick_force", 300))
        self.hand_speed = int(rospy.get_param("~hand_speed", 400))
        self.hand_force = int(rospy.get_param("~hand_force", 300))
        self.hand_open_angles = list(rospy.get_param("~hand_open_angles", [0, 0, 0, 0, 0, 1000]))
        self.hand_close_angles = list(rospy.get_param("~hand_close_angles", [1000, 1000, 1000, 1000, 1000, 0]))

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)

        self.arm = ArmClient(self.arm_ns, self.end_effector_type)
        self.detector = YoloDepthDetector(self.weights_path, self.detection_confidence, self.annotated_topic)

    def run(self) -> None:
        rospy.sleep(1.0)
        rospy.loginfo("Moving to home pose.")
        if not self.arm.movej_p(self.home_pose_xyz, self.home_pose_rpy, self.arm_speed):
            rospy.logerr("Failed to reach the home pose.")
            return

        rospy.loginfo("Opening the end effector.")
        self._open_end_effector()

        rospy.loginfo("Running local YOLO detection.")
        detection = self.detector.detect(self.camera_name, self.target_label, self.detection_timeout)
        if detection is None:
            rospy.logerr("No valid detection was found.")
            return

        rospy.loginfo(
            "Detected %s with confidence %.3f at camera coordinates %s",
            detection.label,
            detection.confidence,
            detection.point_camera,
        )

        point_base = self._camera_point_to_base(detection.point_camera)
        rospy.loginfo("Target in %s: %s", self.base_frame, point_base)

        pregrasp_xyz = (np.array(point_base) + self.pregrasp_offset_xyz).tolist()
        grasp_xyz = (np.array(point_base) + self.grasp_offset_xyz).tolist()
        retreat_xyz = (np.array(point_base) + self.retreat_offset_xyz).tolist()

        rospy.loginfo("Moving to pregrasp pose.")
        if not self.arm.movej_p(pregrasp_xyz, self.grasp_rpy, self.arm_speed):
            rospy.logerr("Failed to reach the pregrasp pose.")
            return

        rospy.loginfo("Descending to grasp pose.")
        if not self.arm.movel(grasp_xyz, self.grasp_rpy, self.arm_speed):
            rospy.logerr("Failed to reach the grasp pose.")
            return

        rospy.loginfo("Closing the end effector.")
        self._close_end_effector()

        rospy.loginfo("Retreating with the object.")
        if not self.arm.movel(retreat_xyz, self.grasp_rpy, self.arm_speed):
            rospy.logerr("Failed to retreat after grasp.")
            return

        rospy.loginfo("Grasp cycle finished.")

    def _open_end_effector(self) -> None:
        if self.end_effector_type == "inspire_gripper":
            self.arm.open_gripper(self.gripper_open_position)
            return
        if self.end_effector_type == "dexterous_hand":
            self.arm.set_hand_speed_force(self.hand_speed, self.hand_force)
            self.arm.set_hand_angles(self.hand_open_angles)
            return
        raise ValueError(f"Unsupported end_effector_type: {self.end_effector_type}")

    def _close_end_effector(self) -> None:
        if self.end_effector_type == "inspire_gripper":
            self.arm.close_gripper(self.gripper_pick_speed, self.gripper_pick_force)
            return
        if self.end_effector_type == "dexterous_hand":
            self.arm.set_hand_speed_force(self.hand_speed, self.hand_force)
            self.arm.set_hand_angles(self.hand_close_angles)
            return
        raise ValueError(f"Unsupported end_effector_type: {self.end_effector_type}")

    def _camera_point_to_base(self, xyz_camera: list[float]) -> list[float]:
        source = PointStamped()
        source.header.frame_id = self.camera_name
        source.header.stamp = rospy.Time(0)
        source.point.x = xyz_camera[0]
        source.point.y = xyz_camera[1]
        source.point.z = xyz_camera[2]

        target = self.tf_buffer.transform(source, self.base_frame, rospy.Duration(1.0))
        return [target.point.x, target.point.y, target.point.z]


def main():
    rospy.init_node("simple_vision_grasp_demo", anonymous=True)
    demo = VisionGraspDemo()
    demo.run()


if __name__ == "__main__":
    main()
