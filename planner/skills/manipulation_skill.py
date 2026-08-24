from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from planner.agent_runtime.models import FailureCode, SkillResult

from .mock_backend import MockRobotBackend


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRASP_CONFIG_PATH = ROOT.parents[1] / "vision_grasp" / "configs" / "grasp_config.example.yaml"


def _manipulation_backend() -> str:
    return os.getenv("LONG_TASKS_MANIPULATION_BACKEND", "mock").strip().lower()


def _grasp_config_path() -> Path:
    return Path(os.getenv("LONG_TASKS_GRASP_CONFIG", str(DEFAULT_GRASP_CONFIG_PATH)))


def _load_grasp_config() -> dict[str, Any]:
    path = _grasp_config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


class PickObjectSkill:
    name = "pick_object"

    def __init__(self, mock_backend: MockRobotBackend | None = None) -> None:
        self.mock_backend = mock_backend or MockRobotBackend()

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        if not obj:
            return SkillResult.rejected(FailureCode.INVALID_ARGUMENT, message="pick_object requires object")
        backend = _manipulation_backend()
        if backend == "mock":
            return self.mock_backend.pick(str(obj))
        if backend != "ros":
            return SkillResult.rejected(
                FailureCode.UNAVAILABLE,
                message=f"unknown manipulation backend: {backend}",
            )

        config = _load_grasp_config()
        arm_ns = kwargs.get("arm_ns") or config.get("arm_ns", "l_arm")
        end_effector_type = kwargs.get("end_effector_type") or config.get(
            "end_effector_type", "dexterous_hand"
        )
        try:
            if kwargs.get("mode") == "pick_demo":
                from vision_grasp.grasp.run_grasp import _run_pick_demo

                result = _run_pick_demo(config, obj)
            elif kwargs.get("mode") == "pose_grasp":
                from vision_grasp.grasp.pose_grasp import execute_pose_grasp_from_config

                result = execute_pose_grasp_from_config(
                    config,
                    pose_file=kwargs.get("pose_file"),
                    object_label=obj,
                    camera_frame=kwargs.get("camera_frame"),
                )
            else:
                from vision_grasp.grasp.end_effector_client import EndEffectorClient

                client = EndEffectorClient(arm_ns=arm_ns, end_effector_type=end_effector_type)
                result = client.close(
                    pick_speed=int(config.get("gripper_pick_speed", 400)),
                    pick_force=int(config.get("gripper_pick_force", 300)),
                    hand_speed=int(config.get("hand_speed", 400)),
                    hand_force=int(config.get("hand_force", 300)),
                    hand_close_angles=config.get(
                        "hand_close_angles", [1000, 1000, 1000, 1000, 1000, 0]
                    ),
                )
                result["object"] = obj
                result["mode"] = kwargs.get("mode", "close_only")
            return SkillResult.succeeded(dict(result))
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            return SkillResult.unknown(
                FailureCode.GRASP_AMBIGUOUS,
                message=str(exc),
                data={"object": obj, "backend": backend},
            )

    def observe(self, **kwargs: Any) -> dict[str, Any]:
        obj = str(kwargs.get("object", ""))
        if _manipulation_backend() == "mock":
            return self.mock_backend.observe_grasp(obj)
        return {
            "object": obj,
            "observation_error": "real grasp evidence adapter is not connected",
        }


class PlaceObjectSkill:
    name = "place_object"

    def __init__(self, mock_backend: MockRobotBackend | None = None) -> None:
        self.mock_backend = mock_backend or MockRobotBackend()

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target") or kwargs.get("table")
        if not target:
            return SkillResult.rejected(FailureCode.INVALID_ARGUMENT, message="place_object requires target")
        backend = _manipulation_backend()
        if backend == "mock":
            return self.mock_backend.place(str(target))
        if backend != "ros":
            return SkillResult.rejected(
                FailureCode.UNAVAILABLE,
                message=f"unknown manipulation backend: {backend}",
            )
        config = _load_grasp_config()
        arm_ns = kwargs.get("arm_ns") or config.get("arm_ns", "l_arm")
        end_effector_type = kwargs.get("end_effector_type") or config.get(
            "end_effector_type", "dexterous_hand"
        )
        try:
            from vision_grasp.grasp.end_effector_client import EndEffectorClient

            client = EndEffectorClient(arm_ns=arm_ns, end_effector_type=end_effector_type)
            result = client.open(
                open_position=int(config.get("gripper_open_position", 1000)),
                hand_speed=int(config.get("hand_speed", 400)),
                hand_force=int(config.get("hand_force", 300)),
                hand_open_angles=config.get("hand_open_angles", [0, 0, 0, 0, 0, 1000]),
            )
            result["target"] = target
            return SkillResult.succeeded(dict(result))
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            return SkillResult.unknown(
                FailureCode.PLACE_FAILED,
                message=str(exc),
                data={"target": target, "backend": backend},
            )

    def observe(self, **kwargs: Any) -> dict[str, Any]:
        target = str(kwargs.get("target") or kwargs.get("table") or "")
        if _manipulation_backend() == "mock":
            return self.mock_backend.observe_place(target)
        return {
            "target": target,
            "observation_error": "real placement evidence adapter is not connected",
        }
