import asyncio
from pathlib import Path

import pytest

from robot_agent.backends.mock_robot import mock_calibration
from robot_agent.backends.real_robot import RealRobotBackend
from robot_agent.hardware import preflight


def test_unconfirmed_example_fails_offline_preflight():
    root = Path(__file__).resolve().parents[1]
    problems = preflight(root / "config/hardware.example.yaml")
    assert problems
    assert all(isinstance(p, str) for p in problems)


def test_real_hardware_refuses_synthetic_calibration():
    with pytest.raises(ValueError, match="measured"):
        RealRobotBackend(
            navigation=None,
            perception=None,
            grasp=None,
            state_reader=None,
            hardware_enabled=True,
            calibration=mock_calibration(),
        )


def test_real_cancel_reaches_adapter_after_coroutine_is_cancelled(mission):
    class Nav:
        def __init__(self):
            self.stops = 0

        async def navigate_to(self, target, mission):
            await asyncio.sleep(5)

        async def cancel(self):
            self.stops += 1

    async def check():
        nav = Nav()
        cal = mock_calibration().model_copy(update={"origin": "measured"})
        backend = RealRobotBackend(
            navigation=nav,
            perception=None,
            grasp=None,
            state_reader=None,
            hardware_enabled=True,
            calibration=cal,
        )
        task = asyncio.create_task(backend.navigate_to("B", mission))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await backend.cancel_current_action()
        assert nav.stops == 1

    asyncio.run(check())
