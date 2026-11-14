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

`POSE_STALE` 注入一次位姿失效。Agent 重新定位后继续抓取与返航，Verifier 检查是否返回 A 且仍持有目标；经验总结步骤从该过程提取失败原因假设、经验与注意事项。

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

再次执行同一命令，将复用同一路径中的 SQLite 经验库。新任务可检索前一次任务已凝练、恢复结果已验证的经验。模型在每轮决策中获得当前 Working Memory 与相关经验；经验总结也使用同一模型接口，不新增 Memory Agent。

结果中保留模型请求与经验总结的指标；模型请求数包含实际执行的决策、场景理解和经验总结调用。模型返回内容由 Pydantic 校验。总结失败时保留原始执行记录，未完成总结的条目不作为已凝练经验注入。

可使用 `--instruction` 提供指令、`--image` 替换示意图，或用 `--mission-file` 读取预验证的任务。当前示例限定 A→B 取回黑色眼镜盒并返回。实际导航 marker 映射由部署配置提供，图片不会直接产生底盘坐标。

`.env` 不进入版本控制，不要将 API Key 填入示例文件或日志。

## 经验与验证的边界

Working Memory 保存当前位置、物体/位姿、持物状态、动作、观察和错误。Episodic Memory 保存执行记录，并增加结构化经验：触发条件、失败原因假设、可复用经验和注意事项。检索以任务、类别、Skill 和失败类型过滤。

只有恢复经过独立验证且经验总结已完成的条目，才进入后续决策上下文。恢复成功不代表原因假设被证实，`cause_status` 只能是 `UNKNOWN` 或 `HYPOTHESIS`；UNKNOWN 的原因文本由程序统一保留为“原因尚未确认”，防止模型在未知状态下夹带物理因果猜测。当前观察与工具前置条件始终优先，历史经验不能写入机器人位置或覆盖物理反馈。

本仓库提供的软件与 API 级演示使用 Mock Backend；平台 GIF/MP4 为已有演示录像，不单独证明新 Agent 的完整硬件闭环。

## 硬件接入

`RobotBackend` 提供通用接口；RealMan 适配复用导航、RGB-D、YOLO-seg、FoundationPose、坐标变换和抓取模块。四个高层工具分别为 `navigate_to`、`locate_object`、`grasp_object`、`observe_robot_state`。

先填写实际位置、状态读取、停止接口、视觉资源及实际夹爪宽度标定，再运行离线检查：

```bash
python -m robot_agent preflight --hardware-config config/hardware.example.yaml
```

示例配置保留待填写项，检查会列出缺失信息。真实动作要求 `--backend realman --enable-hardware` 与经过确认的硬件配置；不能直接使用空模板启用。

完整接入与部署前检查见 [HARDWARE_VALIDATION](HARDWARE_VALIDATION.md)，通用接口见 [BACKEND_API](BACKEND_API.md)，实现机制见 [SYSTEM_DESIGN](SYSTEM_DESIGN.md)。
