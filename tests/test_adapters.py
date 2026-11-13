import asyncio
import json
import sys
import time

import pytest

from robot_agent.adapters.navigation import (
    NavigationAdapter,
    WaterStatusDecoder,
    Waypoint,
)
from robot_agent.adapters.process import ProcessRunner, ProcessFailure
from robot_agent.backends.real_robot import RealRobotBackend, HardwareDisabled


class FakeChassis:
    def __init__(self, status):
        self.value = status
        self.moves = []

    def move_marker(self, marker):
        self.moves.append(marker)
        return {"status": "OK"}

    def status(self):
        return self.value

    def cancel(self):
        return {"status": "OK"}


def water(move_status="succeeded", *, target="mock_B", x=1):
    return {
        "response": [
            {
                "type": "response",
                "command": "/api/robot_status",
                "status": "OK",
                "results": {
                    "move_status": move_status,
                    "move_target": target,
                    "running_status": "idle",
                    "current_pose": {"x": x, "y": 0, "theta": 0},
                },
            }
        ]
    }


def test_water_decoder_requires_success_target_pose_and_localization_attestation(
    mission,
):
    goals = {
        "A": Waypoint(x=0, y=0, theta=0, xy_tolerance_m=0.1, yaw_tolerance_rad=0.1),
        "B": Waypoint(x=1, y=0, theta=0, xy_tolerance_m=0.1, yaw_tolerance_rad=0.1),
    }
    decoder = WaterStatusDecoder(goals)
    # robot_status has no positive localization-valid field, so external attestation is required.
    assert not decoder.decode(
        water(), mission, localization_valid=None
    ).localization_confirmed
    assert (
        decoder.decode(water(), mission, localization_valid=True).robot_location == "B"
    )
    assert (
        decoder.decode(water("idle"), mission, localization_valid=True).robot_location
        is None
    )
    assert (
        decoder.decode(
            water(target="other"), mission, localization_valid=True
        ).robot_location
        is None
    )
    assert (
        decoder.decode(water(x=10), mission, localization_valid=True).robot_location
        is None
    )


def test_navigation_ack_never_counts_as_arrival(mission):
    client = FakeChassis(water("idle"))
    goals = {
        "B": Waypoint(x=1, y=0, theta=0, xy_tolerance_m=0.1, yaw_tolerance_rad=0.1)
    }
    nav = NavigationAdapter(
        client,
        WaterStatusDecoder(goals),
        localization_reader=lambda: True,
        timeout_s=0.01,
        poll_interval_s=0.001,
    )
    result = asyncio.run(nav.navigate_to("B", mission))
    assert result.status == "TIMEOUT"
    assert client.moves == ["mock_B"]


def test_process_runner_timeout_reaps_owned_process(tmp_path):
    runner = ProcessRunner()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(
            runner.run(
                [sys.executable, "-c", "import time; time.sleep(5)"], timeout_s=0.03
            )
        )
    assert not runner.active_pids
    with pytest.raises(ProcessFailure):
        asyncio.run(
            runner.run([sys.executable, "-c", "raise SystemExit(2)"], timeout_s=3)
        )


def test_hardware_backend_is_disabled_by_default(mission):
    backend = RealRobotBackend(
        navigation=None, perception=None, grasp=None, state_reader=None
    )
    with pytest.raises(HardwareDisabled):
        asyncio.run(backend.navigate_to("B", mission))
    with pytest.raises(HardwareDisabled):
        asyncio.run(backend.grasp_object(None, mission))
    obs = asyncio.run(backend.observe_robot_state(mission))
    assert obs.arm_idle is None and obs.gripper_samples == []


@pytest.mark.parametrize(
    "seg_score,pose_score,mask_area,expected_error",
    [
        (0.9, 0.8, 100, None),
        (float("nan"), 0.8, 100, "MASK_INVALID"),
        (0.9, float("nan"), 100, "POSE_QUALITY_LOW"),
        (0.9, "nan", 100, "POSE_QUALITY_LOW"),
        (0.9, 0.8, float("nan"), "MASK_INVALID"),
    ],
)
def test_perception_uses_separate_interpreters_and_original_capture_time(
    mission, tmp_path, seg_score, pose_score, mask_area, expected_error
):
    from robot_agent.adapters.perception import PerceptionAdapter, PerceptionSettings

    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    config = tmp_path / "grasp.yaml"
    config.write_text(
        "base_frame: confirmed_base\ncamera_frame: camera\n", encoding="utf-8"
    )
    mesh, weights = tmp_path / "object.obj", tmp_path / "seg.pt"
    mesh.touch()
    weights.touch()

    class Runner:
        def __init__(self):
            self.commands = []

        async def run(self, command, **kwargs):
            self.commands.append(command)
            if "--output-json" in command:
                p = __import__("pathlib").Path(
                    command[command.index("--output-json") + 1]
                )
                p.write_text(
                    json.dumps(
                        {
                            "selected_label": "case",
                            "selected_confidence": seg_score,
                            "mask_area": mask_area,
                        }
                    )
                )
            elif "--output" in command:
                p = __import__("pathlib").Path(command[command.index("--output") + 1])
                if "transform" in command:
                    payload = {
                        "pose_matrix": [
                            [1, 0, 0, 0.4],
                            [0, 1, 0, 0],
                            [0, 0, 1, 0.1],
                            [0, 0, 0, 1],
                        ],
                        "base_frame": "confirmed_base",
                        "camera_frame": "camera",
                    }
                else:
                    payload = {
                        "confidence": pose_score,
                        "camera_frame": "camera",
                        "pose_matrix": [
                            [1, 0, 0, 0],
                            [0, 1, 0, 0],
                            [0, 0, 1, 1],
                            [0, 0, 0, 1],
                        ],
                    }
                p.write_text(json.dumps(payload))
            return None

    runner = Runner()
    settings = PerceptionSettings(
        repository_root=root,
        ros_python="ros-python",
        segmentation_python="seg-python",
        foundationpose_python="fp-python",
        camera_name="camera",
        camera_frame="camera",
        base_frame="confirmed_base",
        grasp_config=config,
        mesh_path=mesh,
        segmentation_weights=weights,
        segmentation_label="case",
        runtime_root=tmp_path / "runtime",
        segmentation_confidence=0.5,
        stage_timeout_s=20,
        timing_confirmed=True,
    )
    adapter = PerceptionAdapter(settings, runner=runner)
    before = time.time()
    result = asyncio.run(adapter.locate_object("glasses_case", mission, motion_epoch=2))
    if expected_error:
        assert result.status == "FAILED" and result.error_code == expected_error
        assert not adapter.pose_files
        return
    assert result.status == "SUCCEEDED" and result.observation.pose.motion_epoch == 2
    assert before <= result.observation.pose.captured_at <= time.time()
    assert [x[0] for x in runner.commands] == [
        "ros-python",
        "seg-python",
        "fp-python",
        "ros-python",
    ]
    assert all("--execute-grasp" not in x for x in runner.commands)
    assert result.observation.pose.pose_id in adapter.pose_files
