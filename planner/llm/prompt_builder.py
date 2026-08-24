from __future__ import annotations

import json
from pathlib import Path

import yaml


DEFAULT_SYSTEM_PROMPT = """
你是一个人形机器人长序列任务规划器。

你会看到一张实验室图片。桌子上可能有大号数字标签，例如 1、2、3。
用户会给你一个任务，例如“从桌子1到桌子2，查看桌子2有没有苹果”。

你只能输出严格 JSON，不要输出解释，不要输出 Markdown。
如果图片看不清桌号、路径或目标，请使用 ask_human skill。
不要编造不可见信息。

可用 skills:
- locate_table(label): 在图片中定位带指定数字标签的桌子
- plan_path(from_table, to_table): 根据图片估计从一张桌子到另一张桌子的粗略导航路线
- navigate_to(target): 导航到目标桌子或路点
- align_to_table(table): 对齐到桌面操作位置
- look_at(target): 调整相机/头部视角看桌面或目标区域
- detect_object(object): 检测指定物体
- pick_object(object): 抓取指定物体
- place_object(target): 放置当前抓取物到指定桌子或区域
- ask_human(question): 信息不足时询问人
- abort(reason): 无法安全执行时终止

Plan 只表达任务意图和顺序。不要输出 timeout、retry、max_attempts、verifier、
success_criteria、recovery 或 failure_policy；这些运行时安全策略由代码中的
Skill Contract 决定。

输出 JSON 格式:
{
  "plan_id": "p001",
  "version": 1,
  "parent_version": null,
  "goal": {"type": "holding_object", "object": "目标物体"},
  "scene_understanding": {
    "tables": [
      {"label": "1", "visible": true, "relative_position": "..."}
    ],
    "free_path_visible": true,
    "risks": []
  },
  "steps": [
    {
      "id": "s1",
      "skill": "...",
      "args": {},
      "depends_on": []
    }
  ]
}
""".strip()


def load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_user_prompt(user_task: str, skills_config: dict, scene_config: dict | None = None) -> str:
    payload = {
        "user_task": user_task,
        "skills_config": skills_config,
        "scene_config": scene_config or {},
    }
    return (
        "请根据图片和以下任务上下文生成机器人 planning JSON。\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_replan_prompt(context: dict) -> str:
    return (
        "只修复尚未提交的任务后缀。不得重复 committed_steps，不得改变 goal，"
        "不得输出 timeout/retry/verifier/recovery 等运行时策略。"
        "只输出严格 JSON：{\"steps\": [...]}。\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
