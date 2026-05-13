#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from navigation.chassis_client import ChassisNavigationClient

DEFAULT_TARGET_MAP_PATH = ROOT / "planner" / "configs" / "nav_targets.yaml"


def load_targets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("targets", {})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send navigation commands from Long_sequence_tasks.")
    parser.add_argument("--host", default="192.168.10.10")
    parser.add_argument("--port", default=31001, type=int)
    parser.add_argument("--timeout", default=3.0, type=float)
    parser.add_argument("--target-map", default=str(DEFAULT_TARGET_MAP_PATH))

    subparsers = parser.add_subparsers(dest="command", required=True)

    marker_parser = subparsers.add_parser("marker", help="Move to a marker name directly.")
    marker_parser.add_argument("--name", required=True)

    target_parser = subparsers.add_parser("target", help="Resolve a semantic target name to a marker.")
    target_parser.add_argument("--name", required=True)

    location_parser = subparsers.add_parser("location", help="Move to a map coordinate.")
    location_parser.add_argument("--x", required=True, type=float)
    location_parser.add_argument("--y", required=True, type=float)
    location_parser.add_argument("--theta", required=True, type=float)

    subparsers.add_parser("status", help="Read robot status.")
    subparsers.add_parser("markers", help="List markers.")
    subparsers.add_parser("cancel", help="Cancel active movement.")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = ChassisNavigationClient(host=args.host, port=args.port, timeout=args.timeout)

    if args.command == "marker":
        result = client.move_marker(args.name)
    elif args.command == "target":
        target_map = load_targets(Path(args.target_map))
        resolved = target_map.get(args.name, args.name)
        result = client.move_marker(resolved)
        result["target"] = args.name
        result["resolved_marker"] = resolved
    elif args.command == "location":
        result = client.move_location(args.x, args.y, args.theta)
    elif args.command == "status":
        result = client.status()
    elif args.command == "markers":
        result = client.markers()
    else:
        result = client.cancel()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
