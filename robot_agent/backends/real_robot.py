from __future__ import annotations

import time
from ..schemas import Observation


class HardwareDisabled(RuntimeError):
    pass


class RealRobotBackend:
    """Compose high-level adapters for any platform. Explicitly opt in to motion.

    The provided navigation/perception/grasp implementations reuse RealMan
    modules; other platforms implement RobotBackend or supply equivalent ports.
    """

    def __init__(
        self,
        *,
        navigation,
        perception,
        grasp,
        state_reader,
        hardware_enabled=False,
        calibration=None,
        grasp_stopper=None,
    ):
        if hardware_enabled and (
            calibration is None or calibration.origin != "measured"
        ):
            raise ValueError("real hardware requires measured gripper calibration")
        self.navigation, self.perception, self.grasp = navigation, perception, grasp
        self.state_reader = state_reader
        self.hardware_enabled = hardware_enabled
        self.active_action = None
        self.grasp_stopper = grasp_stopper

    def _allowed(self):
        if not self.hardware_enabled:
            raise HardwareDisabled(
                "hardware execution requires explicit opt-in and confirmed configuration"
            )

    async def navigate_to(self, target, mission):
        self._allowed()
        self.active_action = "navigate_to"
        result = await self.navigation.navigate_to(target, mission)
        self.active_action = None
        return result

    async def locate_object(self, object_category, mission, *, motion_epoch):
        if self.perception is None:
            raise ValueError("perception adapter is not configured")
        return await self.perception.locate_object(
            object_category, mission, motion_epoch=motion_epoch
        )

    async def grasp_object(self, pose, mission):
        self._allowed()
        self.active_action = "grasp_object"
        result = await self.grasp.grasp_object(pose, mission)
        self.active_action = None
        return result

    async def observe_robot_state(self, mission):
        obs = (
            await self.state_reader.read(mission)
            if self.state_reader
            else Observation(
                source="unconfigured_state",
                notes=["TODO: supply a timestamped measured state adapter"],
            )
        )
        if self.navigation:
            valid = (
                obs.localization_confirmed
                if 0 <= time.time() - obs.timestamp <= 5
                else None
            )
            nav = await self.navigation.observe(mission, localization_valid=valid)
            location = (
                nav.robot_location
                if nav.localization_confirmed is True
                else obs.robot_location
            )
            confirmed = (
                nav.localization_confirmed
                if nav.localization_confirmed is True
                else obs.localization_confirmed
            )
            obs = obs.model_copy(
                update={
                    "timestamp": min(obs.timestamp, nav.timestamp),
                    "robot_location": location,
                    "localization_confirmed": confirmed,
                    "navigation_status": nav.navigation_status,
                    "motion_settled": obs.motion_settled is True
                    and nav.motion_settled is True,
                    "notes": obs.notes + nav.notes,
                }
            )
        if self.grasp and self.grasp.completed_at is not None:
            completed = self.grasp.completed_at
            stable_phase = (
                obs.arm_idle is True
                and obs.motion_settled is True
                and obs.timestamp >= completed
            )
            obs = obs.model_copy(
                update={
                    "retreat_complete": stable_phase,
                    "gripper_samples": [
                        sample.model_copy(
                            update={
                                "after_retreat": stable_phase
                                and sample.timestamp >= completed
                            }
                        )
                        for sample in obs.gripper_samples
                    ],
                }
            )
        return obs

    async def cancel_current_action(self):
        if self.navigation and self.active_action == "navigate_to":
            await self.navigation.cancel()
        if self.active_action == "grasp_object":
            if self.grasp_stopper is None:
                raise RuntimeError("ARM_STOP_ADAPTER_UNAVAILABLE")
            await self.grasp_stopper.cancel_current_action()
        # Keep active_action after cancellation: an ACK is not a measured stop.
