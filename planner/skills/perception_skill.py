import os
from typing import Any

from .base import SkillResult
from vision_grasp.integration.foundationpose_bridge import FoundationPoseLoadError, load_foundationpose_estimate


class LookAtSkill:
    name = "look_at"

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target")
        # Later: publish to /servo_control/move or camera head controller.
        return SkillResult(ok=True, data={"target": target, "note": "head control not connected"})


class DetectObjectSkill:
    name = "detect_object"

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        pose_file = kwargs.get("pose_file") or os.getenv("LONG_TASKS_FOUNDATIONPOSE_POSE", "").strip()
        camera_frame = kwargs.get("camera_frame")

        if not pose_file:
            return SkillResult(ok=True, data={"object": obj, "found": None, "note": "detector not connected"})

        try:
            estimate = load_foundationpose_estimate(
                pose_file,
                camera_frame=camera_frame,
                object_label=obj,
            )
        except FoundationPoseLoadError as exc:
            return SkillResult(
                ok=False,
                error=str(exc),
                data={"object": obj, "pose_file": pose_file},
            )

        return SkillResult(
            ok=True,
            data={
                "object": obj,
                "found": True,
                "backend": "foundationpose_file",
                "camera_frame": estimate.camera_frame,
                "confidence": estimate.confidence,
                "pose_file": estimate.source_path,
                "object_pose": estimate.pose_matrix.tolist(),
            },
        )
