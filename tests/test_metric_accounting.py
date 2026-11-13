import asyncio
import json

from robot_agent.agent import ReActAgent
from robot_agent.backends.mock_robot import MockRobotBackend
from robot_agent.llm_adapter import StructuredLLMClient, LLMConfig
from robot_agent.tool_registry import ToolRegistry


def test_no_credentials_means_zero_outbound_llm_calls(mission, verifier):
    client = StructuredLLMClient(LLMConfig(api_key=None))
    report = asyncio.run(
        ReActAgent(client, ToolRegistry(MockRobotBackend(), verifier)).run(mission)
    )
    assert report.status == "REQUEST_HELP"
    assert client.request_count == 0
    assert report.metrics.llm_calls == 0


def test_demo_total_time_includes_scene_understanding(monkeypatch, tmp_path):
    from robot_agent import cli
    from robot_agent.llm_adapter import ScriptedDecisionClient
    from robot_agent.mission import MissionDraft

    class Client(ScriptedDecisionClient):
        def __init__(self, config):
            super().__init__()
            self.request_count = 1
            self.latencies = [0.02]

        async def structured(self, *args, **kwargs):
            await asyncio.sleep(0.02)
            return MissionDraft(
                start_location="A",
                source_location="B",
                target_object="black glasses case",
                object_category="glasses_case",
                scene_entities=["A", "B", "table", "black glasses case"],
            )

    monkeypatch.setattr(cli, "StructuredLLMClient", Client)
    monkeypatch.setattr(cli, "load_local_env", lambda path: None)
    monkeypatch.setattr(cli, "config_from_environment", lambda **kwargs: None)
    image = tmp_path / "scene.png"
    image.write_bytes(b"test image")
    args = cli.build_parser().parse_args(
        ["demo", "--llm", "qwen", "--image", str(image), "--output-dir", str(tmp_path)]
    )
    assert asyncio.run(cli.demo(args)) == 0
    report = json.loads((tmp_path / "mission_report.json").read_text(encoding="utf-8"))
    assert report["metrics"]["mission_understanding_sec"] >= 0.015
    assert (
        report["metrics"]["total_execution_sec"]
        >= report["metrics"]["mission_understanding_sec"]
    )
