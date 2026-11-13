from __future__ import annotations

from pathlib import Path
from pydantic import Field, ValidationError
import yaml

from .adapters.navigation import NavigationAdapter, WaterStatusDecoder, Waypoint
from .adapters.perception import PerceptionAdapter, PerceptionSettings
from .adapters.grasp import GraspAdapter
from .adapters.process import ProcessRunner
from .adapters.state import JsonStateReader
from .backends.real_robot import RealRobotBackend
from .schemas import Contract, GripperCalibration
from .verifier import DeterministicVerifier

ROOT = Path(__file__).resolve().parents[1]


class HardwareConfig(Contract):
    interfaces_confirmed: bool = False
    timing_confirmed: bool = False
    repository_root: Path = ROOT
    chassis_host: str
    chassis_port: int = Field(ge=1, le=65535)
    location_mapping: dict[str, str]
    waypoints: dict[str, Waypoint]
    state_command: list[str] = Field(min_length=1)
    grasp_stop_command: list[str] = Field(min_length=1)
    ros_python: str
    segmentation_python: str
    foundationpose_python: str
    grasp_config: Path
    mesh_path: Path
    segmentation_weights: Path
    segmentation_label: str = Field(min_length=1)
    segmentation_confidence: float = Field(ge=0, le=1)
    pose_min_score: float | None = None
    calibration: GripperCalibration
    runtime_root: Path = Path("runtime/hardware")
    pose_ttl_s: float = Field(gt=0)
    observation_ttl_s: float = Field(gt=0)
    stage_timeout_s: float = Field(gt=0)


def load_config(path):
    return HardwareConfig.model_validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    )


def preflight(path):
    """Offline validation only; no imports of ROS and no network/process actions."""
    try:
        config = load_config(path)
    except ValidationError as exc:
        return [
            ".".join(str(p) for p in e["loc"]) + ": " + e["type"] for e in exc.errors()
        ]
    except (OSError, yaml.YAMLError) as exc:
        return ["configuration cannot be read: " + type(exc).__name__]
    missing = []
    if not config.interfaces_confirmed:
        missing.append("operator must confirm platform interfaces and stop semantics")
    if not config.timing_confirmed:
        missing.append("RGB-D synchronization / camera-TF timing must be confirmed")
    if config.calibration.origin != "measured":
        missing.append("calibration must be measured, never synthetic")
    if not {"A", "B"}.issubset(config.location_mapping) or not {"A", "B"}.issubset(
        config.waypoints
    ):
        missing.append(
            "A/B marker mappings and measured goal poses/tolerances are required"
        )
    for name in [
        "ros_python",
        "segmentation_python",
        "foundationpose_python",
        "grasp_config",
        "mesh_path",
        "segmentation_weights",
    ]:
        if not Path(getattr(config, name)).is_file():
            missing.append(name + ": file not found")
    if config.grasp_config.is_file():
        grasp = yaml.safe_load(config.grasp_config.read_text(encoding="utf-8")) or {}
        required = [
            "camera_name",
            "camera_frame",
            "base_frame",
            "arm_ns",
            "end_effector_type",
            "home_pose_xyz",
            "home_pose_rpy",
            "pose_grasp_rpy",
            "arm_speed",
            "motion_timeout",
            "pregrasp_offset_local",
            "retreat_offset_local",
            "object_grasp_transform",
        ]
        missing += [
            "grasp_config." + key + ": explicitly confirmed value required"
            for key in required
            if key not in grasp
        ]
    return missing


class ProcessStopper:
    def __init__(self, command):
        self.command = command
        self.runner = ProcessRunner()

    async def cancel_current_action(self):
        # Command acknowledgement is not proof of physical stop.
        await self.runner.run(self.command, timeout_s=2)


def build_realman_backend(path, *, enable_hardware=False):
    if not enable_hardware:
        raise ValueError("explicit hardware enablement required")
    missing = preflight(path)
    if missing:
        raise ValueError("hardware preflight failed: " + "; ".join(missing))
    config = load_config(path)
    grasp_config = yaml.safe_load(config.grasp_config.read_text(encoding="utf-8"))
    state_reader = JsonStateReader(config.state_command)
    from navigation.chassis_client import ChassisNavigationClient

    async def localization_reader():
        # State command's mission parameter is intentionally not exposed to LLM.
        return await state_reader.localization_valid(
            None, max_age_s=config.observation_ttl_s
        )

    navigation = NavigationAdapter(
        ChassisNavigationClient(config.chassis_host, config.chassis_port),
        WaterStatusDecoder(config.waypoints),
        localization_reader=localization_reader,
    )
    perception = PerceptionAdapter(
        PerceptionSettings(
            repository_root=config.repository_root,
            ros_python=config.ros_python,
            segmentation_python=config.segmentation_python,
            foundationpose_python=config.foundationpose_python,
            camera_name=grasp_config["camera_name"],
            camera_frame=grasp_config["camera_frame"],
            base_frame=grasp_config["base_frame"],
            grasp_config=config.grasp_config,
            mesh_path=config.mesh_path,
            segmentation_weights=config.segmentation_weights,
            segmentation_label=config.segmentation_label,
            runtime_root=config.runtime_root,
            segmentation_confidence=config.segmentation_confidence,
            pose_min_score=config.pose_min_score,
            stage_timeout_s=config.stage_timeout_s,
            timing_confirmed=config.timing_confirmed,
        )
    )
    grasp = GraspAdapter(perception)
    backend = RealRobotBackend(
        navigation=navigation,
        perception=perception,
        grasp=grasp,
        state_reader=state_reader,
        hardware_enabled=True,
        calibration=config.calibration,
        grasp_stopper=ProcessStopper(config.grasp_stop_command),
    )
    verifier = DeterministicVerifier(
        config.calibration,
        base_frame=grasp_config["base_frame"],
        pose_ttl_s=config.pose_ttl_s,
        observation_ttl_s=config.observation_ttl_s,
    )
    return backend, verifier, config.location_mapping
