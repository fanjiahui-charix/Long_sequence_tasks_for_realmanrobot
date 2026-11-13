from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from .agent import ReActAgent
from .backends.mock_robot import MockRobotBackend, mock_calibration
from .demo import demo_mission
from .evaluation import SCENARIOS, evaluate_async
from .llm_adapter import (
    LLMError,
    ScriptedDecisionClient,
    StructuredLLMClient,
    config_from_environment,
    load_local_env,
)
from .memory.episodic import EpisodicMemory
from .mission import understand_mission
from .tool_registry import ToolRegistry
from .verifier import DeterministicVerifier

ROOT = Path(__file__).resolve().parents[1]


def build_parser():
    parser = argparse.ArgumentParser(
        description="Single ReAct + Working/Episodic Memory Robot Agent"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser(
        "demo", help="A→B→A; mock robot by default, no credentials needed"
    )
    demo.add_argument("--llm", choices=["scripted", "qwen"], default="scripted")
    demo.add_argument("--memory", action="store_true")
    demo.add_argument(
        "--fault",
        choices=[
            "NAV_TIMEOUT",
            "OBJECT_NOT_FOUND",
            "POSE_STALE",
            "GRASP_NOT_HELD",
            "TOOL_EXECUTION_UNKNOWN",
        ],
    )
    demo.add_argument("--output-dir", type=Path, default=Path("runtime/demo"))
    demo.add_argument("--image", type=Path)
    demo.add_argument("--instruction", default=demo_mission().instruction)
    demo.add_argument(
        "--mission-file",
        type=Path,
        help="Prevalidated MissionSpec; otherwise --image is required with Qwen",
    )
    demo.add_argument("--env-file", type=Path, default=ROOT / ".env")
    demo.add_argument("--model")
    demo.add_argument("--backend", choices=["mock", "realman"], default="mock")
    demo.add_argument("--hardware-config", type=Path)
    demo.add_argument("--enable-hardware", action="store_true")
    evaluation = commands.add_parser(
        "evaluate", help="A/B benchmark against identical mock faults"
    )
    evaluation.add_argument("--llm", choices=["scripted", "qwen"], default="scripted")
    evaluation.add_argument("--repetitions", type=int, default=3)
    evaluation.add_argument(
        "--scenarios", help="Comma-separated subset: " + ", ".join(SCENARIOS)
    )
    evaluation.add_argument(
        "--output-dir", type=Path, default=Path("runtime/evaluation")
    )
    evaluation.add_argument("--env-file", type=Path, default=ROOT / ".env")
    evaluation.add_argument("--model")
    preflight = commands.add_parser(
        "preflight", help="Offline hardware-config validation; sends no robot commands"
    )
    preflight.add_argument("--hardware-config", required=True, type=Path)
    return parser


async def demo(args):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mission = demo_mission()
    client = ScriptedDecisionClient()
    understanding_sec = 0.0
    if args.llm == "qwen":
        load_local_env(args.env_file)
        client = StructuredLLMClient(config_from_environment(model=args.model))
        if args.mission_file:
            from .schemas import MissionSpec

            mission = MissionSpec.model_validate_json(
                args.mission_file.read_text(encoding="utf-8")
            )
        else:
            if not args.image:
                raise ValueError(
                    "Qwen mission understanding requires --image or a prevalidated --mission-file"
                )
            understanding_started = time.perf_counter()
            mission = await understand_mission(
                client, args.instruction, args.image, mission.location_mapping
            )
            understanding_sec = time.perf_counter() - understanding_started
    faults = {}
    if args.fault:
        skill = (
            "navigate_to"
            if args.fault == "NAV_TIMEOUT"
            else "locate_object"
            if args.fault == "OBJECT_NOT_FOUND"
            else "grasp_object"
        )
        faults[skill] = [args.fault]
    backend = MockRobotBackend(faults=faults)
    verifier = DeterministicVerifier(mock_calibration(), base_frame="mock_base")
    if args.backend == "realman":
        if not args.enable_hardware or not args.hardware_config:
            raise ValueError(
                "real robot requires --enable-hardware and --hardware-config"
            )
        if args.fault:
            raise ValueError("fault injection is restricted to the mock backend")
        from .hardware import build_realman_backend

        backend, verifier, mapping = build_realman_backend(
            args.hardware_config, enable_hardware=True
        )
        mission = mission.model_copy(update={"location_mapping": mapping})
        # Revalidate the trusted mapping; model_copy alone does not validate.
        mission = type(mission).model_validate(mission.model_dump())
    store = (
        EpisodicMemory(args.output_dir / "episodes.sqlite3") if args.memory else None
    )
    try:
        report = await ReActAgent(
            client,
            ToolRegistry(backend, verifier),
            memory=store,
            trace_path=args.output_dir / "trace.jsonl",
        ).run(mission)
    finally:
        if store:
            store.close()
    if isinstance(client, StructuredLLMClient):
        report.metrics.llm_calls = client.request_count
        report.metrics.llm_latency_sec = client.latencies
    report.metrics.mission_understanding_sec = understanding_sec
    report.metrics.total_execution_sec += understanding_sec
    report.evaluation = (
        "Mock/API-level Evaluation"
        if args.backend == "mock"
        else "Real hardware run (requires operator validation)"
    )
    (args.output_dir / "mission_report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "evaluation": report.evaluation,
                "decision_provider": args.llm,
                "status": report.status,
                "robot_at_A": report.final_verification.evidence.get(
                    "robot_at_start", False
                ),
                "object_held": report.final_verification.evidence.get(
                    "object_held", False
                ),
                "llm_calls": report.metrics.llm_calls,
                "decision_calls": report.metrics.decision_calls,
                "failures": report.metrics.failures,
                "recoveries": report.metrics.recoveries,
                "report": str(args.output_dir / "mission_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.status == "COMPLETED" else 2


async def async_main(args):
    if args.command == "demo":
        return await demo(args)
    if args.command == "preflight":
        from .hardware import preflight

        missing = preflight(args.hardware_config)
        print(
            json.dumps(
                {
                    "hardware_ready": not missing,
                    "missing": missing,
                    "mode": "offline/no commands",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if missing else 0
    factory = None
    if args.llm == "qwen":
        load_local_env(args.env_file)
        config = config_from_environment(model=args.model)
        factory = lambda: StructuredLLMClient(config)
    result = await evaluate_async(
        repetitions=args.repetitions,
        output_dir=args.output_dir,
        client_factory=factory,
        scenario_names=args.scenarios.split(",") if args.scenarios else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main():
    args = build_parser().parse_args()
    try:
        return asyncio.run(async_main(args))
    except (ValueError, LLMError) as exc:
        print(
            json.dumps(
                {"status": "REQUEST_HELP", "error": str(exc)}, ensure_ascii=False
            )
        )
        return 2
    except KeyboardInterrupt:
        print("Mission interrupted; verify physical state before restarting.")
        return 130
