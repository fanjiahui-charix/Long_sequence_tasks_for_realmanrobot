#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import CameraInfo, Image


class CaptureRgbdFrameError(RuntimeError):
    """Raised when one RGBD frame cannot be captured from ROS."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture one RGBD frame and camera intrinsics from ROS.")
    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--color-topic", default=None)
    parser.add_argument("--depth-topic", default=None)
    parser.add_argument("--info-topic", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    color_topic = args.color_topic or f"/{args.camera_name}/color/image_raw"
    depth_topic = args.depth_topic or f"/{args.camera_name}/aligned_depth_to_color/image_raw"
    info_topic = args.info_topic or f"/{args.camera_name}/color/camera_info"

    if not rospy.core.is_initialized():
        rospy.init_node("long_tasks_capture_rgbd_frame", anonymous=True, disable_signals=True)

    bridge = CvBridge()

    try:
        color_msg = rospy.wait_for_message(color_topic, Image, timeout=args.timeout)
        depth_msg = rospy.wait_for_message(depth_topic, Image, timeout=args.timeout)
        info_msg = rospy.wait_for_message(info_topic, CameraInfo, timeout=args.timeout)
    except Exception as exc:
        raise CaptureRgbdFrameError(
            "Timed out while waiting for RGBD capture.\n"
            f"color topic: {color_topic}\n"
            f"depth topic: {depth_topic}\n"
            f"info topic: {info_topic}"
        ) from exc

    color = bridge.imgmsg_to_cv2(color_msg, desired_encoding="bgr8")
    depth = bridge.imgmsg_to_cv2(depth_msg, desired_encoding="passthrough")
    depth = np.asarray(depth)
    if depth.ndim != 2:
        raise CaptureRgbdFrameError(f"Expected depth image to be 2D, got shape {depth.shape}")

    if np.issubdtype(depth.dtype, np.floating):
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
        depth = np.clip(np.round(depth * 1000.0), 0, np.iinfo(np.uint16).max).astype(np.uint16)
    elif depth.dtype != np.uint16:
        depth = np.clip(depth, 0, np.iinfo(np.uint16).max).astype(np.uint16)

    rgb_path = output_dir / "rgb.png"
    depth_path = output_dir / "depth.png"
    k_path = output_dir / "cam_K.txt"

    if not cv2.imwrite(str(rgb_path), color):
        raise CaptureRgbdFrameError(f"Failed to write RGB image to {rgb_path}")
    if not cv2.imwrite(str(depth_path), depth):
        raise CaptureRgbdFrameError(f"Failed to write depth image to {depth_path}")

    k_matrix = np.asarray(info_msg.K, dtype=np.float32).reshape(3, 3)
    np.savetxt(str(k_path), k_matrix, fmt="%.8f")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
