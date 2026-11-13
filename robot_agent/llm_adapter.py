from __future__ import annotations

import copy
import asyncio
import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from .schemas import Contract
from .schemas import AgentDecision


class LLMError(RuntimeError):
    pass


class LLMConfig(Contract):
    provider: Literal["qwen", "openai-compatible", "ollama"] = "qwen"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen3-vl-plus"
    vision_model: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    supports_images: bool = True
    temperature: float = Field(default=0, ge=0, le=2)
    timeout_sec: float = Field(default=60, gt=0)
    max_tokens: int = Field(default=1500, gt=0)
    structured_mode: Literal["json_object", "json_schema"] = "json_object"

    @model_validator(mode="after")
    def safe_base_url(self):
        u = urlsplit(self.base_url)
        if not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError(
                "base_url must be an HTTP endpoint without credentials or query"
            )
        if u.scheme != "https" and not (
            u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("remote model endpoints require HTTPS")
        return self


def load_local_env(path):
    """Load an explicitly selected ignored dotenv file without printing values."""
    path = Path(path)
    if path.is_file():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def config_from_environment(**overrides):
    values = {
        "provider": "qwen",
        "model": os.getenv("QWEN_MODEL", "qwen3-vl-plus"),
        "base_url": os.getenv(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        "api_key": os.getenv("DASHSCOPE_API_KEY"),
        "vision_model": os.getenv("QWEN_VISION_MODEL"),
    }
    values.update({k: v for k, v in overrides.items() if v is not None})
    return LLMConfig(**values)


class StructuredLLMClient:
    """Fresh Pydantic-validated decisions over the existing Qwen HTTP protocol.

    No old planner schema, prompt or execution logic is imported. json_object
    supports the wider Qwen family; json_schema is opt-in per provider capability.
    """

    is_real_llm = True

    def __init__(self, config: LLMConfig):
        self.config = config
        self.request_count = 0
        self.last_response_meta = {}
        self.latencies = []

    def _post(self, path, payload):
        key = self.config.api_key.get_secret_value() if self.config.api_key else None
        if self.config.provider == "qwen" and not key:
            raise LLMError("DASHSCOPE_API_KEY is not configured")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + path,
            json.dumps(payload).encode("utf-8"),
            headers,
            method="POST",
        )
        self.request_count += 1
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_sec
            ) as response:
                return json.loads(response.read(4 * 1024 * 1024))
        except urllib.error.HTTPError as exc:
            # Response bodies can contain request data. Never include them in logs.
            code = "provider_error"
            try:
                body = json.loads(exc.read(65536))
                candidate = str(body.get("error", body).get("code", code))
                if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", candidate):
                    code = candidate
            except (ValueError, AttributeError):
                pass
            raise LLMError(f"model API HTTP {exc.code}: {code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise LLMError("model API connection failed or timed out") from None

    async def structured(self, schema, system, user, *, image_path=None):
        image_b64 = None
        mime = None
        if image_path is not None:
            if not self.config.supports_images:
                raise LLMError(
                    "a vision-capable model must be configured for scene input"
                )
            path = Path(image_path)
            data = path.read_bytes()
            if len(data) > 8 * 1024 * 1024:
                raise LLMError("scene image exceeds 8 MiB")
            mime = mimetypes.guess_type(path.name)[0]
            if mime not in {"image/png", "image/jpeg", "image/webp"}:
                raise LLMError("scene input must be PNG, JPEG or WebP")
            image_b64 = base64.b64encode(data).decode("ascii")
        system = (
            system
            + "\nReturn JSON matching this JSON Schema:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        model = (
            (self.config.vision_model or self.config.model)
            if image_b64
            else self.config.model
        )
        if self.config.provider == "ollama":
            message = {"role": "user", "content": user}
            if image_b64:
                message["images"] = [image_b64]
            payload = {
                "model": model,
                "messages": [{"role": "system", "content": system}, message],
                "format": schema.model_json_schema(),
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
            }
            endpoint = "/api/chat"
        else:
            content = (
                user
                if not image_b64
                else [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                    {"type": "text", "text": user},
                ]
            )
            response_format = {"type": "json_object"}
            if self.config.structured_mode == "json_schema":
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "response_format": response_format,
            }
            if self.config.provider == "qwen":
                payload["enable_thinking"] = False
            endpoint = "/chat/completions"
        tick = time.perf_counter()
        try:
            completion = await asyncio.to_thread(self._post, endpoint, payload)
        finally:
            self.latencies.append(time.perf_counter() - tick)
        self.last_response_meta = {
            "request_model": model,
            "response_model": completion.get("model"),
            "response_id": completion.get("id"),
            "usage": completion.get("usage"),
            "latency_sec": self.latencies[-1],
        }
        try:
            content = (
                completion["message"]["content"]
                if self.config.provider == "ollama"
                else completion["choices"][0]["message"]["content"]
            )
            if not isinstance(content, str):
                raise TypeError()
        except (KeyError, IndexError, TypeError):
            raise LLMError("model returned no structured content") from None
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        return schema.model_validate_json(content)

    async def decide(self, context):
        system = (Path(__file__).parent / "prompts/react_system.md").read_text(
            encoding="utf-8"
        )
        return await self.structured(
            AgentDecision, system, json.dumps(context, ensure_ascii=False)
        )


class ScriptedDecisionClient:
    """A transparent deterministic policy for software tests. This is not an LLM.

    The same fallback rules are used in both experimental arms. Memory may suggest
    a recovery tool but is never converted into physical state or a saved pose.
    """

    is_real_llm = False

    def __init__(self):
        self.contexts = []

    async def decide(self, context):
        self.contexts.append(copy.deepcopy(context))
        w = context["working_memory"]
        mission = context["mission"]

        def call(tool, args, why):
            return AgentDecision(
                action_type="CALL_TOOL",
                tool_name=tool,
                arguments=args,
                decision_summary=why,
            )

        if w["uncertain_action"]:
            return call(
                "observe_robot_state",
                {},
                "Read live state before any further physical action.",
            )
        if (
            w["grasp_state"] == "HELD"
            and w["grasped_object"] == mission["object_category"]
        ):
            if w["current_location"] == mission["start_location"]:
                return AgentDecision(
                    action_type="FINISH",
                    decision_summary="Request independent final verification of return and held target.",
                )
            return call(
                "navigate_to",
                {"target": mission["start_location"]},
                "Carry the verified held target back to start.",
            )
        if w["grasp_state"] == "UNKNOWN":
            if len(w["completed_actions"]) >= 2 and all(
                a["tool"] == "observe_robot_state" for a in w["completed_actions"][-2:]
            ):
                return AgentDecision(
                    action_type="REQUEST_HELP",
                    decision_summary="Repeated current observations cannot establish holding state.",
                )
            return call(
                "observe_robot_state",
                {},
                "Actual holding state is unknown; read sensors.",
            )
        if w["current_location"] != mission["source_location"]:
            return call(
                "navigate_to",
                {"target": mission["source_location"]},
                "Reach the object source.",
            )
        # Only use a matching verified recovery, and recheck all current preconditions.
        for ep in context["episodic_memory"]:
            if (
                ep["failure_type"] == w["last_error"]
                and ep["recovery_strategy"]
                and ep["recovery_strategy"][0] == "locate_object"
                and w["pose"] is None
            ):
                return call(
                    "locate_object",
                    {"object_category": mission["object_category"]},
                    "Verified past recovery suggests reacquiring a current pose.",
                )
        if w["pose"] is None:
            return call(
                "locate_object",
                {"object_category": mission["object_category"]},
                "Acquire fresh target pose from the current scene.",
            )
        return call(
            "grasp_object",
            {
                "object_category": mission["object_category"],
                "pose_reference": w["pose"]["pose_id"],
            },
            "Grasp using the currently verified pose reference.",
        )
