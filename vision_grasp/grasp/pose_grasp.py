from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from vision_grasp.grasp.arm_motion_client import ArmMotionClient, ArmMotionError
from vision_grasp.grasp.end_effector_client import EndEffectorClient, EndEffectorControlError
from vision_grasp.integration.foundationpose_bridge import (
    FoundationPoseEstimate,
    FoundationPoseLoadError,
    load_foundationpose_estimate,
)


class PoseGraspError(RuntimeError):
    """Raised when a pose-based grasp execution fails."""


@dataclass
class PoseGraspConfig:
    arm_ns: str = "l_arm"
    base_frame: str = "base_left"
    camera_frame: str = "camera_middle"
    end_effector_type: str = "dexterous_hand"
    arm_speed: float = 0.1
    motion_timeout: float = 20.0
    home_pose_xyz: list[float] = field(default_factory=lambda: [0.166941, -0.246564, 0.079859])
    home_pose_rpy: list[float] = field(default_factory=lambda: [-2.135, 0.634, 2.254])
    pose_grasp_orientation_mode: str = "fixed_rpy"
    pose_grasp_rpy: list[float] = field(default_factory=lambda: [-2.135, 0.634, 2.254])
    pregrasp_offset_local: list[float] = field(default_factory=lambda: [0.0, 0.0, -0.12])
    retreat_offset_local: list[float] = field(default_factory=lambda: [0.0, 0.0, -0.18])
    object_grasp_transform: list[list[float]] = field(
        default_factory=lambda: [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    gripper_open_position: int = 1000
    gripper_pick_speed: int = 400
    gripper_pick_force: int = 300
    hand_speed: int = 400
    hand_force: int = 300
    hand_open_angles: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 1000])
    hand_close_angles: list[int] = field(default_factory=lambda: [1000, 1000, 1000, 1000, 1000, 0])
    foundationpose_pose_file: str = ""

    @classmethod
    def from_dict(cls, payload: dict) -> "PoseGraspConfig":
        defaults = cls()
        return cls(
            arm_ns=str(payload.get("arm_ns", defaults.arm_ns)),
            base_frame=str(payload.get("base_frame", defaults.base_frame)),
            camera_frame=str(payload.get("camera_frame", payload.get("camera_name", defaults.camera_frame))),
            end_effector_type=str(payload.get("end_effector_type", defaults.end_effector_type)),
            arm_speed=float(payload.get("arm_speed", defaults.arm_speed)),
            motion_timeout=float(payload.get("motion_timeout", defaults.motion_timeout)),
            home_pose_xyz=_vector3(payload.get("home_pose_xyz", defaults.home_pose_xyz), "home_pose_xyz"),
            home_pose_rpy=_vector3(payload.get("home_pose_rpy", defaults.home_pose_rpy), "home_pose_rpy"),
            pose_grasp_orientation_mode=str(
                payload.get("pose_grasp_orientation_mode", defaults.pose_grasp_orientation_mode)
            ),
            pose_grasp_rpy=_vector3(
                payload.get("pose_grasp_rpy", payload.get("grasp_rpy", defaults.pose_grasp_rpy)),
                "pose_grasp_rpy",
            ),
            pregrasp_offset_local=_vector3(
                payload.get("pregrasp_offset_local", defaults.pregrasp_offset_local),
                "pregrasp_offset_local",
            ),
            retreat_offset_local=_vector3(
                payload.get("retreat_offset_local", defaults.retreat_offset_local),
                "retreat_offset_local",
            ),
            object_grasp_transform=_matrix4(
                payload.get("object_grasp_transform", defaults.object_grasp_transform),
                "object_grasp_transform",
            ).tolist(),
            gripper_open_position=int(payload.get("gripper_open_position", defaults.gripper_open_position)),
            gripper_pick_speed=int(payload.get("gripper_pick_speed", defaults.gripper_pick_speed)),
            gripper_pick_force=int(payload.get("gripper_pick_force", defaults.gripper_pick_force)),
            hand_speed=int(payload.get("hand_speed", defaults.hand_speed)),
            hand_force=int(payload.get("hand_force", defaults.hand_force)),
            hand_open_angles=_int_list(payload.get("hand_open_angles", defaults.hand_open_angles), 6, "hand_open_angles"),
            hand_close_angles=_int_list(
                payload.get("hand_close_angles", defaults.hand_close_angles),
                6,
                "hand_close_angles",
            ),
            foundationpose_pose_file=str(payload.get("foundationpose_pose_file", defaults.foundationpose_pose_file)),
        )


def execute_pose_grasp_from_config(
    config_dict: dict,
    *,
    pose_file: str | None = None,
    camera_frame: str | None = None,
    object_label: str | None = None,
) -> dict:
    config = PoseGraspConfig.from_dict(config_dict)
    resolved_pose_file = pose_file or config.foundationpose_pose_file
    if not resolved_pose_file:
        raise PoseGraspError("pose-grasp requires a FoundationPose pose file.")

    resolved_camera_frame = camera_frame
    if not resolved_camera_frame and not str(resolved_pose_file).lower().endswith(".json"):
        resolved_camera_frame = config.camera_frame

    estimate = load_foundationpose_estimate(
        resolved_pose_file,
        camera_frame=resolved_camera_frame,
        object_label=object_label,
    )
    return execute_pose_grasp(config, estimate)


def execute_pose_grasp(config: PoseGraspConfig, estimate: FoundationPoseEstimate) -> dict:
    try:
        import rospy
        import tf
        import tf2_ros
    except ImportError as exc:
        raise PoseGraspError(
            "ROS Python packages are not available. Run inside a sourced ROS environment."
        ) from exc

    try:
        if not rospy.core.is_initialized():
            rospy.init_node("long_tasks_pose_grasp", anonymous=True, disable_signals=True)

        tf_buffer = tf2_ros.Buffer()
        _ = tf2_ros.TransformListener(tf_buffer)

        motion = ArmMotionClient(arm_ns=config.arm_ns, auto_init_node=False)
        hand = EndEffectorClient(
            arm_ns=config.arm_ns,
            end_effector_type=config.end_effector_type,
            auto_init_node=False,
        )

        rospy.sleep(1.0)

        transform = tf_buffer.lookup_transform(
            config.base_frame,
            estimate.camera_frame,
            rospy.Time(0),
            rospy.Duration(2.0),
        )
        t_base_camera = _transform_to_matrix(transform)
        t_base_object = np.matmul(t_base_camera, estimate.pose_matrix)
        t_object_grasp = _matrix4(config.object_grasp_transform, "object_grasp_transform")
        t_base_grasp_pose = np.matmul(t_base_object, t_object_grasp)

        grasp_xyz = t_base_grasp_pose[:3, 3].tolist()
        grasp_quaternion = _resolve_grasp_quaternion(
            tf_module=tf,
            t_base_grasp_pose=t_base_grasp_pose,
            orientation_mode=config.pose_grasp_orientation_mode,
            pose_grasp_rpy=config.pose_grasp_rpy,
        )

        t_base_grasp = _matrix_from_pose(tf, grasp_xyz, grasp_quaternion)
        t_base_pregrasp = np.matmul(t_base_grasp, _translation_matrix(config.pregrasp_offset_local))
        t_base_retreat = np.matmul(t_base_grasp, _translation_matrix(config.retreat_offset_local))

        home_quaternion = tf.transformations.quaternion_from_euler(*config.home_pose_rpy)

        if not motion.movej_pose(
            config.home_pose_xyz,
            home_quaternion,
            speed=config.arm_speed,
            timeout=config.motion_timeout,
        ):
            raise PoseGraspError("Failed to reach the home pose before pose grasp.")

        _open_end_effector(config, hand)

        if not motion.movej_pose(
            t_base_pregrasp[:3, 3].tolist(),
            grasp_quaternion,
            speed=config.arm_speed,
            timeout=config.motion_timeout,
        ):
            raise PoseGraspError("Failed to reach the pregrasp pose.")

        if not motion.movel_pose(
            grasp_xyz,
            grasp_quaternion,
            speed=config.arm_speed,
            timeout=config.motion_timeout,
        ):
            raise PoseGraspError("Failed to reach the grasp pose.")

        _close_end_effector(config, hand)

        if not motion.movel_pose(
            t_base_retreat[:3, 3].tolist(),
            grasp_quaternion,
            speed=config.arm_speed,
            timeout=config.motion_timeout,
        ):
            raise PoseGraspError("Failed to retreat after grasp.")

        return {
            "backend": "ros",
            "action": "pose_grasp",
            "arm_ns": config.arm_ns,
            "end_effector_type": config.end_effector_type,
            "base_frame": config.base_frame,
            "camera_frame": estimate.camera_frame,
            "object_label": estimate.object_label,
            "confidence": estimate.confidence,
            "pose_file": estimate.source_path,
            "orientation_mode": config.pose_grasp_orientation_mode,
            "object_pose_in_camera": estimate.pose_matrix.tolist(),
            "object_pose_in_base": t_base_object.tolist(),
            "grasp_pose_in_base": t_base_grasp.tolist(),
            "pregrasp_pose_in_base": t_base_pregrasp.tolist(),
            "retreat_pose_in_base": t_base_retreat.tolist(),
        }
    except (ArmMotionError, EndEffectorControlError, FoundationPoseLoadError) as exc:
        raise PoseGraspError(str(exc)) from exc


def _resolve_grasp_quaternion(
    *,
    tf_module,
    t_base_grasp_pose: np.ndarray,
    orientation_mode: str,
    pose_grasp_rpy: Sequence[float],
) -> list[float]:
    mode = orientation_mode.strip().lower()
    if mode == "fixed_rpy":
        return list(tf_module.transformations.quaternion_from_euler(*[float(v) for v in pose_grasp_rpy]))
    if mode == "object_pose":
        return list(tf_module.transformations.quaternion_from_matrix(t_base_grasp_pose))
    raise PoseGraspError(
        f"Unsupported pose_grasp_orientation_mode: {orientation_mode}. "
        "Use fixed_rpy or object_pose."
    )


def _open_end_effector(config: PoseGraspConfig, hand: EndEffectorClient) -> None:
    hand.open(
        open_position=config.gripper_open_position,
        hand_speed=config.hand_speed,
        hand_force=config.hand_force,
        hand_open_angles=config.hand_open_angles,
    )


def _close_end_effector(config: PoseGraspConfig, hand: EndEffectorClient) -> None:
    hand.close(
        pick_speed=config.gripper_pick_speed,
        pick_force=config.gripper_pick_force,
        hand_speed=config.hand_speed,
        hand_force=config.hand_force,
        hand_close_angles=config.hand_close_angles,
    )


def _transform_to_matrix(transform) -> np.ndarray:
    translation = transform.transform.translation
    rotation = transform.transform.rotation
    return _matrix_from_pose(
        tf_module=None,
        xyz=[translation.x, translation.y, translation.z],
        quaternion_xyzw=[rotation.x, rotation.y, rotation.z, rotation.w],
    )


def _matrix_from_pose(tf_module, xyz: Sequence[float], quaternion_xyzw: Sequence[float]) -> np.ndarray:
    if tf_module is not None:
        matrix = tf_module.transformations.quaternion_matrix(quaternion_xyzw)
    else:
        import tf

        matrix = tf.transformations.quaternion_matrix(quaternion_xyzw)
    matrix[:3, 3] = np.array(_vector3(xyz, "xyz"), dtype=float)
    return matrix


def _translation_matrix(offset_xyz: Sequence[float]) -> np.ndarray:
    matrix = np.eye(4, dtype=float)
    matrix[:3, 3] = np.array(_vector3(offset_xyz, "offset"), dtype=float)
    return matrix


def _vector3(values: Sequence[float], name: str) -> list[float]:
    if len(values) != 3:
        raise PoseGraspError(f"{name} must have exactly 3 values, got {len(values)}")
    return [float(v) for v in values]


def _int_list(values: Sequence[int], expected_len: int, name: str) -> list[int]:
    if len(values) != expected_len:
        raise PoseGraspError(f"{name} must have exactly {expected_len} values, got {len(values)}")
    return [int(v) for v in values]


def _matrix4(values: Sequence[Sequence[float]], name: str) -> np.ndarray:
    matrix = np.array(values, dtype=float)
    if matrix.shape != (4, 4):
        raise PoseGraspError(f"{name} must be a 4x4 matrix, got shape {matrix.shape}")
    return matrix
