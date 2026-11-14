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
from .schemas import AgentDecision, Contract, ExperienceSummary


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


def _reflection_inputs(context):
    """Keep turn references and error attribution tied to runtime records."""
    failure_turn = context.get("failure_turn")
    trace = context.get("decision_trace")
    if type(failure_turn) is not int or failure_turn < 1 or not isinstance(trace, list):
        raise ValueError(
            "reflection requires a positive failure_turn and decision_trace"
        )
    turns = {
        entry["turn"]
        for entry in trace
        if isinstance(entry, dict)
        and type(entry.get("turn")) is int
        and entry["turn"] >= 1
    }
    if failure_turn not in turns:
        raise ValueError("failure_turn must occur in the supplied decision_trace")
    attribution = context.get("failure_attribution")
    verified = context.get("decision_error_verified")
    if (
        attribution not in {"DECISION_ERROR", "EXECUTION_FAILURE", "UNDETERMINED"}
        or type(verified) is not bool
        or verified != (attribution == "DECISION_ERROR")
    ):
        raise ValueError("reflection requires consistent runtime decision attribution")
    return failure_turn, turns, verified


class StructuredLLMClient:
    """Structured decisions and experience reflection over Qwen-compatible HTTP.

    Pydantic validates each response. json_object supports the wider Qwen family;
    json_schema is opt-in per provider capability.
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

    async def summarize_experience(self, context) -> ExperienceSummary:
        """Reflect on past decisions while preserving runtime attribution."""
        failure_turn, turns, decision_error = _reflection_inputs(context)
        system = (Path(__file__).parent / "prompts/experience_summary.md").read_text(
            encoding="utf-8"
        )
        summary = await self.structured(
            ExperienceSummary, system, json.dumps(context, ensure_ascii=False)
        )
        if (
            failure_turn not in summary.source_turns
            or not set(summary.source_turns) <= turns
        ):
            raise LLMError(
                "reflection must cite its failure turn and only supplied turns"
            )
        if (summary.decision_issue is not None) != decision_error:
            raise LLMError("reflection decision_issue contradicts runtime attribution")
        return summary


class ScriptedDecisionClient:
    """A transparent deterministic policy for software tests. This is not an LLM.

    The same fallback rules are used in both experimental arms. Memory may suggest
    a recovery tool but is never converted into physical state or a saved pose.
    """

    is_real_llm = False

    def __init__(self):
        self.contexts = []

    async def summarize_experience(self, context) -> ExperienceSummary:
        """Demonstrate planning constraints with a labelled non-model template."""
        failure_turn, _turns, decision_error = _reflection_inputs(context)
        skill_labels = {
            "navigate_to": "导航",
            "locate_object": "目标定位",
            "grasp_object": "抓取",
            "observe_robot_state": "状态观察",
        }
        skill = context.get("executed_skill")
        skill_label = (
            skill_labels.get(skill, "高层技能")
            if isinstance(skill, str)
            else "高层技能"
        )
        failure = context.get("failure_type")
        if not isinstance(failure, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]{0,63}", failure
        ):
            failure = "未分类异常"
        frame = next(
            entry
            for entry in context["decision_trace"]
            if isinstance(entry, dict) and entry.get("turn") == failure_turn
        )
        before = frame.get("before", {})
        if not isinstance(before, dict):
            before = {}
        if before.get("uncertain_action") is not None or failure == "ACTION_UNRESOLVED":
            issue = "先前物理动作尚待核实时，仍安排了新的物理动作。"
            constraint = "先前动作结果未核清时，下一步先观察当前状态；核清前不安排新的导航或抓取。"
        elif skill == "grasp_object" and before.get("grasp_state") in {
            "HELD",
            "UNKNOWN",
        }:
            issue = "抓取决策遗漏了当前持物状态检查。"
            constraint = "持物状态未知时先观察；已持物时不重复抓取，未持物且其余条件满足时才评估抓取。"
        elif failure == "POSE_STALE" or (
            skill == "grasp_object"
            and (
                before.get("pose_available") is False
                or before.get("pose_reference_matches_current") is False
            )
        ):
            issue = "抓取决策遗漏了当前有效位姿及引用匹配检查。"
            constraint = (
                "抓取前确认当前位姿有效且引用匹配；条件不满足时先重新定位，再评估抓取。"
            )
        elif failure == "INVALID_ARGUMENT":
            issue = "工具选择或参数未满足本任务允许的调用条件。"
            constraint = (
                "选择工具前核对允许的工具与任务目标参数；不能原样重复被拒绝的调用。"
            )
        elif skill == "navigate_to":
            issue = "导航决策遗漏了运行时已核实的前置条件。"
            constraint = "导航未验证到达时，不进入后续定位或抓取；先检查当前导航状态，再按预算重试或求助。"
        elif skill == "locate_object":
            issue = "定位决策遗漏了运行时已核实的前置条件或动作顺序。"
            constraint = "定位未产生当前可用位姿时，不直接进入抓取；先补充观测，再决定重新定位或求助。"
        else:
            issue = "本回合规划遗漏了运行时已核实的技能前置条件或动作顺序。"
            constraint = "选择下一技能前检查当前状态与该技能前置条件；条件不清时先观察，不直接重复失败动作。"
        lesson = (
            "把本回合遗漏的条件检查放到技能选择之前，并利用失败反馈决定下一步，避免无条件重复。"
            if decision_error
            else "把本次执行反馈转为后续检查与重试约束，不据此追认原决策有错。"
        )
        return ExperienceSummary(
            format_version=2,
            applicability=f"确定性演示模板（非LLM）：同类任务的{skill_label}遇到{failure}时。",
            decision_issue=issue if decision_error else None,
            planning_constraints=[
                constraint,
                "相同失败重复出现且当前反馈未改善时，停止盲目重试，按预算请求帮助。",
            ],
            lesson=lesson,
            precautions=[
                "先核对适用条件与当前工作记忆，工具结果是否成立由Verifier判断。",
                "历史位姿ID不能复用，只使用当前观测支持的位姿引用。",
            ],
            source_turns=[failure_turn],
        )

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
