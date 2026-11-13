#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
FOUNDATIONPOSE_ROOT = ROOT / "vision_grasp" / "foundationpose"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FOUNDATIONPOSE_ROOT))

from vision_grasp.integration.foundationpose_bridge import load_foundationpose_estimate
from Utils import draw_posed_3d_box, draw_xyz_axis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw FoundationPose 6D pose overlay on RGB image.")
    parser.add_argument("--rgb", required=True, help="Input RGB/BGR image path.")
    parser.add_argument("--mesh", required=True, help="Object mesh path used by FoundationPose.")
    parser.add_argument("--pose", required=True, help="FoundationPose JSON/TXT pose output.")
    parser.add_argument("--k-file", required=True, help="3x3 camera intrinsic matrix text file.")
    parser.add_argument("--output", required=True, help="Output visualization PNG path.")
    parser.add_argument("--axis-scale", type=float, default=None, help="Axis length in meters. Defaults to 35%% of bbox diagonal.")
    parser.add_argument("--line-width", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rgb_path = Path(args.rgb).expanduser()
    mesh_path = Path(args.mesh).expanduser()
    pose_path = Path(args.pose).expanduser()
    k_path = Path(args.k_file).expanduser()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Failed to read RGB image: {rgb_path}")

    K = np.loadtxt(str(k_path), dtype=np.float64).reshape(3, 3)
    estimate = load_foundationpose_estimate(pose_path, camera_frame="camera_middle")
    ob_in_cam = estimate.pose_matrix.astype(np.float64)

    mesh = trimesh.load(str(mesh_path), force="mesh", process=False)
    if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
        raise SystemExit(f"Mesh has no vertices: {mesh_path}")
    bbox = np.asarray(mesh.bounds, dtype=np.float64)
    diag = float(np.linalg.norm(bbox[1] - bbox[0]))
    axis_scale = float(args.axis_scale) if args.axis_scale is not None else max(diag * 0.35, 0.03)

    vis = image.copy()
    vis = draw_posed_3d_box(K, vis, ob_in_cam, bbox, linewidth=args.line_width)
    vis = draw_xyz_axis(
        vis,
        ob_in_cam,
        scale=axis_scale,
        K=K,
        thickness=max(2, args.line_width),
        transparency=0,
        is_input_rgb=False,
    )

    center = project_point(np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64), K, ob_in_cam)
    if center is not None:
        cv2.circle(vis, center, 4, (255, 255, 255), -1)

    if not cv2.imwrite(str(output_path), vis):
        raise SystemExit(f"Failed to write visualization: {output_path}")

    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "rgb": str(rgb_path),
                "mesh": str(mesh_path),
                "pose": str(pose_path),
                "k_file": str(k_path),
                "output": str(output_path),
                "bbox_min": bbox[0].tolist(),
                "bbox_max": bbox[1].tolist(),
                "axis_scale": axis_scale,
                "confidence": estimate.confidence,
                "object_label": estimate.object_label,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output_path), "metadata": str(metadata_path)}, ensure_ascii=False, indent=2))
    return 0


def project_point(point_h: np.ndarray, K: np.ndarray, ob_in_cam: np.ndarray) -> tuple[int, int] | None:
    p_cam = (ob_in_cam @ point_h)[:3]
    if p_cam[2] <= 1e-6:
        return None
    uvw = K @ p_cam
    uv = uvw[:2] / uvw[2]
    return int(round(float(uv[0]))), int(round(float(uv[1])))


if __name__ == "__main__":
    raise SystemExit(main())
