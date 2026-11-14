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
  "last_error": "POSE_STALE"
}</pre>
</td>
<td valign="top">
<p>将执行轨迹凝练为原因假设、经验和注意事项，存入 SQLite 供后续检索。以下为精简结构示例。</p>
<pre lang="json">{
  "trigger": "POSE_STALE",
  "cause_status": "UNKNOWN",
  "cause_hypothesis": "具体原因尚未确认",
  "lesson": "重新定位后再抓取",
  "precautions": ["不复用失效位姿"]
}</pre>
</td>
</tr>
</table>

恢复成功或任务结束后进行经验总结。恢复结果由 Verifier 确认，原因分析保留为假设；历史经验与当前状态共同参与下一步决策。任务完成需同时通过返航位置与持物状态验证。

[运行演示](docs/QUICKSTART.md) · [系统架构](docs/SYSTEM_DESIGN.md) · [完整 JSON 示例](examples/memory_demo.json) · [硬件接入](docs/HARDWARE_VALIDATION.md)

新增 Agent 贡献采用 [MIT](LICENSE-AGENT)，第三方代码与媒体授权见 [NOTICE](NOTICE.md)。
