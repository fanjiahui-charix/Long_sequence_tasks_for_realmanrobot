#!/usr/bin/env python3
import argparse
from pathlib import Path

import cv2
import numpy as np
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import CameraInfo, Image


def depth_to_mm(depth_img):
    """Convert ROS depth image to uint16 millimeters."""
    if depth_img.dtype == np.uint16:
        return depth_img

    if depth_img.dtype in (np.float32, np.float64):
        depth_mm = depth_img * 1000.0
        depth_mm[~np.isfinite(depth_mm)] = 0
        return np.clip(depth_mm, 0, 65535).astype(np.uint16)

    raise RuntimeError(f"Unsupported depth dtype: {depth_img.dtype}")


def parse_roi(roi_str, width, height):
    """
    ROI format: x,y,w,h
    If omitted, use the central 80 percent of the image to reduce edge clutter.
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


def make_center_window(roi, width, height, scale=0.25):
    """Return a smaller center-biased window inside ROI."""
    x, y, rw, rh = roi
    side = max(24, int(min(rw, rh) * float(scale)))
    side = min(side, rw, rh)
    cx = x + rw // 2
    cy = y + rh // 2

    half = side // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(width, x0 + side)
    y1 = min(height, y0 + side)
    return x0, y0, x1 - x0, y1 - y0


def connected_components(mask_bool):
    mask_u8 = mask_bool.astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_u8, 8)
    components = []
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        cx, cy = centroids[label]
        components.append(
            {
                "label": label,
                "bbox": (int(x), int(y), int(w), int(h)),
                "area": int(area),
                "centroid": (float(cx), float(cy)),
            }
        )
    return labels, components


def select_component(mask_bool, roi, min_area=300, edge_margin_px=12):
    """
    Prefer a center-near component that does not hug the ROI border.

    This is more robust than always taking the largest component when a hand or
    forearm enters the ROI from one side.
    """
    labels, components = connected_components(mask_bool)
    if not components:
        return mask_bool, {"selected_label": None, "selected_area": 0, "selection_mode": "empty"}

    x, y, rw, rh = roi
    roi_cx = x + rw * 0.5
    roi_cy = y + rh * 0.5
    roi_diag = max(float(np.hypot(rw, rh)), 1.0)

    candidates = []
    for comp in components:
        if comp["area"] < min_area:
            continue

        bx, by, bw, bh = comp["bbox"]
        cx, cy = comp["centroid"]
        edge_touch = (
            bx <= x + edge_margin_px
            or by <= y + edge_margin_px
            or (bx + bw) >= (x + rw - edge_margin_px)
            or (by + bh) >= (y + rh - edge_margin_px)
        )
        center_dist = float(np.hypot(cx - roi_cx, cy - roi_cy) / roi_diag)
        candidates.append(
            {
                **comp,
                "edge_touch": bool(edge_touch),
                "center_dist": center_dist,
            }
        )

    if not candidates:
        raise RuntimeError(f"Object mask too small: no component reaches min_area={min_area}")

    non_edge = [c for c in candidates if not c["edge_touch"]]
    pool = non_edge if non_edge else candidates
    selected = sorted(pool, key=lambda c: (c["center_dist"], -c["area"]))[0]

    return labels == selected["label"], {
        "selected_label": int(selected["label"]),
        "selected_area": int(selected["area"]),
        "selection_mode": "center_non_edge" if non_edge else "center_fallback",
        "selected_center_dist": float(selected["center_dist"]),
        "selected_edge_touch": bool(selected["edge_touch"]),
    }


def make_depth_mask(
    depth_mm,
    roi,
    *,
    near_percentile=5.0,
    depth_band_mm=80,
    min_depth_mm=100,
    max_depth_mm=2000,
    center_window_scale=0.25,
    center_min_valid=50,
):
    """
    Build a single-object mask from depth:

    1. Restrict search to ROI.
    2. Estimate target depth from a center-biased seed window if possible.
    3. Keep pixels near that depth band.
    4. Clean with morphology.
    """
    h, w = depth_mm.shape[:2]
    x, y, rw, rh = roi

    mask_roi = np.zeros((h, w), dtype=bool)
    mask_roi[y : y + rh, x : x + rw] = True

    valid = mask_roi & (depth_mm > min_depth_mm) & (depth_mm < max_depth_mm)
    valid_depths = depth_mm[valid]
    if valid_depths.size < 100:
        raise RuntimeError("Not enough valid depth pixels in ROI")

    sx, sy, sw, sh = make_center_window(roi, w, h, scale=center_window_scale)
    center_window = np.zeros((h, w), dtype=bool)
    center_window[sy : sy + sh, sx : sx + sw] = True
    center_valid = valid & center_window
    center_depths = depth_mm[center_valid]

    if center_depths.size >= center_min_valid:
        seed_depths = center_depths
        seed_source = "center_window"
    else:
        seed_depths = valid_depths
        seed_source = "full_roi"

    target_depth = float(np.percentile(seed_depths, near_percentile))

    low = max(min_depth_mm, int(target_depth - depth_band_mm * 0.20))
    high = min(max_depth_mm, int(target_depth + depth_band_mm * 0.55))

    mask = valid & (depth_mm >= low) & (depth_mm <= high)

    mask_u8 = mask.astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)

    debug = {
        "seed_source": seed_source,
        "seed_pixels": int(seed_depths.size),
        "center_window": [int(sx), int(sy), int(sw), int(sh)],
    }
    return mask_u8 > 0, target_depth, low, high, debug


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--output-dir", default="/home/rm/FoundationPose/foundationpose_live")
    parser.add_argument("--timeout", type=float, default=5.0)

    parser.add_argument("--color-topic", default=None)
    parser.add_argument("--depth-topic", default=None)
    parser.add_argument("--info-topic", default=None)

    parser.add_argument("--roi", default=None, help="x,y,w,h. Default: central 80 percent of image.")
    parser.add_argument("--near-percentile", type=float, default=5.0)
    parser.add_argument("--depth-band-mm", type=int, default=80)
    parser.add_argument("--min-depth-mm", type=int, default=100)
    parser.add_argument("--max-depth-mm", type=int, default=2000)
    parser.add_argument("--min-area", type=int, default=300)
    parser.add_argument("--edge-margin-px", type=int, default=12)
    parser.add_argument("--center-window-scale", type=float, default=0.25)
    parser.add_argument("--center-min-valid", type=int, default=50)

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

    mask, target_depth, low, high, debug = make_depth_mask(
        depth_mm,
        roi,
        near_percentile=args.near_percentile,
        depth_band_mm=args.depth_band_mm,
        min_depth_mm=args.min_depth_mm,
        max_depth_mm=args.max_depth_mm,
        center_window_scale=args.center_window_scale,
        center_min_valid=args.center_min_valid,
    )

    mask, component_info = select_component(
        mask,
        roi,
        min_area=args.min_area,
        edge_margin_px=args.edge_margin_px,
    )
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
    sx, sy, sw, sh = debug["center_window"]
    cv2.rectangle(vis, (sx, sy), (sx + sw, sy + sh), (255, 255, 0), 2)
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
    print(f"center_window: x={sx}, y={sy}, w={sw}, h={sh}")
    print(f"seed_source={debug['seed_source']}, seed_pixels={debug['seed_pixels']}")
    print(f"target_depth~{target_depth:.1f} mm, mask depth range=[{low}, {high}] mm")
    print(f"component_mode={component_info['selection_mode']}, selected_area={component_info['selected_area']}")
    print(f"mask area={int(mask.sum())} pixels")


if __name__ == "__main__":
    main()
