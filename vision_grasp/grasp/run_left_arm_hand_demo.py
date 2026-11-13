#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from vision_grasp.grasp.arm_motion_client import ArmMotionClient
from vision_grasp.grasp.end_effector_client import EndEffectorClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fixed right-arm demo: open dexterous hand, move to a reachable pose near current pose, close hand."
    )
    parser.add_argument("--arm-ns", default="r_arm")
    parser.add_argument("--end-effector-type", default="dexterous_hand", choices=["dexterous_hand", "inspire_gripper"])
    parser.add_argument("--speed", type=float, default=0.08)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--offset-x", type=float, default=0.0, help="Target x offset from current pose in base frame, meters.")
    parser.add_argument("--offset-y", type=float, default=0.0, help="Target y offset from current pose in base frame, meters.")
    parser.add_argument("--offset-z", type=float, default=0.0, help="Target z offset from current pose in base frame, meters.")
    parser.add_argument("--target-xyz", default=None, help="Absolute target xyz in base frame, example: 0.45,0.10,0.25. Overrides offsets.")
    parser.add_argument("--target-rpy", default="-2.135,0.634,2.254", help="Target RPY in radians when --target-xyz is used.")
    parser.add_argument("--open-angles", default="[0,0,0,0,0,1000]")
    parser.add_argument("--close-angles", default="[1000,1000,1000,1000,1000,0]")
    parser.add_argument("--hand-speed", type=int, default=400)
    parser.add_argument("--hand-force", type=int, default=300)
    parser.add_argument("--pause-after-open", type=float, default=1.0)
    parser.add_argument("--pause-after-move", type=float, default=1.0)
    parser.add_argument("--open-only", action="store_true", help="Only send the hand-open command. Do not move the arm.")
    parser.add_argument("--skip-plan-wait", action="store_true", help="Do not wait for /Plan_State after publishing MoveJ_P.")
    parser.add_argument("--dry-run", action="store_true", help="Only print current and target pose. Do not move or close hand.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        import rospy
        import tf
        from geometry_msgs.msg import Pose
    except ImportError as exc:
        raise SystemExit("ROS Python packages are not available. Source ROS and lt_grasp_ws first.") from exc

    if not rospy.core.is_initialized():
        rospy.init_node("long_tasks_right_arm_hand_demo", anonymous=True, disable_signals=True)

    if args.target_xyz:
        target_xyz = parse_float3(args.target_xyz, "target-xyz")
        target_rpy = parse_float3(args.target_rpy, "target-rpy")
        target_quat = [float(v) for v in tf.transformations.quaternion_from_euler(*target_rpy)]
        current_pose = try_read_current_pose(rospy, Pose, args.arm_ns, timeout=min(args.timeout, 2.0))
        offset_xyz = None
        if current_pose:
            offset_xyz = [target_xyz[i] - current_pose["xyz"][i] for i in range(3)]
    else:
        current_pose = read_current_pose(rospy, Pose, args.arm_ns, timeout=args.timeout)
        target_xyz = [
            current_pose["xyz"][0] + args.offset_x,
            current_pose["xyz"][1] + args.offset_y,
            current_pose["xyz"][2] + args.offset_z,
        ]
        offset_xyz = [args.offset_x, args.offset_y, args.offset_z]
        target_quat = current_pose["quaternion_xyzw"]

    plan = {
        "arm_ns": args.arm_ns,
        "action": "left_arm_hand_demo",
        "current_xyz": current_pose["xyz"] if current_pose else None,
        "current_quaternion_xyzw": current_pose["quaternion_xyzw"] if current_pose else None,
        "target_xyz": target_xyz,
        "target_quaternion_xyzw": target_quat,
        "offset_xyz": offset_xyz,
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    hand = EndEffectorClient(arm_ns=args.arm_ns, end_effector_type=args.end_effector_type, auto_init_node=False)
    motion = ArmMotionClient(arm_ns=args.arm_ns, auto_init_node=False)

    hand.open(
        hand_speed=args.hand_speed,
        hand_force=args.hand_force,
        hand_open_angles=parse_int_list(args.open_angles, "open-angles"),
    )
    rospy.sleep(args.pause_after_open)
    if args.open_only:
        print(json.dumps({"status": "open_command_sent"}, ensure_ascii=False, indent=2))
        return 0

    ok = motion.movej_pose(
        target_xyz,
        target_quat,
        speed=args.speed,
        timeout=args.timeout,
        wait_for_plan=not args.skip_plan_wait,
    )
    if not ok:
        raise SystemExit(f"Failed to move right arm to target pose: {target_xyz}")
    rospy.sleep(args.pause_after_move)

    hand.close(
        hand_speed=args.hand_speed,
        hand_force=args.hand_force,
        hand_close_angles=parse_int_list(args.close_angles, "close-angles"),
    )
    print(json.dumps({"status": "done", "target_xyz": target_xyz}, ensure_ascii=False, indent=2))
    return 0


def read_current_pose(rospy, Pose, arm_ns: str, timeout: float) -> dict:
    arm_ns = arm_ns.strip("/")
    pose = rospy.wait_for_message(f"/{arm_ns}/rm_driver/Pose_State", Pose, timeout=timeout)
    return {
        "xyz": [float(pose.position.x), float(pose.position.y), float(pose.position.z)],
        "quaternion_xyzw": [
            float(pose.orientation.x),
            float(pose.orientation.y),
            float(pose.orientation.z),
            float(pose.orientation.w),
        ],
    }


def try_read_current_pose(rospy, Pose, arm_ns: str, timeout: float) -> Optional[dict]:
    try:
        return read_current_pose(rospy, Pose, arm_ns, timeout)
    except Exception:
        return None


def parse_float3(raw: str, name: str) -> list[float]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 3:
        raise SystemExit(f"{name} must have 3 comma-separated values, got: {raw}")
    return [float(v) for v in parts]


def parse_int_list(raw: str, name: str) -> list[int]:
    import ast

    try:
        values = ast.literal_eval(raw)
    except Exception as exc:
        raise SystemExit(f"Invalid {name}: {raw}") from exc
    if not isinstance(values, (list, tuple)) or len(values) != 6:
        raise SystemExit(f"{name} must be a list of 6 integers")
    return [int(v) for v in values]


if __name__ == "__main__":
    raise SystemExit(main())
