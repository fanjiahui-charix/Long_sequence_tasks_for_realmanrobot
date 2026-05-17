from __future__ import annotations

from pathlib import Path


class RosImageCaptureError(RuntimeError):
    """Raised when a camera RGB frame cannot be captured from ROS."""


def capture_rgb_image(
    output_path: str | Path,
    camera_name: str = "camera_middle",
    timeout: float = 5.0,
    topic: str | None = None,
) -> str:
    try:
        import cv2
        import rospy
        from cv_bridge import CvBridge
        from sensor_msgs.msg import Image
    except ImportError as exc:
        raise RosImageCaptureError(
            "ROS image capture dependencies are not available. "
            "Run inside a sourced ROS environment with cv_bridge installed."
        ) from exc

    if not rospy.core.is_initialized():
        rospy.init_node("long_tasks_rgb_capture", anonymous=True, disable_signals=True)

    image_topic = topic or f"/{camera_name}/color/image_raw"
    bridge = CvBridge()

    try:
        msg = rospy.wait_for_message(image_topic, Image, timeout=timeout)
    except Exception as exc:
        raise RosImageCaptureError(
            f"Timed out waiting for RGB image on topic {image_topic}"
        ) from exc

    image = bridge.imgmsg_to_cv2(msg, "bgr8")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image)
    if not ok:
        raise RosImageCaptureError(f"Failed to write image to {path}")
    return str(path)
