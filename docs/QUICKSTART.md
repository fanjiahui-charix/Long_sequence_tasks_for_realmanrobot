# 运行与复现

## 环境安装

Agent 使用 Python 3.10+。ROS Noetic、视觉模型环境与 Agent 分别安装，由适配层调用各自解释器。

```bash
python -m venv .venv
```

激活环境：Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1`，Linux 使用 `source .venv/bin/activate`。然后在仓库根目录安装：

```bash
python -m pip install -e .
```

## 软件闭环与故障注入基准

默认模式采用 Mock Backend，提供可复现的状态反馈和故障序列，适合检查任务流程、恢复策略与 Memory 数据流。脚本化决策可离线运行，LLM 调用数为 0。

```bash
# 完整 A→B→A 任务
python -m robot_agent demo --memory

# 注入一次位姿失效，检查重新定位后的抓取与返航
python -m robot_agent demo --memory --fault POSE_STALE --output-dir runtime/memory-demo
```

输出目录包含 `mission_report.json`、JSONL 轨迹与 `episodes.sqlite3`。再次使用同一输出目录运行，会读取其中已有的经验库。

## 接入 Qwen API

将 [.env.example](../.env.example) 复制为 `.env`，填写 DashScope API Key 和账户可用的模型：

```dotenv
DASHSCOPE_API_KEY=your_api_key
QWEN_MODEL=qwen3-vl-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

场景图理解需要支持图像输入的模型。以下命令使用带 A、B、桌子和目标标注的场景图进行任务理解，并通过 Mock Backend 执行技能闭环：

```bash
python -m robot_agent demo --llm qwen --image examples/scene_ab.png --memory --fault POSE_STALE --output-dir runtime/qwen-memory-demo
```

`--instruction` 设置自然语言指令，`--image` 指定场景图；`--mission-file` 可读取已有的 `MissionSpec`，直接进入 ReAct 执行。当前任务场景为 A→B 取回黑色眼镜盒并返回，导航标签与实际点位的对应关系由部署配置提供。

模型请求指标包含实际发出的场景理解、逐轮决策与经验总结调用；原始响应经结构化校验后进入任务执行。

## 决策反思与跨任务经验复用

复盘基准使用固定的前置条件缺失场景：历史策略在没有有效位姿时重复提出抓取，系统保存这些决策及其反馈。模型随后提炼规划约束，新的任务再从 SQLite 读取经验并参与技能选择。

```bash
# 离线基准：脚本化总结与决策
python examples/reflection_demo.py --output-dir runtime/reflection-demo

# Qwen 生成经验总结，并决定后续任务的动作
python examples/reflection_demo.py --llm qwen --output-dir runtime/reflection-qwen
```

已保存的 [完整示例](../examples/memory_demo.json) 使用 `qwen-plus` 进行反思与后续决策，可通过环境变量 `QWEN_MODEL=qwen-plus` 选择该模型。基准为历史错误提案提供固定输入，便于复现经验形成、持久化与注入过程。

每次运行在输出目录生成独立的 SQLite 文件和轨迹。`summary.json` 汇总历史案例、经验条目、实际注入的条目 ID、后续决策及最终结果；`reflection-input.json` 与 `decision-input.json` 可查看模型在两阶段收到的上下文。

经验结构包括：

| 字段 | 内容 |
| --- | --- |
| `applicability` | 可借鉴经验的任务与状态条件 |
| `decision_issue` | 历史决策中有运行时记录支持的问题 |
| `planning_constraints` | 后续规划需要检查的条件或顺序 |
| `lesson` / `precautions` | 可复用经验及注意事项 |
| `source_turns` | 支持总结的历史决策轮次 |

存储、检索与归因规则见 [系统设计](SYSTEM_DESIGN.md)。

## A/B 对照与指标

A 组使用 ReAct + Working Memory，B 组增加持久化 Episodic Memory。两组使用相同决策策略、技能和有序故障场景：

```bash
python -m robot_agent evaluate --repetitions 3 --output-dir runtime/evaluation
```

默认运行正常任务、导航超时、目标未检出、位姿失效、抓取未持物、动作结果待核清、返航掉物、重复失败、反馈缺失与运动未稳定等场景。`--scenarios` 可选择子集，例如：

```bash
python -m robot_agent evaluate --scenarios normal,pose_stale,repeated_failure --repetitions 3 --output-dir runtime/evaluation-subset
```

`metrics.json` 记录任务完成率、恢复成功率、误完成率、重复失败率、模型调用与延迟、总执行时间；`missions.jsonl` 保存逐任务数据。默认模式为脚本化策略，使用 `--llm qwen` 可进行模型 API 对照，模型由 `--model` 或环境配置选择。

这些测试均标记为 Mock/API-level Evaluation，用于软件闭环与策略对照。硬件联调使用独立的平台配置与设备日志，流程见 [部署指南](HARDWARE_VALIDATION.md)。

## 硬件接入

`RobotBackend` 将导航、视觉、抓取和状态读取连接到具体平台。先填写平台配置，再执行离线预检：

```bash
python -m robot_agent preflight --hardware-config config/hardware.example.yaml
```

示例模板会列出待配置项。部署自己的设备时，使用已填写的 YAML，并按 [真机部署与预检指南](HARDWARE_VALIDATION.md) 完成状态读取、单技能联调和完整任务测试。字段与方法说明见 [机器人接口](BACKEND_API.md)。
