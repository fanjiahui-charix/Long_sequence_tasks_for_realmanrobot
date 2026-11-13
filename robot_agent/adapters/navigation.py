from __future__ import annotations

import asyncio
import inspect
import math
import time
from pydantic import Field

from ..schemas import Contract, Observation, SkillReply


class Waypoint(Contract):
    x: float
    y: float
    theta: float
    xy_tolerance_m: float = Field(gt=0)
    yaw_tolerance_rad: float = Field(gt=0, le=math.pi)


class WaterStatusDecoder:
    """WATER API manual v1.1 pp.15–16,69; no inferred localization flag.

    Requires a separate current localization attestation and explicitly measured
    waypoint coordinates/tolerances. An idle/OK response never establishes arrival.
    """

    def __init__(self, goals: dict[str, Waypoint]):
        self.goals = goals

    def decode(self, raw, mission, *, localization_valid=None):
        candidates = raw.get("response", [raw]) if isinstance(raw, dict) else []
        results = None
        for value in candidates:
            if not isinstance(value, dict):
                continue
            response = (
                value.get("type") == "response"
                and value.get("command") == "/api/robot_status"
                and value.get("status") == "OK"
            )
            callback = (
                value.get("type") == "callback" and value.get("topic") == "robot_status"
            )
            if response or callback:
                results = value.get("results")
        obs = Observation(source="water_robot_status", notes=[])
        if not isinstance(results, dict):
            obs.notes.append("Unrecognized robot_status payload")
            return obs
        move, running = results.get("move_status"), results.get("running_status")
        obs.navigation_status = {
            "idle": "IDLE",
            "running": "MOVING",
            "succeeded": "SUCCEEDED",
            "failed": "FAILED",
            "canceled": "FAILED",
        }.get(move, "UNKNOWN")
        obs.motion_settled = running == "idle" and move in {
            "idle",
            "succeeded",
            "failed",
            "canceled",
        }
        if any(
            results.get(k) is True
            for k in ["estop_state", "soft_estop_state", "hard_estop_state"]
        ) or results.get("error_code", "00000000") not in {"00000000", "", None}:
            obs.navigation_status = "FAILED"
            obs.notes.append("Chassis reports stop/error state")
            return obs
        if move != "succeeded" or running != "idle" or localization_valid is not True:
            obs.notes.append(
                "Arrival needs succeeded + idle + independent localization validity"
            )
            return obs
        try:
            pose = results["current_pose"]
            values = [pose[k] for k in ["x", "y", "theta"]]
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
                return obs
            x, y, theta = values
            for label, marker in mission.location_mapping.items():
                goal = self.goals.get(label)
                if marker == results.get("move_target") and goal:
                    delta = math.atan2(
                        math.sin(theta - goal.theta), math.cos(theta - goal.theta)
                    )
                    if (
                        math.hypot(x - goal.x, y - goal.y) <= goal.xy_tolerance_m
                        and abs(delta) <= goal.yaw_tolerance_rad
                    ):
                        obs.robot_location = label
                        obs.localization_confirmed = True
        except (KeyError, TypeError):
            obs.notes.append("Current pose unavailable")
        return obs


class NavigationAdapter:
    def __init__(
        self,
        client,
        decoder,
        *,
        localization_reader,
        timeout_s=180,
        poll_interval_s=0.25,
    ):
        self.client, self.decoder = client, decoder
        self.localization_reader = localization_reader
        self.timeout_s, self.poll_interval_s = timeout_s, poll_interval_s

    async def localization_valid(self):
        value = self.localization_reader()
        return await value if inspect.isawaitable(value) else value

    async def observe(self, mission, *, localization_valid=None):
        if localization_valid is None:
            localization_valid = await self.localization_valid()
        raw = await asyncio.to_thread(self.client.status)
        return self.decoder.decode(raw, mission, localization_valid=localization_valid)

    async def navigate_to(self, target, mission):
        if (
            target not in self.decoder.goals
            or await self.localization_valid() is not True
        ):
            return SkillReply(status="FAILED", error_code="LOCALIZATION_UNKNOWN")
        await asyncio.to_thread(
            self.client.move_marker, mission.location_mapping[target]
        )
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            observation = await self.observe(mission)
            if (
                observation.robot_location == target
                and observation.localization_confirmed is True
                and observation.navigation_status == "SUCCEEDED"
            ):
                return SkillReply(
                    result={"target": target, "arrival_verified_by_adapter": True}
                )
            if observation.navigation_status == "FAILED":
                return SkillReply(status="FAILED", error_code="NAV_FAILED")
            await asyncio.sleep(self.poll_interval_s)
        await self.cancel()
        return SkillReply(status="TIMEOUT", error_code="NAV_TIMEOUT")

    async def cancel(self):
        await asyncio.to_thread(self.client.cancel)
