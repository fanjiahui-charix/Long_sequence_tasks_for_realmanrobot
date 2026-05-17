from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .prompt_builder import DEFAULT_SYSTEM_PROMPT, build_user_prompt, load_yaml
from .schema import validate_plan


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def image_to_data_url(image_path: str | Path) -> str:
    path = Path(image_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    with path.open("rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def extract_json_object(text: str) -> dict:
    content = text.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return json.loads(content)


class QwenPlannerClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        timeout_sec: float = 60.0,
    ) -> None:
        load_local_env()
        self.model = model or os.getenv("QWEN_MODEL", "qwen-vl-plus")
        self.temperature = temperature
        self.last_response_meta: dict = {}
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = (base_url or os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout_sec = timeout_sec

    def _post_chat_completion(self, messages: list[dict]) -> dict:
        if not self.api_key:
            raise ValueError("missing DASHSCOPE_API_KEY")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                response_text = response.read().decode("utf-8")
                return json.loads(response_text)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"planner HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"planner network error: {exc.reason}") from exc

    def plan_from_image(
        self,
        image_path: str | Path,
        user_task: str,
        skills_path: str | Path,
        scene_path: str | Path | None = None,
    ) -> dict:
        skills_config = load_yaml(skills_path)
        scene_config = load_yaml(scene_path) if scene_path else {}
        user_prompt = build_user_prompt(user_task, skills_config, scene_config)

        completion = self._post_chat_completion(
            messages=[
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_to_data_url(image_path)},
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ]
        )

        self.last_response_meta = {
            "request_model": self.model,
            "response_model": completion.get("model"),
            "response_id": completion.get("id"),
            "usage": completion.get("usage"),
            "base_url": self.base_url,
        }

        text = completion["choices"][0]["message"]["content"]
        plan = extract_json_object(text)
        errors = validate_plan(plan)
        if errors:
            raise ValueError(f"invalid plan: {errors}\nraw output:\n{text}")
        return plan
