#!/usr/bin/env python3
"""Command-line client for the Yunji/WATER chassis TCP API."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Iterable
from urllib.parse import quote


DEFAULT_HOST = "192.168.10.10"
DEFAULT_PORT = 31001
DEFAULT_TIMEOUT = 3.0


def request(command: str, host: str, port: int, timeout: float) -> str:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(command.encode("utf-8"))

        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def print_response(raw: str) -> None:
    if not raw:
        return

    # The chassis often returns one JSON object per line.
    lines = [line for line in raw.splitlines() if line.strip()]
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            print(line)
        else:
            print(json.dumps(parsed, ensure_ascii=False, indent=2))


def encode_marker(name: str) -> str:
    return quote(name, safe="")


def build_command(args: argparse.Namespace) -> str:
    action = args.action

    if action == "raw":
        return args.command
    if action == "status":
        return "/api/robot_status"
    if action == "markers":
        return "/api/markers/query_list"
    if action == "marker-brief":
        return "/api/markers/query_brief"
    if action == "cancel":
        return "/api/move/cancel"
    if action == "move-marker":
        return f"/api/move?marker={encode_marker(args.name)}"
    if action == "move-location":
        return f"/api/move?location={args.x},{args.y},{args.theta}"
    if action == "move-markers":
        markers = ",".join(args.names)
        return (
            f"/api/move?markers={quote(markers, safe=',')}"
            f"&distance_tolerance={args.distance_tolerance}&count={args.count}"
        )
    if action == "insert-current":
        command = f"/api/markers/insert?name={encode_marker(args.name)}&type={args.type}"
        if args.num is not None:
            command += f"&num={args.num}"
        return command
    if action == "insert-pose":
        command = (
            f"/api/markers/insert_by_pose?name={encode_marker(args.name)}"
            f"&x={args.x}&y={args.y}&theta={args.theta}"
            f"&floor={args.floor}&type={args.type}"
        )
        if args.num is not None:
            command += f"&num={args.num}"
        return command
    if action == "delete-marker":
        return f"/api/markers/delete?name={encode_marker(args.name)}"

    raise ValueError(f"Unsupported action: {action}")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help="Chassis IP address.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Chassis API port.")
    parser.add_argument("--timeout", default=DEFAULT_TIMEOUT, type=float, help="Socket timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print the API command without sending it.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="action", required=True)

    raw = subparsers.add_parser("raw", help="Send a raw chassis API command.")
    raw.add_argument("command")

    subparsers.add_parser("status", help="Read robot global status.")
    subparsers.add_parser("markers", help="List all marker points.")
    subparsers.add_parser("marker-brief", help="List marker names and type/floor summary.")
    subparsers.add_parser("cancel", help="Cancel active navigation.")

    move_marker = subparsers.add_parser("move-marker", help="Move to a named marker.")
    move_marker.add_argument("name")

    move_location = subparsers.add_parser("move-location", help="Move to a map coordinate.")
    move_location.add_argument("x", type=float)
    move_location.add_argument("y", type=float)
    move_location.add_argument("theta", type=float)

    move_markers = subparsers.add_parser("move-markers", help="Move through several markers.")
    move_markers.add_argument("names", nargs="+")
    move_markers.add_argument("--distance-tolerance", default=0.5, type=float)
    move_markers.add_argument("--count", default=1, type=int)

    insert_current = subparsers.add_parser("insert-current", help="Create a marker at the current robot pose.")
    insert_current.add_argument("name")
    insert_current.add_argument("--type", default=0, type=int)
    insert_current.add_argument("--num", type=int)

    insert_pose = subparsers.add_parser("insert-pose", help="Create a marker at an explicit map pose.")
    insert_pose.add_argument("name")
    insert_pose.add_argument("--x", required=True, type=float)
    insert_pose.add_argument("--y", required=True, type=float)
    insert_pose.add_argument("--theta", required=True, type=float)
    insert_pose.add_argument("--floor", required=True, type=int)
    insert_pose.add_argument("--type", default=0, type=int)
    insert_pose.add_argument("--num", type=int)

    delete_marker = subparsers.add_parser("delete-marker", help="Delete a marker.")
    delete_marker.add_argument("name")

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = build_command(args)

    if args.dry_run:
        print(command)
        return 0

    try:
        raw_response = request(command, args.host, args.port, args.timeout)
    except OSError as exc:
        print(f"Failed to send command to {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    print_response(raw_response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

