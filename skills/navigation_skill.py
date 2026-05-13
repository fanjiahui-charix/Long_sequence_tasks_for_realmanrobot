from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from .base import SkillResult

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_MAP_PATH = ROOT / "configs" / "nav_targets.yaml"


def _load_target_map() -> Dict[str, str]:
    config_path = Path(os.getenv("LONG_TASKS_NAV_TARGET_MAP", str(DEFAULT_TARGET_MAP_PATH)))
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("targets", {})


def _ros_navigation_enabled() -> bool:
    return os.getenv("LONG_TASKS_USE_ROS_NAV", "").lower() in {"1", "true", "yes", "on"}


class LocateTableSkill:
    name = "locate_table"

    def run(self, **kwargs: Any) -> SkillResult:
        label = kwargs.get("label")
        return SkillResult(ok=True, data={"label": label, "note": "prototype only"})


class PlanPathSkill:
    name = "plan_path"

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult(ok=True, data={"path": kwargs, "note": "prototype only"})


class NavigateToSkill:
    name = "navigate_to"

    def run(self, **kwargs: Any) -> SkillResult:
        target = kwargs.get("target") or kwargs.get("table")
        marker = kwargs.get("marker")

        if not _ros_navigation_enabled():
            return SkillResult(
                ok=True,
                data={
                    "target": target,
                    "marker": marker,
                    "note": "prototype only; set LONG_TASKS_USE_ROS_NAV=1 to use ROS navigation",
                },
            )

        try:
            from ros_nodes.navigation_bridge import RosNavigationBridge, RosNavigationError

            bridge = RosNavigationBridge()
            if all(name in kwargs for name in ("x", "y", "theta")):
                result = bridge.navigate_to_location(kwargs["x"], kwargs["y"], kwargs["theta"])
            elif kwargs.get("rviz_goal"):
                result = bridge.publish_rviz_goal(
                    kwargs["x"],
                    kwargs["y"],
                    kwargs.get("yaw", kwargs.get("theta", 0.0)),
                    frame_id=kwargs.get("frame_id", "map"),
                )
            else:
                target_map = _load_target_map()
                resolved_marker = marker or target_map.get(str(target), str(target))
                result = bridge.navigate_to_marker(resolved_marker)
                result["resolved_target"] = target
            return SkillResult(ok=True, data=result)
        except (ImportError, RosNavigationError, KeyError, ValueError) as exc:
            return SkillResult(ok=False, error=str(exc), data={"target": target, "marker": marker})


class AlignToTableSkill:
    name = "align_to_table"

    def run(self, **kwargs: Any) -> SkillResult:
        table = kwargs.get("table")
        return SkillResult(ok=True, data={"table": table, "note": "alignment not connected"})
