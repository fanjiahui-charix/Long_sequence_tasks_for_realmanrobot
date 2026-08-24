from __future__ import annotations

import json
from typing import Any


def extract_machine_result(stdout: str) -> dict[str, Any]:
    """Return the final JSON object from a log-contaminated subprocess stream."""
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    if not candidates:
        raise RuntimeError("subprocess produced no JSON object")
    return candidates[-1]
