#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np
import trimesh


def _read_rgb(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _read_depth(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        depth = np.load(str(path)).astype(np.float32)
    else:
        depth_raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if depth_raw is None:
            raise FileNotFoundError(path)
        if depth_raw.dtype.kind in ("u", "i"):
            depth = depth_raw.astype(np.float32) / 1000.0
        else:
            depth = depth_raw.astype(np.float32)
    return depth


def _read_mask(path: Path, shape: tuple[int, int]) -> np.ndarray:
    if not path:
        return np.ones(shape, dtype=bool)
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(path)
    if mask.shape != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask > 0


def _read_intrinsics(args: argparse.Namespace) -> np.ndarray:
    if args.k_file:
        return np.loadtxt(args.k_file, dtype=np.float32).reshape(3, 3)
    if args.k_json:
        payload = json.loads(Path(args.k_json).read_text(encoding="utf-8"))
        if "K" in payload:
            return np.asarray(payload["K"], dtype=np.float32).reshape(3, 3)
        fx = float(payload["fx"])
        fy = float(payload["fy"])
        cx = float(payload["cx"])
        cy = float(payload["cy"])
        K = np.eye(3, dtype=np.float32)
        K[0, 0] = fx
        K[1, 1] = fy
        K[0, 2] = cx
        K[1, 2] = cy
        return K
    if all(v is not None for v in (args.fx, args.fy, args.cx, args.cy)):
        K = np.eye(3, dtype=np.float32)
        K[0, 0] = args.fx
        K[1, 1] = args.fy
        K[0, 2] = args.cx
        K[1, 2] = args.cy
        return K
    raise SystemExit("Need --k-file, --k-json, or fx/fy/cx/cy.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-frame FoundationPose inference -> pose file")
    parser.add_argument("--foundationpose-root", default="/home/rm/Long_sequence_tasks/vision_grasp/foundationpose")
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--rgb", required=True)
    parser.add_argument("--depth", required=True)
    parser.add_argument("--mask", default=None)
    parser.add_argument("--k-file", default=None)
    parser.add_argument("--k-json", default=None)
    parser.add_argument("--fx", type=float, default=None)
    parser.add_argument("--fy", type=float, default=None)
    parser.add_argument("--cx", type=float, default=None)
    parser.add_argument("--cy", type=float, default=None)
    parser.add_argument("--camera-frame", default="camera_middle")
    parser.add_argument("--object-label", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--debug-dir", default="/tmp/foundationpose_single_debug")
    parser.add_argument("--debug", type=int, default=0)
    parser.add_argument("--est-refine-iter", type=int, default=5)
    parser.add_argument("--track-refine-iter", type=int, default=2)
    args = parser.parse_args()

    repo_root = Path(args.foundationpose_root).expanduser().resolve()
    sys.path.insert(0, str(repo_root))

    import nvdiffrast.torch as dr
    from estimater import FoundationPose, PoseRefinePredictor, ScorePredictor, set_logging_format, set_seed

    set_logging_format()
    set_seed(0)

    rgb = _read_rgb(Path(args.rgb))
    depth = _read_depth(Path(args.depth))
    mask = _read_mask(Path(args.mask), rgb.shape[:2]) if args.mask else (depth > 0)
    K = _read_intrinsics(args)

    mesh = trimesh.load(args.mesh, force="mesh")
    if mesh.vertex_normals is None or len(mesh.vertex_normals) == 0:
        _ = mesh.vertex_normals

    scorer = ScorePredictor()
    refiner = PoseRefinePredictor()
    glctx = dr.RasterizeCudaContext()
    est = FoundationPose(
        model_pts=mesh.vertices,
        model_normals=mesh.vertex_normals,
        mesh=mesh,
        scorer=scorer,
        refiner=refiner,
        debug_dir=args.debug_dir,
        debug=args.debug,
        glctx=glctx,
    )

    pose = est.register(K=K, rgb=rgb, depth=depth, ob_mask=mask, iteration=args.est_refine_iter)
    confidence = float(est.scores[0].detach().cpu().item()) if getattr(est, "scores", None) is not None else None

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "camera_frame": args.camera_frame,
        "object_label": args.object_label,
        "confidence": confidence,
        "pose_matrix": np.asarray(pose, dtype=np.float64).reshape(4, 4).tolist(),
        "source": "foundationpose_single",
        "mesh": str(Path(args.mesh).expanduser().resolve()),
        "rgb": str(Path(args.rgb).expanduser().resolve()),
        "depth": str(Path(args.depth).expanduser().resolve()),
        "mask": str(Path(args.mask).expanduser().resolve()) if args.mask else None,
    }

    if out_path.suffix.lower() == ".txt":
        np.savetxt(str(out_path), np.asarray(pose, dtype=np.float64).reshape(4, 4))
    else:
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        np.savetxt(str(out_path.with_suffix(".txt")), np.asarray(pose, dtype=np.float64).reshape(4, 4))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
