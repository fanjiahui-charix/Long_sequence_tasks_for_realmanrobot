from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from .models import jsonable
from .state import WorldState


class JsonlTraceWriter:
    def __init__(
        self,
        path: str | Path,
        *,
        mission_id: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.mission_id = mission_id
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream: TextIO = self.path.open("a", encoding="utf-8", newline="\n")

    def record(
        self,
        event_type: str,
        *,
        state: WorldState | None = None,
        **payload: Any,
    ) -> None:
        event: dict[str, Any] = {
            "timestamp": float(self.clock()),
            "mission_id": self.mission_id,
            "event_type": event_type,
        }
        event.update({key: jsonable(value) for key, value in payload.items() if value is not None})
        if state is not None:
            event["state_hash"] = state.stable_hash()
            event["state"] = state.snapshot()
        self._stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        self._stream.write("\n")
        self._stream.flush()

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.flush()
            self._stream.close()

    def __enter__(self) -> JsonlTraceWriter:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()


class NullTraceWriter:
    path: None = None

    def record(self, _event_type: str, **_payload: Any) -> None:
        return None

    def close(self) -> None:
        return None
