#!/usr/bin/env python3
"""ROS-side worker. Uses only the existing ROS environment, never Pydantic.

No module imports ROS or touches a robot until main() is explicitly invoked.
Transform is read-only. Grasp additionally requires --enable-hardware.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["transform", "grasp"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--pose-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--enable-hardware", action="store_true")
    args = parser.parse_args()
    if args.command == "grasp" and not args.enable_hardware:
        raise SystemExit("grasp requires explicit --enable-hardware")
    import yaml

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    # Never silently substitute left/right arm, camera frame or motion parameters.
    required = [
        "arm_ns",
        "base_frame",
        "camera_frame",
        "end_effector_type",
        "home_pose_xyz",
        "home_pose_rpy",
        "pose_grasp_rpy",
        "arm_speed",
        "motion_timeout",
        "pregrasp_offset_local",
        "retreat_offset_local",
        "object_grasp_transform",
    ]
    if any(key not in config for key in required):
        raise SystemExit("confirmed grasp configuration is incomplete")
    if args.command == "grasp":
        from vision_grasp.grasp.pose_grasp import execute_pose_grasp_from_config

        result = execute_pose_grasp_from_config(config, pose_file=args.pose_file)
        result["sequence_complete"] = True
    else:
        import numpy as np
        import rospy
        import tf2_ros
        from vision_grasp.integration.foundationpose_bridge import (
            load_foundationpose_estimate,
        )
        from vision_grasp.grasp.pose_grasp import _transform_to_matrix

        estimate = load_foundationpose_estimate(args.pose_file)
        if estimate.camera_frame != config["camera_frame"]:
            raise SystemExit("pose camera frame does not match confirmed configuration")
        rospy.init_node("react_pose_transform", anonymous=True, disable_signals=True)
        buffer = tf2_ros.Buffer()
        _listener = tf2_ros.TransformListener(buffer)  # retain subscription lifetime
        rospy.sleep(0.5)
        transform = buffer.lookup_transform(
            config["base_frame"],
            estimate.camera_frame,
            rospy.Time(0),
            rospy.Duration(2.0),
        )
        matrix = np.matmul(_transform_to_matrix(transform), estimate.pose_matrix)
        result = {
            "pose_matrix": matrix.tolist(),
            "base_frame": config["base_frame"],
            "camera_frame": estimate.camera_frame,
        }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
