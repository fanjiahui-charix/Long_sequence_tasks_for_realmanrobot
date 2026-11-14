from __future__ import annotations

import asyncio
import json
import statistics
from pathlib import Path
from uuid import uuid4

from .agent import ReActAgent
from .backends.mock_robot import MockRobotBackend, mock_calibration
from .demo import demo_mission
from .llm_adapter import ScriptedDecisionClient
from .memory.episodic import EpisodicMemory
from .tool_registry import ToolRegistry
from .verifier import DeterministicVerifier

SCENARIOS = {
    "normal": {},
    "nav_timeout": {"navigate_to": ["NAV_TIMEOUT"]},
    "object_not_found": {"locate_object": ["OBJECT_NOT_FOUND"]},
    "pose_stale": {"grasp_object": ["POSE_STALE"]},
    "grasp_not_held": {"grasp_object": ["GRASP_NOT_HELD"]},
    "execution_unknown": {"grasp_object": ["TOOL_EXECUTION_UNKNOWN"]},
    "drop_on_return": {"navigate_to": [None, "DROP_OBJECT"]},
    "repeated_failure": {"locate_object": ["OBJECT_NOT_FOUND"] * 20},
    "missing_feedback": {},
    "motion_unsettled": {},
}


class EvidenceFaultBackend(MockRobotBackend):
    def __init__(self, scenario, **kwargs):
        super().__init__(**kwargs)
        self.scenario = scenario

    async def observe_robot_state(self, mission):
        obs = await super().observe_robot_state(mission)
        if self.scenario == "missing_feedback":
            obs.gripper_samples = []
        if self.scenario == "motion_unsettled":
            obs.arm_idle = False
            obs.motion_settled = False
        return obs


def summarize(rows):
    count = len(rows)
    completed = sum(row["status"] == "COMPLETED" for row in rows)
    false = sum(
        row["status"] == "COMPLETED" and not row["ground_truth_success"] for row in rows
    )
    failures = sum(row["metrics"]["failures"] for row in rows)
    recovered = sum(row["metrics"]["recoveries"] for row in rows)
    repeated = sum(row["metrics"]["repeated_failures"] for row in rows)
    latencies = [value for row in rows for value in row["metrics"]["llm_latency_sec"]]
    return {
        "mission_count": count,
        "completed_count": completed,
        "task_completion_rate": completed / count if count else 0,
        "failure_events": failures,
        "recovered_failure_events": recovered,
        "recovery_success_rate": recovered / failures if failures else None,
        "false_completion_count": false,
        "false_completion_rate": false / count if count else 0,
        "repeated_failure_events": repeated,
        "repeated_failure_rate": repeated / failures if failures else None,
        "llm_calls": sum(r["metrics"]["llm_calls"] for r in rows),
        "average_llm_latency_sec": statistics.mean(latencies) if latencies else None,
        "average_total_execution_sec": statistics.mean(
            r["metrics"]["total_execution_sec"] for r in rows
        )
        if count
        else None,
        "decision_calls": sum(r["metrics"]["decision_calls"] for r in rows),
        "episodes_retrieved": sum(r["metrics"]["episodes_retrieved"] for r in rows),
    }


async def evaluate_async(
    *,
    repetitions=3,
    output_dir="runtime/evaluation",
    client_factory=None,
    scenario_names=None,
):
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    selected = list(SCENARIOS) if scenario_names is None else list(scenario_names)
    if not selected or any(name not in SCENARIOS for name in selected):
        raise ValueError("unknown or empty evaluation scenarios")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    store = EpisodicMemory(output / ("episodes_" + str(uuid4()) + ".sqlite3"))
    try:
        for group in ["A", "B"]:
            for repetition in range(repetitions):
                for scenario in selected:
                    mission = demo_mission(f"{group}-{repetition}-{scenario}")
                    backend = EvidenceFaultBackend(scenario, faults=SCENARIOS[scenario])
                    client = (
                        client_factory() if client_factory else ScriptedDecisionClient()
                    )
                    verifier = DeterministicVerifier(
                        mock_calibration(), base_frame="mock_base"
                    )
                    trace_path = output / "traces" / (mission.mission_id + ".jsonl")
                    report = await ReActAgent(
                        client,
                        ToolRegistry(backend, verifier),
                        memory=store if group == "B" else None,
                        trace_path=trace_path,
                        max_turns=20,
                    ).run(mission)
                    row = {
                        "group": group,
                        "scenario": scenario,
                        "repetition": repetition,
                        "mission_id": mission.mission_id,
                        "status": report.status,
                        "ground_truth_success": backend.ground_truth(mission),
                        "final_verified": report.final_verification.verified,
                        "metrics": report.metrics.model_dump(mode="json"),
                        "model": getattr(
                            getattr(client, "config", None), "model", None
                        ),
                    }
                    rows.append(row)
                    print(
                        json.dumps(
                            {
                                "progress": mission.mission_id,
                                "status": report.status,
                                "llm_calls": report.metrics.llm_calls,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
    finally:
        store.close()
    result = {
        "evaluation": "Mock/API-level Evaluation",
        "decision_provider": "real LLM"
        if client_factory
        else "deterministic scripted policy",
        "repetitions": repetitions,
        "scenarios": selected,
        "groups": {
            group: summarize([row for row in rows if row["group"] == group])
            for group in ["A", "B"]
        },
        "limitations": [
            "Backend: deterministic MockRobotBackend with injectable fault sequences.",
            "The same policy, tools, verifier and ordered fault suite are used in A/B; B alone has persistent episodic memory.",
            "Decision client: scripted by default; --llm qwen selects the configured API model.",
            "Measurement scope: software/API-level task execution and recovery.",
        ],
    }
    (output / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "missions.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return result


def evaluate(**kwargs):
    return asyncio.run(evaluate_async(**kwargs))
