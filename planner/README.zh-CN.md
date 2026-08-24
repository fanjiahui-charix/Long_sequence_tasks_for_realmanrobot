# 闭环 Planner 与 Agent Runtime

[English](./README.md) | [简体中文](./README.zh-CN.md)

`planner/` 现在只有一套执行架构：`AgentRuntime`。技能返回成功不代表步骤完成；
系统必须重新观察世界、验证 Skill Contract 的后置条件，验证通过后才能提交状态。

## 执行闭环

```text
Qwen Mission Plan（只表达意图）
        |
Schema + Contract 语义 dry-run
        |
PRECHECK -> EXECUTE -> OBSERVE/VERIFY -> COMMIT
                    |        失败
                    v
          确定性恢复 -> 有限安全重试
                    |
          基于已验证状态修复剩余后缀
                    |
                ABORT/HUMAN
```

timeout、重试次数、verifier、恢复和安全规则全部由代码中的 Skill Contract 管理，
不允许 Qwen 自行定义。

## 主要模块

- `agent_runtime/models.py`：计划、执行、验证、失败和任务结果类型。
- `agent_runtime/state.py`：带时间戳的物体状态和唯一事实源 `WorldState`。
- `agent_runtime/contracts.py`：前置条件、效果、超时、重试模式和 verifier。
- `agent_runtime/semantic_validator.py`：执行前符号化 dry-run。
- `agent_runtime/executor.py`：有界技能调用和异常归一化。
- `agent_runtime/verifiers.py`：导航、感知、抓取、放置和最终目标验证。
- `agent_runtime/recovery.py`：确定性恢复、预算和重复失败检测。
- `agent_runtime/replanner.py`：只修复未提交计划后缀。
- `agent_runtime/trace.py`：逐事件 flush 的 JSONL trajectory。
- `agent_runtime/runtime.py`：显式闭环状态机。
- `skills/`：Mock、TCP、ROS、FoundationPose 和操作适配器。

旧 `TaskExecutor` 路径已经删除。

## Mock 验收

以下命令不需要网络、ROS、相机、底盘或机械臂：

```powershell
python -m pytest planner/tests -q
python -m compileall -q planner
```

测试覆盖到达验证、缺失/过期位姿、物理结果 UNKNOWN、Verified Commit、确定性
恢复、后缀修复、防死循环预算、最终目标复验、JSON 协议、轨迹记录，以及完整的
故障注入 episode。

## 运行任务

全 Mock：

```bash
python3 planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "去 pointb 抓取眼镜盒，然后回到 pointa" \
  --nav-backend mock \
  --perception-backend mock \
  --manipulation-backend mock \
  --trajectory runtime/trajectories/mock-mission.jsonl
```

后续实体联调入口：

```bash
python3 planner/examples/run_long_task.py \
  --camera-name camera_middle \
  --task "去 pointb 抓取眼镜盒" \
  --nav-backend tcp \
  --perception-backend foundationpose \
  --manipulation-backend ros \
  --pick-mode pose_grasp
```

任务硬预算：

- `--mission-timeout`：任务时限，默认 900 秒。
- `--max-total-actions`：最大物理/恢复动作数，默认 50。
- `--max-replans`：最大后缀修复次数，默认 3。
- `--failure-repeat-threshold`：同状态同失败升级阈值，默认 3。
- `--trajectory`：指定 JSONL 轨迹文件。

没有 Qwen API key 时，确定性局部恢复仍可运行；需要 LLM 修复后缀时会明确终止。

## 状态与安全约束

- `SkillResult` 只表示执行器对命令执行情况的判断。
- `VerificationResult` 表示真实观察是否满足后置条件。
- 只有 verifier 通过后才能修改 `WorldState`。
- 物体位姿包含 frame、timestamp、source、valid 和可空 confidence。
- 有物理副作用的 `UNKNOWN` 禁止盲目重试。
- Replan 不得修改或重复已提交步骤。
- 所有步骤完成后仍要重新观察并验证最终目标。

## 轨迹与回退

JSONL 事件记录 mission、计划版本、步骤、attempt、执行结果、验证证据、恢复决策、
状态快照和稳定哈希。每条事件立即落盘，中断后仍可解析。默认目录为
`runtime/trajectories/`。

本轮以完整 Mock 故障注入闭环为验收标准。TCP 导航已有真实状态观察；ROS 导航
状态、真实抓取和放置证据将在实体联调时接入。证据不足时当前实现会返回未知或失败，
不会伪造成功。

阶段提交、回退命令和实体联调清单见
[agent-runtime-rollout.md](./docs/agent-runtime-rollout.md)。
