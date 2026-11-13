from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from ..schemas import Contract, Observation, PoseReference, SkillReply
from .process import ProcessRunner


class PerceptionSettings(Contract):
    repository_root: Path
    ros_python: str
    segmentation_python: str
    foundationpose_python: str
    camera_name: str
    camera_frame: str
    base_frame: str
    grasp_config: Path
    mesh_path: Path
    segmentation_weights: Path
    segmentation_label: str
    runtime_root: Path
    segmentation_confidence: float = Field(ge=0, le=1)
    stage_timeout_s: float = Field(gt=0)
    pose_min_score: float | None = None
    timing_confirmed: bool = False


class PerceptionAdapter:
    def __init__(self, settings: PerceptionSettings, *, runner=None):
        self.settings = settings
        self.runner = runner or ProcessRunner()
        self.pose_files = {}

    async def locate_object(self, object_category, mission, *, motion_epoch):
        s = self.settings
        if not s.timing_confirmed:
            return SkillReply(status="FAILED", error_code="SENSOR_TIMING_UNCONFIRMED")
        if any(
            not p.is_file()
            for p in [s.mesh_path, s.segmentation_weights, s.grasp_config]
        ):
            return SkillReply(
                status="FAILED", error_code="PERCEPTION_CONFIGURATION_REQUIRED"
            )
        runtime = s.runtime_root / str(uuid4())
        runtime.mkdir(parents=True, exist_ok=False)
        camera, seg = runtime / "camera", runtime / "segmentation.json"
        camera_pose, base_pose = (
            runtime / "camera_pose.json",
            runtime / "base_pose.json",
        )
        root = s.repository_root
        # This is a conservative lower bound, never an output file mtime or the
        # time inference completes. Operator must confirm RGB-D/TF timing first.
        captured_at = time.time()
        await self.runner.run(
            [
                s.ros_python,
                str(root / "vision_grasp/camera/capture_rgbd_frame.py"),
                "--camera-name",
                s.camera_name,
                "--output-dir",
                str(camera),
            ],
            timeout_s=s.stage_timeout_s,
            cwd=root,
        )
        await self.runner.run(
            [
                s.segmentation_python,
                str(root / "vision_grasp/segmentation/run_yolo_seg_mask.py"),
                "--rgb",
                str(camera / "rgb.png"),
                "--output-mask",
                str(camera / "mask.png"),
                "--output-vis",
                str(camera / "mask_vis.png"),
                "--output-json",
                str(seg),
                "--weights",
                str(s.segmentation_weights),
                "--label",
                s.segmentation_label,
                "--conf",
                str(s.segmentation_confidence),
            ],
            timeout_s=s.stage_timeout_s,
            cwd=root,
            isolated_python=s.segmentation_python == s.foundationpose_python,
        )
        metadata = json.loads(seg.read_text(encoding="utf-8"))
        confidence, area = (
            metadata.get("selected_confidence"),
            metadata.get("mask_area"),
        )
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
            or type(area) is not int
            or area <= 0
        ):
            return SkillReply(status="FAILED", error_code="MASK_INVALID")
        if (
            metadata.get("selected_label") != s.segmentation_label
            or confidence < s.segmentation_confidence
        ):
            return SkillReply(status="FAILED", error_code="OBJECT_NOT_FOUND")
        await self.runner.run(
            [
                s.foundationpose_python,
                str(root / "vision_grasp/integration/run_foundationpose_single.py"),
                "--foundationpose-root",
                str(root / "vision_grasp/foundationpose"),
                "--mesh",
                str(s.mesh_path),
                "--rgb",
                str(camera / "rgb.png"),
                "--depth",
                str(camera / "depth.png"),
                "--mask",
                str(camera / "mask.png"),
                "--k-file",
                str(camera / "cam_K.txt"),
                "--camera-frame",
                s.camera_frame,
                "--object-label",
                s.segmentation_label,
                "--output",
                str(camera_pose),
                "--debug-dir",
                str(runtime / "debug"),
            ],
            timeout_s=s.stage_timeout_s,
            cwd=root,
            isolated_python=True,
        )
        raw = json.loads(camera_pose.read_text(encoding="utf-8"))
        score = raw.get("confidence")
        if score is not None and (
            type(score) not in (int, float) or not math.isfinite(score)
        ):
            return SkillReply(status="FAILED", error_code="POSE_QUALITY_LOW")
        if s.pose_min_score is not None and (
            score is None or float(score) < s.pose_min_score
        ):
            return SkillReply(status="FAILED", error_code="POSE_QUALITY_LOW")
        await self.runner.run(
            [
                s.ros_python,
                str(root / "robot_agent/hardware_worker.py"),
                "transform",
                "--config",
                str(s.grasp_config),
                "--pose-file",
                str(camera_pose),
                "--output",
                str(base_pose),
            ],
            timeout_s=s.stage_timeout_s,
            cwd=root,
        )
        transformed = json.loads(base_pose.read_text(encoding="utf-8"))
        if (
            transformed.get("base_frame") != s.base_frame
            or transformed.get("camera_frame") != s.camera_frame
        ):
            return SkillReply(status="FAILED", error_code="COORDINATE_TRANSFORM_FAILED")
        pose = PoseReference(
            pose_id=str(uuid4()),
            object_category=object_category,
            captured_at=captured_at,
            reference_frame=s.base_frame,
            robot_location=mission.source_location,
            motion_epoch=motion_epoch,
            matrix=transformed["pose_matrix"],
            source_ref=str(camera_pose),
        )
        self.pose_files[pose.pose_id] = {
            "pose": pose,
            "camera_file": camera_pose,
            "sha256": hashlib.sha256(camera_pose.read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256(s.grasp_config.read_bytes()).hexdigest(),
        }
        # Bound references and artifacts retained in RAM (disk remains operator-owned).
        if len(self.pose_files) > 8:
            self.pose_files.pop(next(iter(self.pose_files)))
        return SkillReply(
            result={
                "segmentation_confidence": metadata["selected_confidence"],
                "foundationpose_score": score,
            },
            observation=Observation(
                source="rgbd_yolo_foundationpose_tf",
                object_category=object_category,
                object_detected=True,
                mask_valid=True,
                pose=pose,
                raw_result_reference=str(base_pose),
            ),
        )
