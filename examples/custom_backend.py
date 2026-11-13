"""Template for another platform. All operations are high-level.

Implement RobotBackend using your robot's existing drivers. This file does not
send motion. See docs/BACKEND_API.md for feedback and cancellation semantics.
"""

from robot_agent.schemas import Observation


class YourRobotBackend:
    async def navigate_to(self, target, mission):
        raise NotImplementedError("Call your navigation API and verify arrival")

    async def locate_object(self, object_category, mission, *, motion_epoch):
        raise NotImplementedError("RGB-D / segmentation / pose / base-frame transform")

    async def grasp_object(self, pose, mission):
        raise NotImplementedError(
            "Pregrasp, grasp, close and retreat; return measured state"
        )

    async def observe_robot_state(self, mission):
        return Observation(
            source="unconfigured_custom_backend",
            notes=["TODO: implement measured feedback"],
        )

    async def cancel_current_action(self):
        raise NotImplementedError(
            "Implement an independent platform stop/cancel interface"
        )
