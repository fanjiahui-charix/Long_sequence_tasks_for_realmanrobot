# ReAct + Memory Robot Agent

面向长时序移动操作任务的具身 Agent 与记忆增强执行框架，基于 RealMan 移动操作平台。

**任务示例：A 出发 → B 定位眼镜盒 → 抓取 → 携物返回 A。**

![机器人平台演示](docs/media/project-demo.gif)

[原速视频](docs/media/project-demo.mp4) · 已有平台演示；Agent 验证采用 Qwen API + Mock Backend。

## Agent 闭环

以自然语言和场景图像为输入，ReAct 逐轮选择导航、目标定位、抓取和状态观察等高层 Skill，依据执行反馈调整后续行动。

`Observation → ReAct Decision → Tool Calling → Verification → Memory Update`

## 双层 Memory

<table>
<tr>
<th width="50%">Working Memory</th>
<th width="50%">Episodic Memory</th>
</tr>
<tr>
<td valign="top">
<p>维护当前任务事实，随观察更新并注入每轮决策。</p>
<pre lang="json">{
  "current_location": "B",
  "pose": null,
  "grasp_state": "NOT_HELD",
  "last_error": null
}</pre>
</td>
<td valign="top">
<p>复盘历史决策、当时状态、失败反馈及后续过程，形成条件性经验。以下为精简结构示例。</p>
<pre lang="json">{
  "applicability":
    "到达目标区域后，当前没有有效位姿",
  "decision_issue":
    "前置条件未改善时反复提出抓取",
  "planning_constraints": [
    "先取得本轮有效位姿，再安排抓取",
    "前置条件未改善时，不机械重试"
  ],
  "lesson":
    "利用反馈补齐条件，再决定下一步",
  "precautions": [
    "状态不明先观察，避免重复无效动作"
  ]
}</pre>
</td>
</tr>
</table>

经运行时证据确认的决策问题，可凝练为规划约束、检查项和注意事项，写入 SQLite 并注入后续 ReAct。Working Memory 保持实时事实；工具失败不自动等同规划错误。任务完成需同时通过返航位置与持物状态验证。

**复盘演示：受控重复抓取提案 → Qwen 反思 → 跨任务检索 → 先定位，再抓取返航。** [查看实际输入、经验与下一步决策](examples/memory_demo.json)。

[运行与复盘](docs/QUICKSTART.md) · [系统架构](docs/SYSTEM_DESIGN.md) · [完整 JSON 示例](examples/memory_demo.json) · [硬件接入](docs/HARDWARE_VALIDATION.md)

新增 Agent 贡献采用 [MIT](LICENSE-AGENT)，第三方代码与媒体授权见 [NOTICE](NOTICE.md)。
