#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


class CaptureSegDatasetError(RuntimeError):
    """Raised when the segmentation dataset capture workflow fails."""


class RosRgbdStream:
    """Holds the latest RGB, depth, and camera-info messages from ROS."""

    def __init__(self, *, rospy, CvBridge, Image, CameraInfo, color_topic: str, depth_topic: str, info_topic: str):
        self._rospy = rospy
        self._bridge = CvBridge()
        self._Image = Image
        self._CameraInfo = CameraInfo

        self.color = None
        self.depth = None
        self.info = None
        self.color_seq = -1
        self.depth_seq = -1
        self.color_stamp = None
        self.depth_stamp = None
        self.info_stamp = None

        self._color_sub = rospy.Subscriber(color_topic, Image, self._on_color, queue_size=1)
        self._depth_sub = rospy.Subscriber(depth_topic, Image, self._on_depth, queue_size=1)
        self._info_sub = rospy.Subscriber(info_topic, CameraInfo, self._on_info, queue_size=1)

    def _on_color(self, msg):
        image = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        self.color = np.asarray(image).copy()
        self.color_seq += 1
        self.color_stamp = msg.header.stamp.to_sec() if msg.header.stamp else None

    def _on_depth(self, msg):
        depth = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        depth = np.asarray(depth)
        if np.issubdtype(depth.dtype, np.floating):
            depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
            depth = np.clip(np.round(depth * 1000.0), 0, np.iinfo(np.uint16).max).astype(np.uint16)
        elif depth.dtype != np.uint16:
            depth = np.clip(depth, 0, np.iinfo(np.uint16).max).astype(np.uint16)
        self.depth = depth.copy()
        self.depth_seq += 1
        self.depth_stamp = msg.header.stamp.to_sec() if msg.header.stamp else None

    def _on_info(self, msg):
        self.info = msg
        self.info_stamp = msg.header.stamp.to_sec() if msg.header.stamp else None

    def close(self):
        self._color_sub.unregister()
        self._depth_sub.unregister()
        self._info_sub.unregister()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture segmentation training data from the robot camera.")
    parser.add_argument("--camera-name", default="camera_middle")
    parser.add_argument("--dataset-name", required=True, help="Dataset folder name under vision_grasp/segmentation/datasets.")
    parser.add_argument("--mode", choices=["snapshot", "video"], default="snapshot")
    parser.add_argument("--output-root", default=None, help="Defaults to vision_grasp/segmentation/datasets.")
    parser.add_argument("--session-name", default=None, help="Optional session folder name. Defaults to timestamp.")
    parser.add_argument("--timeout", type=float, default=10.0, help="How long to wait for the first RGB/depth/info frame.")
    parser.add_argument("--color-topic", default=None)
    parser.add_argument("--depth-topic", default=None)
    parser.add_argument("--info-topic", default=None)
    parser.add_argument("--window-name", default="seg_dataset_capture")
    parser.add_argument("--video-fps", type=float, default=10.0)
    parser.add_argument("--extract-every-nth-frame", type=int, default=10, help="Used in video mode when auto-extract is enabled.")
    parser.add_argument("--no-auto-extract", action="store_true", help="Disable automatic frame extraction after video recording stops.")
    parser.add_argument("--no-depth-preview", action="store_true", help="Only show RGB preview.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        import rospy
        from cv_bridge import CvBridge  # noqa: F401
        from sensor_msgs.msg import CameraInfo, Image
    except ImportError as exc:
        raise CaptureSegDatasetError(
            "ROS capture dependencies are not available. Run this script in a sourced ROS environment."
        ) from exc

    base_root = Path(args.output_root).expanduser() if args.output_root else (
        Path(__file__).resolve().parent / "datasets"
    )
    dataset_root = base_root / args.dataset_name
    session_name = args.session_name or time.strftime("%Y%m%d_%H%M%S")
    session_root = dataset_root / "raw" / session_name
    camera_dir = session_root / "camera"
    snapshot_rgb_dir = session_root / "snapshots" / "rgb"
    snapshot_depth_dir = session_root / "snapshots" / "depth"
    snapshot_meta_dir = session_root / "snapshots" / "meta"
    video_dir = session_root / "videos"
    video_meta_dir = session_root / "videos" / "meta"
    extracted_dir = session_root / "videos" / "extracted_frames"
    for d in (
        camera_dir,
        snapshot_rgb_dir,
        snapshot_depth_dir,
        snapshot_meta_dir,
        video_dir,
        video_meta_dir,
        extracted_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)

    color_topic = args.color_topic or f"/{args.camera_name}/color/image_raw"
    depth_topic = args.depth_topic or f"/{args.camera_name}/aligned_depth_to_color/image_raw"
    info_topic = args.info_topic or f"/{args.camera_name}/color/camera_info"

    if not rospy.core.is_initialized():
        rospy.init_node("long_tasks_capture_seg_dataset", anonymous=True, disable_signals=True)

    stream = RosRgbdStream(
        rospy=rospy,
        CvBridge=CvBridge,
        Image=Image,
        CameraInfo=CameraInfo,
        color_topic=color_topic,
        depth_topic=depth_topic,
        info_topic=info_topic,
    )

    wait_deadline = time.time() + args.timeout
    while time.time() < wait_deadline and (stream.color is None or stream.depth is None or stream.info is None):
        rospy.sleep(0.05)

    if stream.color is None or stream.depth is None or stream.info is None:
        stream.close()
        raise CaptureSegDatasetError(
            "Timed out waiting for the first RGB/depth/camera_info frame.\n"
            f"color topic: {color_topic}\n"
            f"depth topic: {depth_topic}\n"
            f"info topic: {info_topic}"
        )

    session_meta = {
        "dataset_name": args.dataset_name,
        "session_name": session_name,
        "mode": args.mode,
        "camera_name": args.camera_name,
        "color_topic": color_topic,
        "depth_topic": depth_topic,
        "info_topic": info_topic,
        "video_fps": args.video_fps,
        "extract_every_nth_frame": args.extract_every_nth_frame,
    }
    (session_root / "session.json").write_text(json.dumps(session_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    k_path = camera_dir / "cam_K.txt"
    info_json_path = camera_dir / "camera_info.json"
    _write_camera_info(k_path, info_json_path, stream.info)

    cv2.namedWindow(args.window_name, cv2.WINDOW_NORMAL)
    _print_help(args.mode)

    recording = False
    writer = None
    current_video_path = None
    current_video_meta_path = None
    current_video_frames = 0
    last_written_color_seq = -1
    auto_extract = not args.no_auto_extract

    try:
        while not rospy.is_shutdown():
            preview = _build_preview(stream.color, stream.depth, show_depth=not args.no_depth_preview)
            overlay_lines = [
                f"dataset={args.dataset_name}",
                f"session={session_name}",
                f"mode={args.mode}",
                "keys: h=help, q=quit, s/space=save snapshot",
            ]
            if args.mode == "video":
                overlay_lines.append("keys: r=start/stop recording")
                overlay_lines.append(f"recording={'ON' if recording else 'OFF'}")
            preview = _draw_overlay(preview, overlay_lines)
            cv2.imshow(args.window_name, preview)

            if recording and writer is not None and stream.color_seq != last_written_color_seq:
                writer.write(stream.color)
                current_video_frames += 1
                last_written_color_seq = stream.color_seq

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                if recording:
                    _stop_recording(
                        writer=writer,
                        video_meta_path=current_video_meta_path,
                        video_path=current_video_path,
                        frame_count=current_video_frames,
                        camera_name=args.camera_name,
                        color_topic=color_topic,
                        auto_extract=auto_extract,
                        extract_dir=extracted_dir,
                        extract_every_nth_frame=args.extract_every_nth_frame,
                    )
                break
            if key in (ord("h"), ord("H")):
                _print_help(args.mode)
            elif key in (ord("s"), ord("S"), 32):
                _save_snapshot(
                    rgb_dir=snapshot_rgb_dir,
                    depth_dir=snapshot_depth_dir,
                    meta_dir=snapshot_meta_dir,
                    color=stream.color,
                    depth=stream.depth,
                    k_path=k_path,
                    camera_name=args.camera_name,
                    color_topic=color_topic,
                    depth_topic=depth_topic,
                    info_topic=info_topic,
                    color_stamp=stream.color_stamp,
                    depth_stamp=stream.depth_stamp,
                )
            elif args.mode == "video" and key in (ord("r"), ord("R")):
                if not recording:
                    current_video_path, current_video_meta_path, writer = _start_recording(
                        video_dir=video_dir,
                        meta_dir=video_meta_dir,
                        frame_shape=stream.color.shape,
                        fps=args.video_fps,
                        camera_name=args.camera_name,
                        color_topic=color_topic,
                    )
                    current_video_frames = 0
                    last_written_color_seq = -1
                    recording = True
                    print(f"[capture_seg_dataset] recording started: {current_video_path}")
                else:
                    _stop_recording(
                        writer=writer,
                        video_meta_path=current_video_meta_path,
                        video_path=current_video_path,
                        frame_count=current_video_frames,
                        camera_name=args.camera_name,
                        color_topic=color_topic,
                        auto_extract=auto_extract,
                        extract_dir=extracted_dir,
                        extract_every_nth_frame=args.extract_every_nth_frame,
                    )
                    writer = None
                    current_video_path = None
                    current_video_meta_path = None
                    current_video_frames = 0
                    recording = False
    finally:
        if writer is not None:
            writer.release()
        stream.close()
        cv2.destroyAllWindows()

    return 0


def _write_camera_info(k_path: Path, info_json_path: Path, info_msg) -> None:
    k_matrix = np.asarray(info_msg.K, dtype=np.float32).reshape(3, 3)
    np.savetxt(str(k_path), k_matrix, fmt="%.8f")
    payload = {
        "width": int(info_msg.width),
        "height": int(info_msg.height),
        "distortion_model": str(info_msg.distortion_model),
        "K": list(info_msg.K),
        "D": list(info_msg.D),
        "R": list(info_msg.R),
        "P": list(info_msg.P),
    }
    info_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_preview(color: np.ndarray, depth: np.ndarray, *, show_depth: bool) -> np.ndarray:
    rgb = color.copy()
    if not show_depth or depth is None:
        return rgb

    depth_vis = _depth_to_colormap(depth)
    if depth_vis.shape[:2] != rgb.shape[:2]:
        depth_vis = cv2.resize(depth_vis, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    return np.hstack([rgb, depth_vis])


def _depth_to_colormap(depth: np.ndarray) -> np.ndarray:
    valid = depth > 0
    if not np.any(valid):
        return np.zeros((depth.shape[0], depth.shape[1], 3), dtype=np.uint8)
    d = depth.astype(np.float32)
    lo = np.percentile(d[valid], 2)
    hi = np.percentile(d[valid], 98)
    if hi <= lo:
        hi = lo + 1.0
    norm = np.clip((d - lo) / (hi - lo), 0.0, 1.0)
    vis = (norm * 255.0).astype(np.uint8)
    return cv2.applyColorMap(vis, cv2.COLORMAP_JET)


def _draw_overlay(image: np.ndarray, lines: list[str]) -> np.ndarray:
    canvas = image.copy()
    y = 28
    for line in lines:
        cv2.putText(canvas, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2, cv2.LINE_AA)
        y += 28
    return canvas


def _save_snapshot(
    *,
    rgb_dir: Path,
    depth_dir: Path,
    meta_dir: Path,
    color: np.ndarray,
    depth: np.ndarray,
    k_path: Path,
    camera_name: str,
    color_topic: str,
    depth_topic: str,
    info_topic: str,
    color_stamp: float | None,
    depth_stamp: float | None,
) -> None:
    index = _next_index(rgb_dir, "rgb_", ".png")
    stem = f"{index:06d}"
    rgb_path = rgb_dir / f"rgb_{stem}.png"
    depth_path = depth_dir / f"depth_{stem}.png"
    meta_path = meta_dir / f"meta_{stem}.json"

    if not cv2.imwrite(str(rgb_path), color):
        raise CaptureSegDatasetError(f"Failed to write RGB snapshot to {rgb_path}")
    if not cv2.imwrite(str(depth_path), depth):
        raise CaptureSegDatasetError(f"Failed to write depth snapshot to {depth_path}")

    payload = {
        "index": index,
        "rgb_path": str(rgb_path),
        "depth_path": str(depth_path),
        "k_path": str(k_path),
        "camera_name": camera_name,
        "color_topic": color_topic,
        "depth_topic": depth_topic,
        "info_topic": info_topic,
        "color_stamp": color_stamp,
        "depth_stamp": depth_stamp,
        "saved_at": time.time(),
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[capture_seg_dataset] saved snapshot #{index}: {rgb_path.name}")


def _start_recording(
    *,
    video_dir: Path,
    meta_dir: Path,
    frame_shape: tuple[int, int, int],
    fps: float,
    camera_name: str,
    color_topic: str,
):
    index = _next_index(video_dir, "rgb_video_", ".mp4")
    stem = f"{index:06d}"
    video_path = video_dir / f"rgb_video_{stem}.mp4"
    meta_path = meta_dir / f"rgb_video_{stem}.json"
    height, width = frame_shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise CaptureSegDatasetError(f"Failed to open video writer for {video_path}")

    payload = {
        "index": index,
        "video_path": str(video_path),
        "camera_name": camera_name,
        "color_topic": color_topic,
        "fps": fps,
        "width": width,
        "height": height,
        "started_at": time.time(),
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return video_path, meta_path, writer


def _stop_recording(
    *,
    writer,
    video_meta_path: Path | None,
    video_path: Path | None,
    frame_count: int,
    camera_name: str,
    color_topic: str,
    auto_extract: bool,
    extract_dir: Path,
    extract_every_nth_frame: int,
) -> None:
    if writer is not None:
        writer.release()
    if video_path is None or video_meta_path is None:
        return

    payload = {
        "video_path": str(video_path),
        "camera_name": camera_name,
        "color_topic": color_topic,
        "frame_count": frame_count,
        "stopped_at": time.time(),
        "auto_extract": bool(auto_extract),
        "extract_every_nth_frame": int(extract_every_nth_frame),
    }
    video_meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[capture_seg_dataset] recording stopped: {video_path.name}, frames={frame_count}")

    if auto_extract and extract_every_nth_frame > 0:
        saved = _extract_frames_from_video(
            video_path=video_path,
            extract_root=extract_dir / video_path.stem,
            every_nth_frame=extract_every_nth_frame,
        )
        print(f"[capture_seg_dataset] extracted {saved} frames to {extract_dir / video_path.stem}")


def _extract_frames_from_video(*, video_path: Path, extract_root: Path, every_nth_frame: int) -> int:
    extract_root.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise CaptureSegDatasetError(f"Failed to open recorded video for extraction: {video_path}")

    saved = 0
    frame_idx = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_idx % every_nth_frame == 0:
                saved += 1
                frame_path = extract_root / f"frame_{saved:06d}.png"
                if not cv2.imwrite(str(frame_path), frame):
                    raise CaptureSegDatasetError(f"Failed to write extracted frame to {frame_path}")
            frame_idx += 1
    finally:
        capture.release()
    return saved


def _next_index(directory: Path, prefix: str, suffix: str) -> int:
    max_index = 0
    for path in directory.glob(f"{prefix}*{suffix}"):
        stem = path.name[len(prefix):-len(suffix)]
        if stem.isdigit():
            max_index = max(max_index, int(stem))
    return max_index + 1


def _print_help(mode: str) -> None:
    print("[capture_seg_dataset] keyboard controls")
    print("  h : show help")
    print("  q / Esc : quit")
    print("  s / Space : save current RGB-D snapshot")
    if mode == "video":
        print("  r : start/stop RGB video recording")


if __name__ == "__main__":
    raise SystemExit(main())
