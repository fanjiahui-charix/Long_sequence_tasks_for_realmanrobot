# 实验结果：Mock/API-level Evaluation

日期：2026-11-13（Asia/Shanghai）。所有机器人状态、位姿、夹爪宽度与故障均为合成 Mock/API-level 数据。真实 Qwen API 调用不等于真实机器人验证。

## 软件验证

最终自动化测试：51 passed；独立复核同样通过。Ruff 格式与 F 类静态检查通过，Git Diff whitespace check 通过。独立环境：Windows / Python 3.13.9 / Pydantic 2.14.3 / PyYAML 6.0.3 / pytest 9.2.0。旧环境 Pydantic 2.12.2 的核心测试也已运行；最终验收使用独立 .venv。

Wheel 构建、独立安装以及在源码目录外使用 -I 启动完整 Mock Demo 均通过。ROS、FoundationPose CUDA 推理与真实机械动作未在此 Windows 软件环境验证。GitHub CI 配置覆盖 Ubuntu/Windows 与 Python 3.10/3.12；发布后的最新结果见 [Agent software tests](https://github.com/fanjiahui-charix/Long_sequence_tasks_for_realmanrobot/actions/workflows/tests.yml)。这里保存的是本地软件/API-level 验收记录。

## Experiment A / B：脚本化完整故障集

两组使用相同的确定性策略、Tools、Verifier、10 个故障场景及相同顺序，每个场景重复 3 次。A 只用 Working Memory；B 使用独立 SQLite，跨 Mission 保存并检索经过验证的恢复经验。脚本化决策不是 LLM，因此模型调用数为 0。

| Metric | A: Working Memory | B: + Episodic Memory |
|---|---:|---:|
| Missions | 30 | 30 |
| Completed | 21 | 21 |
| Task Completion Rate | 70.00% | 70.00% |
| Recovery Success Rate | 66.67% | 66.67% |
| False Completion Rate | 0.00% | 0.00% |
| Repeated Failure Rate | 22.22% | 22.22% |
| LLM Calls | 0 | 0 |
| Average LLM Latency | N/A (no LLM) | N/A (no LLM) |
| Average Total Execution Time | 0.0086 s | 0.0156 s |
| Retrieved episode injections | 0 | 387 |

场景为正常流程、导航超时、目标未找到、位姿过期、抓取空夹、抓取执行未知、返航掉物、持续失败、实际宽度缺失、动作持续未结束。每组 21/30 完成；其余 9 次是三个故意不可恢复场景的安全终止。该 70% 不代表机器人能力上限。全部可恢复场景在脚本策略下完成，误报完成为 0。

B 确实检索并注入历史经验；在该规则策略中没有观察到成功率或调用次数优势，不能据此宣称 Memory 提升了模型决策能力。

## Experiment A / B：真实 Qwen API + Mock 机器人

模型：qwen3-vl-plus，JSON Object 输出加客户端 Pydantic 校验。相同故障为 POSE_STALE 和 TOOL_EXECUTION_UNKNOWN，每组各 2 次重复（4 个 Mission）。两组逐任务执行，B 从空数据库开始，在后续任务中检索已验证恢复。

| Metric | A: Working Memory | B: + Episodic Memory |
|---|---:|---:|
| Missions | 4 | 4 |
| Completed | 4 | 4 |
| Task Completion Rate | 100.00% | 100.00% |
| Recovery Success Rate | 100.00% | 100.00% |
| False Completion Rate | 0.00% | 0.00% |
| Repeated Failure Rate | 0.00% | 0.00% |
| LLM Calls | 29 | 31 |
| Average LLM Latency | 3.076 s | 3.050 s |
| Average Total Execution Time | 22.3517 s | 23.7371 s |
| Retrieved episode injections | 0 | 48 |

此样本仅验证真实模型调用、结构化工具决策、恢复和 Memory 注入。样本量小且未随机化组次序；没有充分证据证明 Episodic Memory 带来稳定收益。延迟包含网络与服务波动，不是硬件控制环周期。

## 图片输入完整 Demo

输入为 examples/scene_ab.png 合成示意图和自然语言指令。真实 Qwen 完成 MissionSpec 解析及 ReAct 决策，注入一次 POSE_STALE 后恢复。

- 终态：COMPLETED；robot_at_A=true，object_held=true。
- LLM Calls：8（含场景理解）；决策调用：7。
- 失败：1；验证恢复：1。
- 场景理解：3.423 秒；从理解到任务完成总时间：24.914 秒。
- 持物证据源为 mock_actual_encoder，标定 origin=synthetic，不能作为真机持物证据。

## 指标口径与复现

Task Completion Rate=完成 Mission/全部 Mission。Recovery Success Rate=原后置条件已恢复的失败事件/全部失败事件。False Completion Rate=错误报告完成的 Mission/全部 Mission（与 Mock 后端独立 ground truth 对照）。Repeated Failure Rate=同一 Mission 内相同 Skill/Failure 首次之后的事件/全部失败事件。

LLM Calls 计数实际发出的请求；本地配置校验失败不计网络调用。Agent 总时间覆盖 ReAct、执行、观察与 Memory；图片 Demo 另计入场景理解。LLM latency 记录请求耗时，decision latency 另存。Tool 和 Memory retrieval time 保存在各 Mission 指标中。检索 precision/relevance 未做独立人工标注，不报告数值。

复现：

```bash
python -m pytest -q
python -m robot_agent demo --memory --fault POSE_STALE
python -m robot_agent evaluate --repetitions 3
python -m robot_agent demo --llm qwen --image examples/scene_ab.png --memory --fault POSE_STALE
python -m robot_agent evaluate --llm qwen --scenarios pose_stale,execution_unknown --repetitions 2
```

原始 JSONL/SQLite/XML 和汇总结果保存于 gitignored runtime/，单独作为验收记录交付，不加入开源源码包。核心代码/测试指纹 SHA256：bd4e7855b7c01e9608d70e8fb6396d96d66dffbbd9173284213dd262ebcd2efd。
