#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
VISION_GRASP_DIR = ROOT / "vision_grasp"
FOUNDATIONPOSE_ROOT = VISION_GRASP_DIR / "foundationpose"
ROS_PYTHON = Path("/usr/bin/python3")
ROS_SETUP_SCRIPTS = (
    "/opt/ros/noetic/setup.bash",
    "/home/rm/lt_grasp_ws/devel/setup.bash",
)
CAPTURE_SCRIPT = FOUNDATIONPOSE_ROOT / "capture_object_rgbd.py"
RAW_RGBD_CAPTURE_HELPER = VISION_GRASP_DIR / "camera" / "capture_rgbd_frame.py"
YOLO_SEG_RUNNER = VISION_GRASP_DIR / "segmentation" / "run_yolo_seg_mask.py"
FOUNDATIONPOSE_RUNNER = VISION_GRASP_DIR / "integration" / "run_foundationpose_single.sh"
GRASP_RUNNER = VISION_GRASP_DIR / "grasp" / "run_grasp.py"
DEFAULT_CONFIG_PATH = VISION_GRASP_DIR / "configs" / "grasp_config.example.yaml"

sys.path.insert(0, str(ROOT))

from vision_grasp.integration.foundationpose_bridge import load_foundationpose_estimate


class PoseGraspPipelineError(RuntimeError):
    """Raised when the pose-grasp pipeline cannot finish."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one RGBD frame, run FoundationPose, and optionally execute pose grasp."
    )
    parser.add_argument("--foundationpose-root", default=str(FOUNDATIONPOSE_ROOT))
    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--camera-frame", default=None)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--object-label", default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--runtime-root", default=str(VISION_GRASP_DIR / "runtime"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--execute-grasp", action="store_true")
    parser.add_argument(
        "--mask-backend",
        default="depth",
        choices=["depth", "yolo-seg"],
        help="Auto-mask backend. depth uses depth thresholding; yolo-seg uses official Ultralytics segmentation.",
    )

    parser.add_argument(
        "--mask",
        nargs="?",
        const="auto",
        default="auto",
        help="Mask source. Use '--mask' for current-frame auto mask, or '--mask /path/to/mask.png' for a manual mask file.",
    )
    parser.add_argument("--roi", default=None, help="ROI for capture_object_rgbd.py, format x,y,w,h.")
    parser.add_argument("--timeout", type=float, default=5.0, help="ROS capture timeout in seconds.")
    parser.add_argument("--color-topic", default=None)
    parser.add_argument("--depth-topic", default=None)
    parser.add_argument("--info-topic", default=None)
    parser.add_argument("--near-percentile", type=float, default=5.0)
    parser.add_argument("--depth-band-mm", type=int, default=80)
    parser.add_argument("--min-depth-mm", type=int, default=100)
    parser.add_argument("--max-depth-mm", type=int, default=2000)
    parser.add_argument("--min-area", type=int, default=300)
    parser.add_argument("--edge-margin-px", type=int, default=12)
    parser.add_argument("--center-window-scale", type=float, default=0.25)
    parser.add_argument("--center-min-valid", type=int, default=50)

    parser.add_argument("--seg-weights", default="yolov8n-seg.pt")
    parser.add_argument("--seg-label", default=None, help="YOLO-seg target class label. Defaults to --object-label when omitted.")
    parser.add_argument("--seg-conf", type=float, default=0.25)
    parser.add_argument("--seg-imgsz", type=int, default=640)
    parser.add_argument("--seg-device", default="0")
    parser.add_argument("--seg-max-det", type=int, default=20)

    parser.add_argument("--debug", type=int, default=0)
    parser.add_argument("--est-refine-iter", type=int, default=5)
    parser.add_argument("--track-refine-iter", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    runtime_dir = Path(args.runtime_root).expanduser() / run_id
    capture_dir = runtime_dir / "capture"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    capture_dir.mkdir(parents=True, exist_ok=True)

    camera_frame = args.camera_frame or args.camera_name
    pose_output = runtime_dir / "foundationpose_pose.json"
    debug_dir = runtime_dir / "foundationpose_debug"
    yolo_seg_json = runtime_dir / "yolo_seg_result.json"

    mask_mode, manual_mask_path = _resolve_mask_source(args.mask)

    if mask_mode == "manual":
        raw_capture_cmd = _build_raw_rgbd_capture_cmd(args, capture_dir)
        _run_command(raw_capture_cmd, cwd=ROOT)
        mask_path = _copy_manual_mask(manual_mask_path, runtime_dir)
        mask_backend = "manual"
    elif args.mask_backend == "yolo-seg":
        raw_capture_cmd = _build_raw_rgbd_capture_cmd(args, capture_dir)
        _run_command(raw_capture_cmd, cwd=ROOT)
        mask_path = capture_dir / "mask.png"
        yolo_seg_cmd = _build_yolo_seg_cmd(args, capture_dir, mask_path, yolo_seg_json)
        _run_command(yolo_seg_cmd, cwd=ROOT)
        mask_backend = "yolo-seg"
    else:
        capture_cmd = _build_capture_cmd(args, capture_dir)
        _run_command(capture_cmd, cwd=ROOT)
        mask_path = capture_dir / "mask.png"
        mask_backend = "depth"

    foundationpose_cmd = _build_foundationpose_cmd(
        args=args,
        capture_dir=capture_dir,
        pose_output=pose_output,
        debug_dir=debug_dir,
        camera_frame=camera_frame,
        mask_path=mask_path,
    )
    _run_command(foundationpose_cmd, cwd=ROOT)

    estimate = load_foundationpose_estimate(
        pose_output,
        camera_frame=camera_frame,
        object_label=args.object_label,
    )

    grasp_cmd = _build_grasp_cmd(
        config_path=Path(args.config).expanduser(),
        pose_file=pose_output,
        target_label=args.object_label,
    )

    result = {
        "run_id": run_id,
        "runtime_dir": str(runtime_dir),
        "camera_name": args.camera_name,
        "camera_frame": camera_frame,
        "mesh": str(Path(args.mesh).expanduser()),
        "object_label": args.object_label,
        "execute_grasp": bool(args.execute_grasp),
        "mask_mode": mask_mode,
        "mask_backend": mask_backend,
        "capture_dir": str(capture_dir),
        "capture_outputs": {
            "rgb": str(capture_dir / "rgb.png"),
            "depth": str(capture_dir / "depth.png"),
            "mask": str(mask_path),
            "k_file": str(capture_dir / "cam_K.txt"),
            "mask_vis": str(capture_dir / "mask_vis.png"),
        },
        "foundationpose": {
            "command": foundationpose_cmd,
            "pose_file_json": str(pose_output),
            "pose_file_txt": str(pose_output.with_suffix(".txt")),
            "confidence": estimate.confidence,
            "pose_matrix": estimate.pose_matrix.tolist(),
        },
        "yolo_seg": {
            "weights": args.seg_weights,
            "label": args.seg_label or args.object_label,
            "result_json": str(yolo_seg_json),
            "result": _load_optional_json(yolo_seg_json),
        },
        "grasp": {
            "command": grasp_cmd,
            "executed": False,
            "result": None,
        },
    }

    if args.execute_grasp:
        grasp_cp = _run_command(grasp_cmd, cwd=ROOT)
        result["grasp"]["executed"] = True
        result["grasp"]["result"] = _try_parse_json(grasp_cp.stdout)

    result_path = runtime_dir / "pipeline_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _build_capture_cmd(args: argparse.Namespace, capture_dir: Path) -> list[str]:
    cmd = [
        str(ROS_PYTHON),
        str(CAPTURE_SCRIPT),
        "--camera-name",
        args.camera_name,
        "--output-dir",
        str(capture_dir),
        "--timeout",
        str(args.timeout),
        "--near-percentile",
        str(args.near_percentile),
        "--depth-band-mm",
        str(args.depth_band_mm),
        "--min-depth-mm",
        str(args.min_depth_mm),
        "--max-depth-mm",
        str(args.max_depth_mm),
        "--min-area",
        str(args.min_area),
        "--edge-margin-px",
        str(args.edge_margin_px),
        "--center-window-scale",
        str(args.center_window_scale),
        "--center-min-valid",
        str(args.center_min_valid),
    ]
    _maybe_append(cmd, "--roi", args.roi)
    _maybe_append(cmd, "--color-topic", args.color_topic)
    _maybe_append(cmd, "--depth-topic", args.depth_topic)
    _maybe_append(cmd, "--info-topic", args.info_topic)
    return _wrap_ros_command(cmd)


def _build_yolo_seg_cmd(
    args: argparse.Namespace,
    capture_dir: Path,
    mask_path: Path,
    result_json: Path,
) -> list[str]:
    cmd = [
        str(ROS_PYTHON),
        str(YOLO_SEG_RUNNER),
        "--rgb",
        str(capture_dir / "rgb.png"),
        "--output-mask",
        str(mask_path),
        "--output-vis",
        str(capture_dir / "mask_vis.png"),
        "--output-json",
        str(result_json),
        "--weights",
        str(args.seg_weights),
        "--conf",
        str(args.seg_conf),
        "--imgsz",
        str(args.seg_imgsz),
        "--device",
        str(args.seg_device),
        "--max-det",
        str(args.seg_max_det),
    ]
    _maybe_append(cmd, "--label", args.seg_label or args.object_label)
    return _wrap_ros_command(cmd)


def _build_raw_rgbd_capture_cmd(args: argparse.Namespace, capture_dir: Path) -> list[str]:
    cmd = [
        str(ROS_PYTHON),
        str(RAW_RGBD_CAPTURE_HELPER),
        "--camera-name",
        args.camera_name,
        "--output-dir",
        str(capture_dir),
        "--timeout",
        str(args.timeout),
    ]
    _maybe_append(cmd, "--color-topic", args.color_topic)
    _maybe_append(cmd, "--depth-topic", args.depth_topic)
    _maybe_append(cmd, "--info-topic", args.info_topic)
    return _wrap_ros_command(cmd)


def _build_foundationpose_cmd(
    *,
    args: argparse.Namespace,
    capture_dir: Path,
    pose_output: Path,
    debug_dir: Path,
    camera_frame: str,
    mask_path: Path,
) -> list[str]:
    cmd = [
        str(FOUNDATIONPOSE_RUNNER),
        "--foundationpose-root",
        str(Path(args.foundationpose_root).expanduser()),
        "--mesh",
        str(Path(args.mesh).expanduser()),
        "--rgb",
        str(capture_dir / "rgb.png"),
        "--depth",
        str(capture_dir / "depth.png"),
        "--mask",
        str(mask_path),
        "--k-file",
        str(capture_dir / "cam_K.txt"),
        "--camera-frame",
        camera_frame,
        "--output",
        str(pose_output),
        "--debug-dir",
        str(debug_dir),
        "--debug",
        str(args.debug),
        "--est-refine-iter",
        str(args.est_refine_iter),
        "--track-refine-iter",
        str(args.track_refine_iter),
    ]
    _maybe_append(cmd, "--object-label", args.object_label)
    return cmd


def _build_grasp_cmd(*, config_path: Path, pose_file: Path, target_label: str | None) -> list[str]:
    cmd = [
        str(ROS_PYTHON),
        str(GRASP_RUNNER),
        "--config",
        str(config_path),
        "pose-grasp",
        "--pose-file",
        str(pose_file),
    ]
    _maybe_append(cmd, "--target-label", target_label)
    return _wrap_ros_command(cmd)


def _copy_manual_mask(mask_path: Path, runtime_dir: Path) -> Path:
    if not mask_path.exists():
        raise PoseGraspPipelineError(f"Manual mask not found: {mask_path}")
    target = runtime_dir / f"manual_mask{mask_path.suffix.lower() or '.png'}"
    shutil.copy2(str(mask_path), str(target))
    return target


def _resolve_mask_source(mask_arg: str | None) -> tuple[str, Path | None]:
    if mask_arg is None:
        return "auto", None

    normalized = str(mask_arg).strip()
    if normalized == "" or normalized.lower() == "auto":
        return "auto", None

    return "manual", Path(normalized).expanduser()


def _wrap_ros_command(cmd: Sequence[str]) -> list[str]:
    source_parts = [f"source {shlex.quote(path)}" for path in ROS_SETUP_SCRIPTS]
    exec_part = " ".join(shlex.quote(part) for part in cmd)
    shell_cmd = "set -e; " + " && ".join(source_parts) + " && " + exec_part
    return ["bash", "-lc", shell_cmd]


def _run_command(cmd: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0:
        raise PoseGraspPipelineError(
            "Command failed.\n"
            f"cwd: {cwd}\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}"
        )
    return cp


def _try_parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _maybe_append(cmd: list[str], flag: str, value: str | None) -> None:
    if value is None or value == "":
        return
    cmd.extend([flag, str(value)])


if __name__ == "__main__":
    raise SystemExit(main())
