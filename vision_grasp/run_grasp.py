#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vision_grasp.end_effector_client import EndEffectorClient, EndEffectorControlError


DEFAULT_CONFIG_PATH = ROOT / "vision_grasp" / "demo" / "config" / "grasp_config.example.yaml"


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_demo_module():
    from vision_grasp.demo.scripts.simple_vision_grasp_demo import VisionGraspDemo

    return VisionGraspDemo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control the gripper/hand from Long_sequence_tasks.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--arm-ns", default=None)
    parser.add_argument("--end-effector-type", default=None, choices=["inspire_gripper", "dexterous_hand"])

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("open", help="Open the current end effector.")
    subparsers.add_parser("close", help="Close the current end effector.")

    angles_parser = subparsers.add_parser("set-angles", help="Set raw dexterous-hand joint angles.")
    angles_parser.add_argument("--angles", required=True, help='Example: "[0,0,0,0,0,1000]"')

    demo_parser = subparsers.add_parser("pick-demo", help="Run the one-shot local vision grasp demo.")
    demo_parser.add_argument("--target-label", default=None)

    return parser


def _resolve_settings(args: argparse.Namespace) -> dict:
    config = _load_config(Path(args.config))
    arm_ns = args.arm_ns or config.get("arm_ns", "l_arm")
    end_effector_type = args.end_effector_type or config.get("end_effector_type", "dexterous_hand")
    return {
        "config": config,
        "arm_ns": arm_ns,
        "end_effector_type": end_effector_type,
    }


def _run_pick_demo(config: dict, target_label: str | None) -> dict:
    try:
        import rospy
    except ImportError as exc:
        raise EndEffectorControlError(
            "ROS Python packages are not available. Run inside a sourced ROS environment."
        ) from exc

    if not rospy.core.is_initialized():
        rospy.init_node("long_tasks_vision_grasp_demo", anonymous=True, disable_signals=True)

    config_ns = "/vision_grasp_demo"
    merged = dict(config)
    if target_label:
        merged["target_label"] = target_label
    for key, value in merged.items():
        rospy.set_param(f"{config_ns}/{key}", value)

    VisionGraspDemo = _load_demo_module()
    demo = VisionGraspDemo()
    demo.run()
    return {
        "backend": "ros",
        "action": "pick_demo",
        "config_ns": config_ns,
        "target_label": merged.get("target_label", ""),
        "end_effector_type": merged.get("end_effector_type"),
    }


def main() -> None:
    args = build_parser().parse_args()
    settings = _resolve_settings(args)
    config = settings["config"]

    if args.command == "pick-demo":
        result = _run_pick_demo(config, args.target_label)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    try:
        client = EndEffectorClient(
            arm_ns=settings["arm_ns"],
            end_effector_type=settings["end_effector_type"],
        )

        if args.command == "open":
            result = client.open(
                open_position=int(config.get("gripper_open_position", 1000)),
                hand_speed=int(config.get("hand_speed", 400)),
                hand_force=int(config.get("hand_force", 300)),
                hand_open_angles=config.get("hand_open_angles", [0, 0, 0, 0, 0, 1000]),
            )
        elif args.command == "close":
            result = client.close(
                pick_speed=int(config.get("gripper_pick_speed", 400)),
                pick_force=int(config.get("gripper_pick_force", 300)),
                hand_speed=int(config.get("hand_speed", 400)),
                hand_force=int(config.get("hand_force", 300)),
                hand_close_angles=config.get("hand_close_angles", [1000, 1000, 1000, 1000, 1000, 0]),
            )
        else:
            raw_angles = yaml.safe_load(args.angles)
            result = client.set_hand_angles(
                raw_angles,
                hand_speed=int(config.get("hand_speed", 400)),
                hand_force=int(config.get("hand_force", 300)),
            )
    except EndEffectorControlError as exc:
        raise SystemExit(str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
