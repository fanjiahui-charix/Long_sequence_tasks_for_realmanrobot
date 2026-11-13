from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4
from ..schemas import SkillReply
from .process import ProcessRunner


class GraspAdapter:
    def __init__(self, perception, *, runner=None):
        self.perception = perception
        self.runner = runner or ProcessRunner()
        self.completed_at = None

    async def grasp_object(self, pose, mission):
        s = self.perception.settings
        asset = self.perception.pose_files.get(pose.pose_id)
        if (
            not asset
            or asset["pose"] != pose
            or hashlib.sha256(asset["camera_file"].read_bytes()).hexdigest()
            != asset["sha256"]
            or hashlib.sha256(s.grasp_config.read_bytes()).hexdigest()
            != asset["config_sha256"]
        ):
            return SkillReply(status="FAILED", error_code="POSE_REFERENCE_INVALID")
        self.completed_at = None
        output = s.runtime_root / ("grasp_" + str(uuid4()) + ".json")
        await self.runner.run(
            [
                s.ros_python,
                str(s.repository_root / "robot_agent/hardware_worker.py"),
                "grasp",
                "--enable-hardware",
                "--config",
                str(s.grasp_config),
                "--pose-file",
                str(asset["camera_file"]),
                "--output",
                str(output),
            ],
            timeout_s=s.stage_timeout_s,
            cwd=s.repository_root,
        )
        result = json.loads(output.read_text(encoding="utf-8"))
        if result.get("sequence_complete") is not True:
            return SkillReply(status="UNKNOWN", error_code="GRASP_EXECUTION_UNKNOWN")
        self.completed_at = time.time()
        return SkillReply(
            result={"sequence_complete": True, "raw_result_reference": str(output)}
        )
