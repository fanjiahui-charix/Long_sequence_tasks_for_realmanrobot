from __future__ import annotations

import json
import time
from pathlib import Path
from pydantic import Field
from .schemas import Contract, Verification
from .state import WorkingMemory


class MissionMetrics(Contract):
    decision_calls: int = 0
    llm_calls: int = 0
    llm_latency_sec: list[float] = Field(default_factory=list)
    decision_latency_sec: list[float] = Field(default_factory=list)
    tool_execution_sec: float = 0
    memory_retrieval_sec: float = 0
    mission_understanding_sec: float = 0
    total_execution_sec: float = 0
    failures: int = 0
    recoveries: int = 0
    repeated_failures: int = 0
    finish_rejections: int = 0
    episodes_retrieved: int = 0


class MissionReport(Contract):
    status: str
    state: WorkingMemory
    final_verification: Verification
    metrics: MissionMetrics
    trace: list[dict] = Field(default_factory=list)
    evaluation: str = "API-level Evaluation"


class TraceRecorder:
    def __init__(self, path=None):
        self.events = []
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, event, **data):
        value = {"event": event, "timestamp": time.time(), **data}
        self.events.append(value)
        if self.path:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(value, ensure_ascii=False) + "\n")
