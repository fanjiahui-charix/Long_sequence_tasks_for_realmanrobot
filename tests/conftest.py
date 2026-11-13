import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def mission():
    from robot_agent.schemas import MissionSpec

    return MissionSpec(
        mission_id="test",
        instruction="从A到B拿黑色眼镜盒再回A",
        start_location="A",
        source_location="B",
        target_object="black glasses case",
        object_category="glasses_case",
        location_mapping={"A": "mock_A", "B": "mock_B"},
        scene_entities=["A", "B", "table", "black glasses case"],
    )


@pytest.fixture
def calibration():
    from robot_agent.schemas import GripperCalibration

    return GripperCalibration(
        calibration_id="synthetic-test",
        object_category="glasses_case",
        origin="synthetic",
        empty_range_mm=(0, 2),
        held_range_mm=(20, 35),
        max_spread_mm=1,
        min_samples=3,
        max_age_s=5,
    )


@pytest.fixture
def verifier(calibration):
    from robot_agent.verifier import DeterministicVerifier

    return DeterministicVerifier(
        calibration, base_frame="mock_base", pose_ttl_s=10, observation_ttl_s=5
    )


@pytest.fixture
def measured():
    from robot_agent.schemas import Observation, WidthSample

    def make(now=100, width=25, **kwargs):
        return Observation(
            timestamp=now,
            source="test_sensor",
            robot_location="A",
            localization_confirmed=True,
            navigation_status="IDLE",
            arm_idle=True,
            motion_settled=True,
            retreat_complete=True,
            gripper_samples=[
                WidthSample(
                    timestamp=now - i * 0.01,
                    width_mm=width,
                    measured=True,
                    source="test_actual_encoder",
                    after_retreat=True,
                )
                for i in range(3)
            ],
            **kwargs,
        )

    return make
