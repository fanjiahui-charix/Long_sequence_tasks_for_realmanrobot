#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


class YoloSegMaskError(RuntimeError):
    """Raised when YOLO segmentation cannot produce a usable mask."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run official Ultralytics YOLO-seg on one RGB image and write mask files.")
    parser.add_argument("--rgb", required=True, help="Path to input RGB image.")
    parser.add_argument("--output-mask", required=True, help="Path to output binary mask PNG.")
    parser.add_argument("--output-vis", required=True, help="Path to output visualization image.")
    parser.add_argument("--output-json", default=None, help="Optional metadata JSON path.")
    parser.add_argument("--weights", default="yolov8n-seg.pt", help="Ultralytics segmentation weight path or official model name.")
    parser.add_argument("--label", default=None, help="Target class label. If omitted, choose the best center-near instance.")
    parser.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--device", default="0", help="Ultralytics device string. Use 0 for CUDA, cpu for CPU.")
    parser.add_argument("--max-det", type=int, default=20, help="Maximum detections.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rgb_path = Path(args.rgb).expanduser()
    output_mask = Path(args.output_mask).expanduser()
    output_vis = Path(args.output_vis).expanduser()
    output_json = Path(args.output_json).expanduser() if args.output_json else None

    if not rgb_path.exists():
        raise YoloSegMaskError(f"RGB image not found: {rgb_path}")

    image = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
    if image is None:
        raise YoloSegMaskError(f"Failed to load RGB image: {rgb_path}")

    model = YOLO(args.weights)
    if getattr(model, "task", None) != "segment":
        raise YoloSegMaskError(
            f"YOLO model is not a segmentation model: task={getattr(model, 'task', None)}. "
            "Use a *-seg.pt weight."
        )

    results = model.predict(
        source=image,
        conf=float(args.conf),
        imgsz=int(args.imgsz),
        device=args.device,
        max_det=int(args.max_det),
        verbose=False,
    )
    if not results:
        raise YoloSegMaskError("YOLO-seg returned no results.")

    result = results[0]
    if result.masks is None or result.boxes is None or len(result.boxes) == 0:
        raise YoloSegMaskError("YOLO-seg found no segmented instances.")

    selected = _select_instance(result, image.shape[:2], target_label=args.label)
    mask = selected["mask"]
    mask_u8 = mask.astype(np.uint8) * 255

    output_mask.parent.mkdir(parents=True, exist_ok=True)
    output_vis.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(output_mask), mask_u8):
        raise YoloSegMaskError(f"Failed to write mask image to {output_mask}")

    vis = image.copy()
    vis[mask] = (0, 0, 255)
    x1, y1, x2, y2 = selected["bbox_xyxy"]
    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
    label_text = f"{selected['label']} {selected['confidence']:.3f}"
    cv2.putText(vis, label_text, (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    if not cv2.imwrite(str(output_vis), vis):
        raise YoloSegMaskError(f"Failed to write visualization image to {output_vis}")

    metadata = {
        "weights": args.weights,
        "requested_label": args.label,
        "selected_label": selected["label"],
        "selected_confidence": selected["confidence"],
        "selected_bbox_xyxy": selected["bbox_xyxy"],
        "selected_center_dist": selected["center_dist"],
        "mask_area": selected["mask_area"],
        "image_shape": list(image.shape[:2]),
    }
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


def _select_instance(result, image_shape, *, target_label: str | None):
    height, width = image_shape
    cx = width * 0.5
    cy = height * 0.5
    diag = max(float(np.hypot(width, height)), 1.0)

    masks = result.masks.data.detach().cpu().numpy()
    boxes_xyxy = result.boxes.xyxy.detach().cpu().numpy()
    confs = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = result.names

    candidates = []
    for idx in range(len(boxes_xyxy)):
        label = str(names[classes[idx]])
        if target_label and label != target_label:
            continue

        mask = masks[idx] > 0.5
        if not np.any(mask):
            continue

        ys, xs = np.where(mask)
        mx = float(xs.mean())
        my = float(ys.mean())
        center_dist = float(np.hypot(mx - cx, my - cy) / diag)
        candidates.append(
            {
                "label": label,
                "confidence": float(confs[idx]),
                "mask": mask,
                "mask_area": int(mask.sum()),
                "bbox_xyxy": [int(v) for v in boxes_xyxy[idx].tolist()],
                "center_dist": center_dist,
            }
        )

    if not candidates:
        if target_label:
            raise YoloSegMaskError(f"YOLO-seg found no instance for label '{target_label}'.")
        raise YoloSegMaskError("YOLO-seg produced no usable mask candidate.")

    candidates.sort(key=lambda c: (c["center_dist"], -c["confidence"], -c["mask_area"]))
    return candidates[0]


if __name__ == "__main__":
    raise SystemExit(main())
