from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros_nodes.navigation_bridge import RosNavigationBridge, RosNavigationError


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one navigation command through ROS.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    marker_parser = subparsers.add_parser("marker", help="Navigate with /navigation_marker")
    marker_parser.add_argument("--name", required=True, help="Marker name such as dianA")

    location_parser = subparsers.add_parser("location", help="Navigate with /navigation_location")
    location_parser.add_argument("--x", required=True, type=float)
    location_parser.add_argument("--y", required=True, type=float)
    location_parser.add_argument("--theta", required=True, type=float)

    rviz_parser = subparsers.add_parser("rviz-goal", help="Publish a 2D nav goal to RViz topic")
    rviz_parser.add_argument("--x", required=True, type=float)
    rviz_parser.add_argument("--y", required=True, type=float)
    rviz_parser.add_argument("--yaw", required=True, type=float)
    rviz_parser.add_argument("--frame-id", default="map")

    subparsers.add_parser("cancel", help="Cancel current navigation")

    args = parser.parse_args()

    try:
        bridge = RosNavigationBridge()
        if args.command == "marker":
            result = bridge.navigate_to_marker(args.name)
        elif args.command == "location":
            result = bridge.navigate_to_location(args.x, args.y, args.theta)
        elif args.command == "rviz-goal":
            result = bridge.publish_rviz_goal(args.x, args.y, args.yaw, frame_id=args.frame_id)
        else:
            result = bridge.cancel_navigation()
    except RosNavigationError as exc:
        raise SystemExit(str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
