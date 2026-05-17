from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .base import SkillResult
from vision_grasp.end_effector_client import EndEffectorClient, EndEffectorControlError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRASP_CONFIG_PATH = ROOT / "configs" / "grasp.yaml"


def _manipulation_backend() -> str:
    return os.getenv("LONG_TASKS_MANIPULATION_BACKEND", "mock").strip().lower()


def _grasp_config_path() -> Path:
    value = os.getenv("LONG_TASKS_GRASP_CONFIG", str(DEFAULT_GRASP_CONFIG_PATH))
    return Path(value)


def _load_grasp_config() -> dict:
    path = _grasp_config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class PickObjectSkill:
    name = "pick_object"

    def run(self, **kwargs: Any) -> SkillResult:
        obj = kwargs.get("object")
        backend = _manipulation_backend()

        if backend == "mock":
            return SkillResult(ok=True, data={"object": obj, "backend": "mock", "note": "grasping not connected"})

        config = _load_grasp_config()
        arm_ns = kwargs.get("arm_ns") or config.get("arm_ns", "l_arm")
        end_effector_type = kwargs.get("end_effector_type") or config.get("end_effector_type", "dexterous_hand")

        try:
            if kwargs.get("mode") == "pick_demo":
                from vision_grasp.run_grasp import _run_pick_demo

                result = _run_pick_demo(config, obj)
            else:
                client = EndEffectorClient(arm_ns=arm_ns, end_effector_type=end_effector_type)
                result = client.close(
                    pick_speed=int(config.get("gripper_pick_speed", 400)),
                    pick_force=int(config.get("gripper_pick_force", 300)),
                    hand_speed=int(config.get("hand_speed", 400)),
                    hand_force=int(config.get("hand_force", 300)),
                    hand_close_angles=config.get("hand_close_angles", [1000, 1000, 1000, 1000, 1000, 0]),
                )
                result["object"] = obj
                result["mode"] = kwargs.get("mode", "close_only")
            return SkillResult(ok=True, data=result)
        except (ValueError, EndEffectorControlError, ImportError) as exc:
            return SkillResult(ok=False, error=str(exc), data={"object": obj, "backend": backend})


class PlaceObjectSkill:
    name = "place_object"

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target") or kwargs.get("table")
        backend = _manipulation_backend()

        if backend == "mock":
            return SkillResult(ok=True, data={"target": target, "backend": "mock", "note": "placing not connected"})

        config = _load_grasp_config()
        arm_ns = kwargs.get("arm_ns") or config.get("arm_ns", "l_arm")
        end_effector_type = kwargs.get("end_effector_type") or config.get("end_effector_type", "dexterous_hand")

        try:
            client = EndEffectorClient(arm_ns=arm_ns, end_effector_type=end_effector_type)
            result = client.open(
                open_position=int(config.get("gripper_open_position", 1000)),
                hand_speed=int(config.get("hand_speed", 400)),
                hand_force=int(config.get("hand_force", 300)),
                hand_open_angles=config.get("hand_open_angles", [0, 0, 0, 0, 0, 1000]),
            )
            result["target"] = target
            return SkillResult(ok=True, data=result)
        except (ValueError, EndEffectorControlError) as exc:
            return SkillResult(ok=False, error=str(exc), data={"target": target, "backend": backend})
