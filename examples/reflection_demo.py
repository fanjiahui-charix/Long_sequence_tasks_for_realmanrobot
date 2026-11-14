"""Decision-reflection benchmark with repeatable precondition-failure injection.

With --llm qwen, reflection and the follow-up mission use the configured API
model. Run after `python -m pip install -e .`; robot state uses the Mock backend.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

from robot_agent.agent import ReActAgent
from robot_agent.backends.mock_robot import MockRobotBackend, mock_calibration
from robot_agent.demo import demo_mission
from robot_agent.llm_adapter import (
    ScriptedDecisionClient,
    StructuredLLMClient,
    config_from_environment,
    load_local_env,
)
from robot_agent.memory.episodic import EpisodicMemory
from robot_agent.schemas import AgentDecision
from robot_agent.tool_registry import ToolRegistry
from robot_agent.verifier import DeterministicVerifier


class CapturingClient:
    """Capture the exact model inputs and structured decisions for inspection."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.decisions = []
        self.reflections = []

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def decide(self, context):
        decision = await self.delegate.decide(context)
        self.decisions.append((copy.deepcopy(context), decision))
        return decision

    async def summarize_experience(self, context):
        self.reflections.append(copy.deepcopy(context))
        return await self.delegate.summarize_experience(context)


class ControlledHistoricalPolicy(CapturingClient):
    async def decide(self, context):
        if context["working_memory"]["current_location"] != "B":
            decision = AgentDecision(
                action_type="CALL_TOOL",
                tool_name="navigate_to",
                arguments={"target": "B"},
                decision_summary="受控历史案例：先到 B。",
            )
        else:
            decision = AgentDecision(
                action_type="CALL_TOOL",
                tool_name="grasp_object",
                arguments={
                    "object_category": "glasses_case",
                    "pose_reference": "missing-pose",
                },
                decision_summary="受控错误提案：没有有效位姿仍反复提出抓取。",
            )
        self.decisions.append((copy.deepcopy(context), decision))
        return decision


def make_agent(client, store, backend, trace_path):
    return ReActAgent(
        client,
        ToolRegistry(
            backend, DeterministicVerifier(mock_calibration(), base_frame="mock_base")
        ),
        memory=store,
        trace_path=trace_path,
        consolidation_timeout_s=60,
    )


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_demo(output_dir, delegate):
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex[:8]
    database = output_dir / ("history-" + run_id + ".sqlite3")
    historical_trace = output_dir / ("historical-" + run_id + ".jsonl")
    current_trace = output_dir / ("current-" + run_id + ".jsonl")
    historical_client = ControlledHistoricalPolicy(delegate)
    historical_backend = MockRobotBackend()
    with EpisodicMemory(database) as store:
        historical = await make_agent(
            historical_client,
            store,
            historical_backend,
            historical_trace,
        ).run(demo_mission())
        episodes = store.retrieve()
        if historical.status != "REQUEST_HELP" or len(episodes) != 1:
            raise RuntimeError(
                "historical case did not produce one usable reflected episode"
            )
        episode = episodes[0]
        count = store.connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        if (
            not episode.decision_error_verified
            or episode.verified
            or historical_backend.calls != ["navigate_to"]
        ):
            raise RuntimeError("historical evidence does not match the controlled case")

    # Reopen the on-disk SQLite database: this is cross-mission memory, not a
    # retained Python object. A fresh robot starts at A with no object held.
    current_client = CapturingClient(delegate)
    with EpisodicMemory(database) as store:
        current = await make_agent(
            current_client, store, MockRobotBackend(), current_trace
        ).run(demo_mission())

    selected = next(
        (
            (context, decision)
            for context, decision in current_client.decisions
            if context["working_memory"]["current_location"] == "B"
            and context["working_memory"]["pose"] is None
        ),
        None,
    )
    if selected is None:
        raise RuntimeError("no decision at B without a current pose was recorded")
    context, next_decision = selected
    injected = context["episodic_memory"]
    injected_ids = [item["episode_id"] for item in injected]
    if (
        episode.episode_id not in injected_ids
        or next_decision.tool_name != "locate_object"
    ):
        raise RuntimeError(
            "the historical constraint was not injected before localization"
        )
    if current.status != "COMPLETED" or not current.final_verification.verified:
        raise RuntimeError("the follow-up mission did not pass final verification")

    working = context["working_memory"]
    result = {
        "evaluation": "Mock/API-level Evaluation",
        "run_id": run_id,
        "database_file": database.name,
        "trace_files": {
            "historical": historical_trace.name,
            "current": current_trace.name,
        },
        "historical_decision_origin": "deterministic precondition-failure injection policy",
        "reflection_provider": "qwen"
        if getattr(delegate, "is_real_llm", False)
        else "scripted template (not an LLM)",
        "model": getattr(getattr(delegate, "config", None), "model", None),
        "historical_status": historical.status,
        "historical_failure_count": historical.metrics.failures,
        "historical_dispatched_tools": historical_backend.calls,
        "episode_count": count,
        "prior_ep_id": episode.episode_id,
        "historical_decision_evidence": historical_client.reflections[0][
            "decision_trace"
        ],
        "reflected_experience": episode.experience.model_dump(mode="json"),
        "working_memory": {
            key: working[key]
            for key in ("current_location", "pose", "grasp_state", "last_error")
        },
        "episodic_memory": next(
            item for item in injected if item["episode_id"] == episode.episode_id
        ),
        "injected_episode_ids": injected_ids,
        "next_decision": next_decision.model_dump(mode="json"),
        "mission_completed": current.status == "COMPLETED",
        "final_verification": current.final_verification.model_dump(mode="json"),
        "llm_calls": historical.metrics.llm_calls + current.metrics.llm_calls,
        "reflection_llm_calls": historical.metrics.consolidation_llm_calls,
        "decision_calls": current.metrics.decision_calls,
        "metrics": {
            "historical": historical.metrics.model_dump(mode="json"),
            "current": current.metrics.model_dump(mode="json"),
        },
        "interpretation": "End-to-end check of reflection, persistence, retrieval, context injection and follow-up tool choice.",
    }
    write_json(output_dir / "historical.json", historical.model_dump(mode="json"))
    write_json(output_dir / "current.json", current.model_dump(mode="json"))
    write_json(output_dir / "reflection-input.json", historical_client.reflections[0])
    write_json(output_dir / "decision-input.json", context)
    write_json(output_dir / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", choices=["scripted", "qwen"], default="scripted")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("runtime/reflection-demo")
    )
    args = parser.parse_args()
    if args.llm == "qwen":
        load_local_env(args.env_file)
        delegate = StructuredLLMClient(config_from_environment(max_tokens=2200))
    else:
        delegate = ScriptedDecisionClient()
    result = asyncio.run(run_demo(args.output_dir, delegate))
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "historical_status",
                    "episode_count",
                    "prior_ep_id",
                    "next_decision",
                    "mission_completed",
                    "llm_calls",
                    "reflection_llm_calls",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
