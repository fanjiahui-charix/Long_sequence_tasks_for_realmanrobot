#!/usr/bin/env python3
import argparse
from pathlib import Path

import cv2
import numpy as np
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image, CameraInfo


def largest_component(mask_bool, min_area=300):
    mask_u8 = mask_bool.astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, 8)

    if num_labels <= 1:
        return mask_bool

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest_label = 1 + int(np.argmax(areas))
    largest_area = int(stats[largest_label, cv2.CC_STAT_AREA])

    if largest_area < min_area:
        raise RuntimeError(f"Object mask too small: area={largest_area}, min_area={min_area}")

    return labels == largest_label


def depth_to_mm(depth_img):
    """
    FoundationPose 常见输入是 uint16 深度图，单位 mm。
    如果 ROS 深度是 16UC1，直接用。
    如果 ROS 深度是 32FC1，通常是米，这里转成 mm。
    """
    if depth_img.dtype == np.uint16:
        return depth_img

    if depth_img.dtype == np.float32 or depth_img.dtype == np.float64:
        depth_mm = depth_img * 1000.0
        depth_mm[~np.isfinite(depth_mm)] = 0
        depth_mm = np.clip(depth_mm, 0, 65535).astype(np.uint16)
        return depth_mm

    raise RuntimeError(f"Unsupported depth dtype: {depth_img.dtype}")


def parse_roi(roi_str, width, height):
    """
    roi 格式: x,y,w,h
    如果不传，默认取画面中间 80% 区域，避免边缘背景干扰。
    """
    if roi_str is None:
        margin_x = int(width * 0.10)
        margin_y = int(height * 0.10)
        return margin_x, margin_y, width - 2 * margin_x, height - 2 * margin_y

    vals = [int(v) for v in roi_str.split(",")]
    if len(vals) != 4:
        raise RuntimeError("--roi must be x,y,w,h")

    x, y, w, h = vals
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def make_depth_mask(depth_mm, roi, near_percentile=5.0, depth_band_mm=80, min_depth_mm=100, max_depth_mm=2000):
    """
    简单单物体分割：
    - 假设目标物体在桌面/背景前面
    - 在 ROI 里面找比较靠近相机的一团东西
    - 取最大连通区域作为目标物体 mask

    适合：画面里主要只有一个要抓的物体。
    """
    h, w = depth_mm.shape[:2]
    x, y, rw, rh = roi

    mask_roi = np.zeros((h, w), dtype=bool)
    mask_roi[y:y + rh, x:x + rw] = True

    valid = (
        mask_roi
        & (depth_mm > min_depth_mm)
        & (depth_mm < max_depth_mm)
    )

    valid_depths = depth_mm[valid]
    if valid_depths.size < 100:
        raise RuntimeError("Not enough valid depth pixels in ROI")

    # 找 ROI 里比较靠近相机的深度
    target_depth = np.percentile(valid_depths, near_percentile)

    # 取 target_depth 附近一段深度作为物体候选
    low = max(min_depth_mm, int(target_depth - depth_band_mm * 0.3))
    high = min(max_depth_mm, int(target_depth + depth_band_mm))

    mask = valid & (depth_mm >= low) & (depth_mm <= high)

    # 形态学清理
    mask_u8 = mask.astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)

    return mask_u8 > 0, target_depth, low, high


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--output-dir", default="/home/rm/FoundationPose/foundationpose_live")
    parser.add_argument("--timeout", type=float, default=5.0)

    parser.add_argument("--color-topic", default=None)
    parser.add_argument("--depth-topic", default=None)
    parser.add_argument("--info-topic", default=None)

    parser.add_argument("--roi", default=None, help="x,y,w,h. 不填则默认取画面中间 80%")
    parser.add_argument("--near-percentile", type=float, default=5.0)
    parser.add_argument("--depth-band-mm", type=int, default=80)
    parser.add_argument("--min-depth-mm", type=int, default=100)
    parser.add_argument("--max-depth-mm", type=int, default=2000)
    parser.add_argument("--min-area", type=int, default=300)

    args = parser.parse_args()

    rospy.init_node("capture_object_rgbd", anonymous=True)
    bridge = CvBridge()

    color_topic = args.color_topic or f"/{args.camera_name}/color/image_raw"
    depth_topic = args.depth_topic or f"/{args.camera_name}/aligned_depth_to_color/image_raw"
    info_topic = args.info_topic or f"/{args.camera_name}/color/camera_info"

    print("Waiting for:")
    print("  color:", color_topic)
    print("  depth:", depth_topic)
    print("  info :", info_topic)

    color_msg = rospy.wait_for_message(color_topic, Image, timeout=args.timeout)
    depth_msg = rospy.wait_for_message(depth_topic, Image, timeout=args.timeout)
    info_msg = rospy.wait_for_message(info_topic, CameraInfo, timeout=args.timeout)

    color_bgr = bridge.imgmsg_to_cv2(color_msg, "bgr8")
    depth_raw = bridge.imgmsg_to_cv2(depth_msg, desired_encoding="passthrough")
    depth_mm = depth_to_mm(depth_raw)

    height, width = depth_mm.shape[:2]
    roi = parse_roi(args.roi, width, height)

    mask, target_depth, low, high = make_depth_mask(
        depth_mm,
        roi,
        near_percentile=args.near_percentile,
        depth_band_mm=args.depth_band_mm,
        min_depth_mm=args.min_depth_mm,
        max_depth_mm=args.max_depth_mm,
    )

    mask = largest_component(mask, min_area=args.min_area)
    mask_u8 = mask.astype(np.uint8) * 255

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    rgb_path = out / "rgb.png"
    depth_path = out / "depth.png"
    mask_path = out / "mask.png"
    k_path = out / "cam_K.txt"
    vis_path = out / "mask_vis.png"

    cv2.imwrite(str(rgb_path), color_bgr)
    cv2.imwrite(str(depth_path), depth_mm)
    cv2.imwrite(str(mask_path), mask_u8)

    K = np.array(info_msg.K, dtype=np.float32).reshape(3, 3)
    np.savetxt(str(k_path), K)

    vis = color_bgr.copy()
    vis[mask] = (0, 0, 255)

    x, y, rw, rh = roi
    cv2.rectangle(vis, (x, y), (x + rw, y + rh), (0, 255, 0), 2)

    cv2.imwrite(str(vis_path), vis)

    print("")
    print("Saved files:")
    print(" ", rgb_path)
    print(" ", depth_path)
    print(" ", mask_path)
    print(" ", k_path)
    print(" ", vis_path)
    print("")
    print(f"ROI: x={x}, y={y}, w={rw}, h={rh}")
    print(f"target_depth≈{target_depth:.1f} mm, mask depth range=[{low}, {high}] mm")
    print(f"mask area={int(mask.sum())} pixels")


if __name__ == "__main__":
    main()