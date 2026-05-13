from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import quote


DEFAULT_HOST = "192.168.10.10"
DEFAULT_PORT = 31001
DEFAULT_TIMEOUT = 3.0


class ChassisNavigationError(RuntimeError):
    """Raised when the chassis API cannot be reached or returns bad data."""


def _encode_marker(name: str) -> str:
    return quote(name, safe="")


def _parse_lines(raw: str) -> List[Any]:
    if not raw:
        return []

    parsed: List[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append(line)
    return parsed


@dataclass
class ChassisNavigationClient:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout: float = DEFAULT_TIMEOUT

    def request(self, command: str) -> str:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(command.encode("utf-8"))

                chunks: List[bytes] = []
                while True:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
        except OSError as exc:
            raise ChassisNavigationError(
                f"Failed to send command to {self.host}:{self.port}: {exc}"
            ) from exc

        return b"".join(chunks).decode("utf-8", errors="replace").strip()

    def _result(self, mode: str, command: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        raw = self.request(command)
        result = {
            "backend": "tcp",
            "mode": mode,
            "host": self.host,
            "port": self.port,
            "command": command,
            "response": _parse_lines(raw),
        }
        if extra:
            result.update(extra)
        return result

    def status(self) -> Dict[str, Any]:
        return self._result("status", "/api/robot_status")

    def markers(self) -> Dict[str, Any]:
        return self._result("markers", "/api/markers/query_list")

    def marker_brief(self) -> Dict[str, Any]:
        return self._result("marker_brief", "/api/markers/query_brief")

    def move_marker(self, name: str) -> Dict[str, Any]:
        if not name:
            raise ChassisNavigationError("marker name must be non-empty")
        command = f"/api/move?marker={_encode_marker(name)}"
        return self._result("marker", command, {"marker": name})

    def move_location(self, x: float, y: float, theta: float) -> Dict[str, Any]:
        command = f"/api/move?location={float(x)},{float(y)},{float(theta)}"
        return self._result("location", command, {"x": float(x), "y": float(y), "theta": float(theta)})

    def move_markers(
        self,
        names: Iterable[str],
        distance_tolerance: float = 0.5,
        count: int = 1,
    ) -> Dict[str, Any]:
        marker_list = [name for name in names if name]
        if not marker_list:
            raise ChassisNavigationError("marker sequence must be non-empty")
        joined = ",".join(marker_list)
        command = (
            f"/api/move?markers={quote(joined, safe=',')}"
            f"&distance_tolerance={float(distance_tolerance)}&count={int(count)}"
        )
        return self._result(
            "markers",
            command,
            {
                "markers": marker_list,
                "distance_tolerance": float(distance_tolerance),
                "count": int(count),
            },
        )

    def cancel(self) -> Dict[str, Any]:
        return self._result("cancel", "/api/move/cancel")
