import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from robot_agent.llm_adapter import LLMConfig, LLMError, StructuredLLMClient
from robot_agent.mission import understand_mission
from robot_agent.schemas import AgentDecision


@pytest.fixture
def http_api():
    requests = []
    response = {
        "action_type": "CALL_TOOL",
        "tool_name": "navigate_to",
        "arguments": {"target": "B"},
        "decision_summary": "Navigate to source.",
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                {
                    "path": self.path,
                    "body": json.loads(
                        self.rfile.read(int(self.headers["Content-Length"]))
                    ),
                }
            )
            payload = json.dumps(
                {
                    "model": "test-vl",
                    "choices": [{"message": {"content": json.dumps(response)}}],
                    "usage": {"total_tokens": 10},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_port), requests, response
    server.shutdown()
    server.server_close()
    thread.join()


def test_qwen_transport_and_pydantic_structured_output(http_api):
    base, requests, response = http_api
    client = StructuredLLMClient(
        LLMConfig(base_url=base + "/v1", api_key="test-secret", model="test-vl")
    )
    result = asyncio.run(
        client.decide(
            {"working_memory": {}, "mission": {}, "tools": [], "episodic_memory": []}
        )
    )
    assert isinstance(result, AgentDecision)
    assert requests[0]["path"] == "/v1/chat/completions"
    assert requests[0]["body"]["response_format"] == {"type": "json_object"}
    assert "test-secret" not in str(client.config)
    assert "test-secret" not in json.dumps(client.last_response_meta)
    response.clear()
    response.update(
        action_type="CALL_TOOL",
        tool_name="joint_move",
        arguments={},
        decision_summary="bad",
    )
    with pytest.raises(ValidationError):
        asyncio.run(client.decide({}))


def test_image_understanding_keeps_mapping_outside_llm_control(http_api, tmp_path):
    base, requests, response = http_api
    image = tmp_path / "scene.png"
    image.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
        )
    )
    response.clear()
    response.update(
        start_location="A",
        source_location="B",
        target_object="black glasses case",
        object_category="glasses_case",
        scene_entities=["A", "B", "table", "black glasses case"],
    )
    client = StructuredLLMClient(
        LLMConfig(base_url=base, api_key="test", model="test-vl")
    )
    mission = asyncio.run(
        understand_mission(
            client,
            "Go from A to B, retrieve the black glasses case and return to A.",
            image,
            {"A": "real_marker1", "B": "real_marker2"},
        )
    )
    assert mission.location_mapping == {"A": "real_marker1", "B": "real_marker2"}
    assert mission.scene_image_sha256
    content = requests[-1]["body"]["messages"][-1]["content"]
    assert content[0]["type"] == "image_url" and content[0]["image_url"][
        "url"
    ].startswith("data:image/png;base64,")
    response["location_mapping"] = {"A": "invented"}
    with pytest.raises(ValidationError):
        asyncio.run(understand_mission(client, "retrieve", image, {"A": "x", "B": "y"}))
    response.pop("location_mapping")
    response["source_location"] = "C"
    with pytest.raises(ValidationError):
        asyncio.run(understand_mission(client, "retrieve", image, {"A": "x", "B": "y"}))


def test_text_only_client_cannot_silently_claim_image_understanding(tmp_path):
    image = tmp_path / "scene.png"
    image.write_bytes(b"image")
    client = StructuredLLMClient(
        LLMConfig(
            provider="openai-compatible",
            base_url="http://localhost:1",
            model="text",
            supports_images=False,
        )
    )
    with pytest.raises(LLMError, match="vision"):
        asyncio.run(client.structured(AgentDecision, "JSON", "hello", image_path=image))
    assert client.request_count == 0
