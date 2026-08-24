from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from navigation.chassis_client import ChassisNavigationClient, ChassisNavigationError
from planner.agent_runtime.models import FailureCode, SkillResult

from .mock_backend import MockRobotBackend


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_MAP_PATH = ROOT / "configs" / "nav_targets.yaml"


def _load_target_map() -> dict[str, str]:
    config_path = Path(os.getenv("LONG_TASKS_NAV_TARGET_MAP", str(DEFAULT_TARGET_MAP_PATH)))
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    return data.get("targets", {})


def _ros_navigation_enabled() -> bool:
    return os.getenv("LONG_TASKS_USE_ROS_NAV", "").lower() in {"1", "true", "yes", "on"}


def _nav_backend() -> str:
    backend = os.getenv("LONG_TASKS_NAV_BACKEND", "").strip().lower()
    if backend:
        return backend
    return "ros" if _ros_navigation_enabled() else "tcp"


def _status_results(status_response: dict[str, Any]) -> dict[str, Any]:
    parsed = status_response.get("response", [])
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("results"), dict):
            return dict(item["results"])
    raise ChassisNavigationError("No chassis status payload found in response")


class LocateTableSkill:
    name = "locate_table"

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult.rejected(
            FailureCode.UNAVAILABLE,
            message="table localization adapter is not connected",
            data={"label": kwargs.get("label")},
        )


class PlanPathSkill:
    name = "plan_path"

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult.rejected(
            FailureCode.UNAVAILABLE,
            message="path planning adapter is not connected",
            data=dict(kwargs),
        )


class NavigateToSkill:
    name = "navigate_to"

    def __init__(self, mock_backend: MockRobotBackend | None = None) -> None:
        self.mock_backend = mock_backend or MockRobotBackend()

    def _target(self, kwargs: dict[str, Any]) -> tuple[Any, str]:
        target = kwargs.get("target") or kwargs.get("table")
        marker = kwargs.get("marker")
        target_map = _load_target_map()
        resolved = marker or target_map.get(str(target), str(target or ""))
        return target or marker, resolved

    def _tcp_client(self) -> ChassisNavigationClient:
        return ChassisNavigationClient(
            host=os.getenv("LONG_TASKS_CHASSIS_HOST", "192.168.10.10"),
            port=int(os.getenv("LONG_TASKS_CHASSIS_PORT", "31001")),
            timeout=float(os.getenv("LONG_TASKS_CHASSIS_TIMEOUT", "3.0")),
        )

    def run(self, **kwargs: Any) -> SkillResult:
        target, resolved_marker = self._target(kwargs)
        if target is None and not all(name in kwargs for name in ("x", "y", "theta")):
            return SkillResult.rejected(
                FailureCode.INVALID_ARGUMENT,
                message="navigate_to requires a target/marker or x/y/theta",
            )
        backend = _nav_backend()
        if backend == "mock":
            return self.mock_backend.navigate(str(target))
        if backend == "tcp":
            try:
                client = self._tcp_client()
                if all(name in kwargs for name in ("x", "y", "theta")):
                    response = client.move_location(kwargs["x"], kwargs["y"], kwargs["theta"])
                else:
                    response = client.move_marker(resolved_marker)
                return SkillResult.succeeded(
                    {
                        "backend": "tcp",
                        "command_accepted": True,
                        "target": target,
                        "marker": resolved_marker,
                        "response": response,
                    }
                )
            except (ValueError, ChassisNavigationError) as exc:
                return SkillResult.failed(
                    FailureCode.NAVIGATION_FAILED,
                    message=str(exc),
                    data={"target": target, "marker": resolved_marker, "backend": "tcp"},
                    retryable=True,
                )
        if backend == "ros":
            try:
                from navigation.ros_bridge.navigation_bridge import (
                    RosNavigationBridge,
                    RosNavigationError,
                )
            except ImportError as exc:
                return SkillResult.rejected(
                    FailureCode.UNAVAILABLE,
                    message=f"ROS navigation adapter is unavailable: {exc}",
                )
            try:
                bridge = RosNavigationBridge()
                if all(name in kwargs for name in ("x", "y", "theta")):
                    response = bridge.navigate_to_location(kwargs["x"], kwargs["y"], kwargs["theta"])
                else:
                    response = bridge.navigate_to_marker(resolved_marker)
                return SkillResult.succeeded(
                    {
                        "backend": "ros",
                        "command_accepted": True,
                        "target": target,
                        "marker": resolved_marker,
                        "response": response,
                    }
                )
            except (KeyError, ValueError, RosNavigationError) as exc:
                return SkillResult.failed(
                    FailureCode.NAVIGATION_FAILED,
                    message=str(exc),
                    data={"target": target, "marker": resolved_marker, "backend": "ros"},
                    retryable=True,
                )
        return SkillResult.rejected(
            FailureCode.UNAVAILABLE,
            message=f"unknown navigation backend: {backend}",
        )

    def observe(self, **kwargs: Any) -> dict[str, Any]:
        target, _resolved_marker = self._target(kwargs)
        backend = _nav_backend()
        if backend == "mock":
            return self.mock_backend.observe_navigation(str(target))
        if backend == "tcp":
            results = _status_results(self._tcp_client().status())
            return {"backend": "tcp", "target": target, **results}
        return {
            "backend": backend,
            "target": target,
            "observation_error": "navigation status adapter is unavailable",
        }


class AlignToTableSkill:
    name = "align_to_table"

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult.rejected(
            FailureCode.UNAVAILABLE,
            message="table alignment adapter is not connected",
            data={"table": kwargs.get("table")},
        )
