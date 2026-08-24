from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from planner.agent_runtime.models import FailureCode, SkillResult

from .mock_backend import MockRobotBackend


class LookAtSkill:
    name = "look_at"

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult.rejected(
            FailureCode.UNAVAILABLE,
            message="head/camera control adapter is not connected",
            data={"target": kwargs.get("target")},
        )


class DetectObjectSkill:
    name = "detect_object"

    def __init__(self, mock_backend: MockRobotBackend | None = None) -> None:
        self.mock_backend = mock_backend or MockRobotBackend()
        self._last_observations: dict[str, dict[str, Any]] = {}

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        if not obj:
            return SkillResult.rejected(
                FailureCode.INVALID_ARGUMENT,
                message="detect_object requires object",
            )
        backend = os.getenv("LONG_TASKS_PERCEPTION_BACKEND", "foundationpose").strip().lower()
        if backend == "mock":
            return self.mock_backend.detect(str(obj))

        pose_file = kwargs.get("pose_file") or os.getenv("LONG_TASKS_FOUNDATIONPOSE_POSE", "").strip()
        camera_frame = kwargs.get("camera_frame")
        if not pose_file:
            return SkillResult.rejected(
                FailureCode.PERCEPTION_UNAVAILABLE,
                message="FoundationPose result is not configured",
                data={"object": obj},
            )
        try:
            from vision_grasp.integration.foundationpose_bridge import (
                FoundationPoseLoadError,
                load_foundationpose_estimate,
            )
        except ImportError as exc:
            return SkillResult.rejected(
                FailureCode.PERCEPTION_UNAVAILABLE,
                message=f"FoundationPose adapter is unavailable: {exc}",
                data={"object": obj, "pose_file": pose_file},
            )
        try:
            estimate = load_foundationpose_estimate(
                pose_file,
                camera_frame=camera_frame,
                object_label=obj,
            )
            timestamp = Path(estimate.source_path or pose_file).stat().st_mtime
        except (OSError, FoundationPoseLoadError) as exc:
            return SkillResult.failed(
                FailureCode.POSE_INVALID,
                message=str(exc),
                data={"object": obj, "pose_file": pose_file},
                retryable=True,
            )

        observation = {
            "object": str(obj),
            "found": True,
            "pose": estimate.pose_matrix.tolist(),
            "frame_id": estimate.camera_frame,
            "timestamp": float(timestamp),
            "source": estimate.source_path,
            "confidence": estimate.confidence,
        }
        self._last_observations[str(obj)] = observation
        return SkillResult.succeeded(
            {
                "backend": "foundationpose_file",
                "object": obj,
                "observation_ready": True,
            }
        )

    def observe(self, **kwargs: Any) -> dict[str, Any]:
        obj = str(kwargs.get("object", ""))
        backend = os.getenv("LONG_TASKS_PERCEPTION_BACKEND", "foundationpose").strip().lower()
        if backend == "mock":
            return self.mock_backend.observe_object(obj)
        return dict(self._last_observations.get(obj, {"object": obj, "found": False}))
