from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


class FoundationPoseLoadError(RuntimeError):
    """Raised when a FoundationPose result file cannot be parsed."""


@dataclass
class FoundationPoseEstimate:
    pose_matrix: np.ndarray
    camera_frame: str
    object_label: str | None = None
    confidence: float | None = None
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_frame": self.camera_frame,
            "object_label": self.object_label,
            "confidence": self.confidence,
            "source_path": self.source_path,
            "pose_matrix": self.pose_matrix.tolist(),
        }


def load_foundationpose_estimate(
    path: str | Path,
    *,
    camera_frame: str | None = None,
    object_label: str | None = None,
) -> FoundationPoseEstimate:
    pose_path = Path(path).expanduser()
    if not pose_path.exists():
        raise FoundationPoseLoadError(f"FoundationPose result file not found: {pose_path}")

    if pose_path.suffix.lower() == ".json":
        payload = json.loads(pose_path.read_text(encoding="utf-8"))
        pose_matrix = _extract_pose_matrix(payload)
        resolved_camera_frame = (
            camera_frame
            or payload.get("camera_frame")
            or payload.get("frame_id")
            or payload.get("camera_name")
        )
        resolved_object_label = object_label or payload.get("object_label") or payload.get("label")
        confidence = _maybe_float(payload.get("confidence") or payload.get("score"))
    else:
        pose_matrix = _normalize_pose_matrix(np.loadtxt(str(pose_path), dtype=float))
        resolved_camera_frame = camera_frame
        resolved_object_label = object_label
        confidence = None

    if not resolved_camera_frame:
        raise FoundationPoseLoadError(
            "camera_frame is required when the FoundationPose result file does not include it."
        )

    return FoundationPoseEstimate(
        pose_matrix=pose_matrix,
        camera_frame=str(resolved_camera_frame),
        object_label=resolved_object_label,
        confidence=confidence,
        source_path=str(pose_path),
    )


def _extract_pose_matrix(payload: dict[str, Any]) -> np.ndarray:
    for key in ("ob_in_cam", "pose_matrix", "pose", "matrix", "transform"):
        if key in payload:
            return _normalize_pose_matrix(np.array(payload[key], dtype=float))
    raise FoundationPoseLoadError(
        "JSON FoundationPose result must contain one of: ob_in_cam, pose_matrix, pose, matrix, transform."
    )


def _normalize_pose_matrix(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape == (16,):
        matrix = matrix.reshape(4, 4)
    if matrix.shape != (4, 4):
        raise FoundationPoseLoadError(f"Expected a 4x4 pose matrix, got shape {matrix.shape}")
    if not np.allclose(matrix[3], np.array([0.0, 0.0, 0.0, 1.0]), atol=1e-4):
        raise FoundationPoseLoadError("Pose matrix last row must be [0, 0, 0, 1].")
    return matrix


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
