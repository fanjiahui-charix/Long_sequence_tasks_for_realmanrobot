# 运行与复现

## 安装

Agent 使用独立的 Python 3.10+ 环境。ROS Noetic、FoundationPose Conda 与 Agent 环境各自保留，不合并或升级现有机器人依赖。

在仓库根目录执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux：

```bash
source .venv/bin/activate
```

安装 Agent：

```bash
python -m pip install -e .
```

## 无硬件演示

```bash
python -m robot_agent demo --memory
python -m robot_agent demo --memory --fault POSE_STALE --output-dir runtime/memory-demo
```

默认使用 Mock Backend 和脚本化决策，无需 API Key。脚本化决策及其经验摘要用于离线演示，LLM 调用数记为 0。

`POSE_STALE` 注入一次位姿失效。Agent 重新定位后继续抓取与返航，Verifier 检查是否返回 A 且仍持有目标；该场景用于演示工具反馈后的恢复。工具返回失败不自动证明 Agent 的决策存在错误。

输出位于 `runtime/`：任务结果 `mission_report.json`、JSONL 轨迹与 `episodes.sqlite3`。运行时文件已被 Git 忽略。

## Qwen API 与经验总结

将仓库中的 `.env.example` 复制为 `.env`，填写自己的 DashScope API Key 和账户可用的视觉模型：

```dotenv
DASHSCOPE_API_KEY=your_api_key
QWEN_MODEL=qwen3-vl-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

从带 A、B、桌子和眼镜盒标注的示意图理解任务，并运行完整流程：

```bash
python -m robot_agent demo --llm qwen --image examples/scene_ab.png --memory --fault POSE_STALE --output-dir runtime/qwen-memory-demo
```

再次执行同一命令，将复用同一路径中的 SQLite 经验库。新任务可检索前一次任务已凝练且有验证证据的经验。模型在每轮决策中获得当前 Working Memory 与相关经验；经验总结也使用同一模型接口，不新增 Memory Agent。

结果中保留模型请求与经验总结的指标；模型请求数包含实际执行的决策、场景理解和经验总结调用。模型返回内容由 Pydantic 校验。总结失败时保留原始执行记录，未完成总结的条目不作为已凝练经验注入。

可使用 `--instruction` 提供指令、`--image` 替换示意图，或用 `--mission-file` 读取预验证的任务。当前示例限定 A→B 取回黑色眼镜盒并返回。实际导航 marker 映射由部署配置提供，图片不会直接产生底盘坐标。

`.env` 不进入版本控制，不要将 API Key 填入示例文件或日志。

## 历史决策复盘

Working Memory 保存当前位置、物体/位姿、持物状态、动作、观察和错误，维护当前任务事实。Episodic Memory 根据历史“决策 + 当时状态 + 失败反馈 + 后续过程”提取可复用的规划经验：

- applicability：什么情境下适用。
- decision_issue：历史决策中经证据支持的问题。
- planning_constraints：以后规划需要满足的条件或检查。
- lesson / precautions：可复用经验与注意事项。
- source_turns：支持这条经验的历史轮次。

只有运行时证据支持 DECISION_ERROR，才能把历史失败归因为决策错误。工具报错、传感器缺反馈或执行未达目标，本身不等同于规划失误。经验总结也不用于猜测物理故障根因。

存入 SQLite 后，经验需为 READY，且满足“恢复经过独立验证”或“decision_error_verified 已由运行时证据确认”之一，才进入后续 ReAct 上下文。因此，有确证的规划前置条件错误即使没有恢复，也可以形成条件性经验。当前观察与工具前置条件始终优先，历史经验不能覆写 Working Memory 中的实时事实。

### 受控示例

离线运行：

```bash
python examples/reflection_demo.py --output-dir runtime/reflection-demo
```

使用前文配置的 Qwen API 生成反思与后续决策：

```bash
python examples/reflection_demo.py --llm qwen --output-dir runtime/reflection-qwen
```

已保存的完整示例使用 `qwen-plus` 生成反思与后续决策，可通过环境变量 `QWEN_MODEL=qwen-plus` 复现该模型选择；默认使用 `.env` 中的配置。模型生成的经验是条件性建议，当前工具前置条件、重试预算和 Verifier 始终优先。

该示例按四步展示经验形成与复用：

1. **历史失败**：在尚未取得当前有效位姿、前置条件没有改善的情况下，受控历史 Agent 反复提出抓取。运行时拒绝提案，保留决策、当时 Working Memory、失败反馈与后续过程。
2. **决策复盘**：将完整历史提供给总结步骤，识别有证据支持的规划问题，形成“先取得有效位姿”“前置条件未改善时不机械重试”等条件性约束和注意事项。Qwen 模式由真实模型生成该反思。
3. **长期保存**：结构化经验与来源轮次写入 SQLite，经运行时确认的决策错误可成为后续检索条目。
4. **后续任务**：新任务检索并注入历史经验，再生成下一步决策。输出的 `prior_ep_id` 对应被复用的历史条目，`next_decision` 展示注入之后的实际动作选择。

历史中的错误提案是为复盘而受控设置的，不声称 Qwen 自发犯了这些错误。默认模式采用脚本化总结与决策、可离线运行；`--llm qwen` 使用真实模型进行反思与后续决策。演示关注经验生成、持久化、回读和注入的链路，不推断物理故障原因。

本仓库的软件与 API 级演示使用 Mock Backend；平台 GIF/MP4 为已有演示录像，不单独证明新 Agent 的完整硬件闭环。

## 硬件接入

`RobotBackend` 提供通用接口；RealMan 适配复用导航、RGB-D、YOLO-seg、FoundationPose、坐标变换和抓取模块。四个高层工具分别为 `navigate_to`、`locate_object`、`grasp_object`、`observe_robot_state`。

先填写实际位置、状态读取、停止接口、视觉资源及实际夹爪宽度标定，再运行离线检查：

```bash
python -m robot_agent preflight --hardware-config config/hardware.example.yaml
```

示例配置保留待填写项，检查会列出缺失信息。真实动作要求 `--backend realman --enable-hardware` 与经过确认的硬件配置；不能直接使用空模板启用。

完整接入与部署前检查见 [HARDWARE_VALIDATION](HARDWARE_VALIDATION.md)，通用接口见 [BACKEND_API](BACKEND_API.md)，实现机制见 [SYSTEM_DESIGN](SYSTEM_DESIGN.md)。
