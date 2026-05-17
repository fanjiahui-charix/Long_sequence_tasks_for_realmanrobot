#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vision_grasp.ros_image_capture import RosImageCaptureError, capture_rgb_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one current RGB frame from a ROS camera topic.")
    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--topic", default=None, help="Optional explicit image topic.")
    parser.add_argument("--timeout", default=5.0, type=float)
    parser.add_argument(
        "--output",
        default="/tmp/long_tasks_current_rgb.jpg",
        help="Where to save the captured image.",
    )
    args = parser.parse_args()

    try:
        saved = capture_rgb_image(
            output_path=args.output,
            camera_name=args.camera_name,
            timeout=args.timeout,
            topic=args.topic,
        )
    except RosImageCaptureError as exc:
        raise SystemExit(str(exc))

    print(json.dumps({"saved_image": saved, "camera_name": args.camera_name, "topic": args.topic}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
