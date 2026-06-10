# Long Sequence Tasks 中文说明

这个仓库是机器人长序列移动操作任务的统一工作区，按能力模块组织，而不是按底层实现方式组织。

- `navigation/`：底盘运动、AGV 控制、导航接口
- `planner/`：文本到计划、计划校验、长序列任务执行
- `vision_grasp/`：相机采集、FoundationPose 6D 位姿估计、抓取执行

当前仓库已经整理成适合后续开源的结构。`FoundationPose` 作为内部模块放在
`vision_grasp/foundationpose/`，机器人相关的集成层放在它旁边。

英文版说明见：`README.md`

## 总体架构

完整 demo 链路是：

1. 先用分层 bringup 启动 ROS 和硬件依赖。
2. 用 `planner/` 把自然语言任务转成长序列结构化计划。
3. 用 `navigation/` 控制底盘移动到目标点位或目标桌面。
4. 用 `vision_grasp/` 采当前画面、生成或传入 mask、运行 FoundationPose、把相机坐标系下的位姿转换到机械臂基座坐标系，并执行抓取。

三个主模块可以分开调试：

- `navigation/` 可以单独联调，不依赖视觉或抓取。
- `planner/` 可以走 mock 后端，先验证任务规划逻辑。
- `vision_grasp/` 可以只做感知，也可以做感知加真实抓取。

## 仓库结构

```text
Long_sequence_tasks/
  navigation/          底盘与导航代码
  planner/             LLM 规划与执行层
  vision_grasp/        视觉抓取主模块
  scripts/             一键 bringup、停止、系统检查脚本
  .env.example         环境变量模板
  README.md            英文总说明
  README.zh-CN.md      中文总说明
```

分模块说明：

- `/home/rm/Long_sequence_tasks/navigation/README.zh-CN.md`
- `/home/rm/Long_sequence_tasks/planner/README.zh-CN.md`
- `/home/rm/Long_sequence_tasks/vision_grasp/README.zh-CN.md`

## 运行环境

这个项目主要用两套 Python 环境：

- ROS / 硬件控制：
  `/usr/bin/python3`
  同时需要 `source /opt/ros/noetic/setup.bash`
- FoundationPose 推理：
  `conda activate foundationpose`

相机采集、TF 查询、机械臂与夹爪控制会自动走 ROS 的系统 Python。FoundationPose 推理脚本会自动切到 `foundationpose` conda 环境。

## 一键 Bringup

最常用的是最小启动模式：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
```

`--mode minimal` 会启动：

- `roscore`
- 底盘驱动
- 头顶相机
- 6 自由度机械臂驱动
- 末端执行器驱动
- 必要 TF 发布

如果你还需要更完整的任务态节点，可以用：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode full
```

停止 bringup 拉起的进程：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_stop.sh
```

检查当前 ROS 节点、话题和关键 TF：

```bash
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

## Demo 用法

### 1. 只跑导航

```bash
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py markers
python3 /home/rm/Long_sequence_tasks/navigation/run_navigation.py target --name table_2
```

作用：

- `markers`：打印当前可用标记点
- `target --name table_2`：让底盘移动到命名目标点

### 2. 只跑规划

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and check whether there is an apple" \
  --nav-backend mock \
  --manipulation-backend mock
```

作用：

- 调用规划模型生成长序列计划
- 用 mock 后端做安全干跑
- 不会真实驱动底盘和机械臂

### 3. 只做视觉位姿估计

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/foundationpose/demo_data/mustard0/mesh/textured_simple.obj \
  --object-label mustard \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  --mask
```

作用：

- 采一帧当前 RGB-D 图像
- 自动基于深度生成 mask
- 运行 FoundationPose
- 输出 `foundationpose_pose.json` 和 `pipeline_result.json`
- 默认不会动机械臂，除非加 `--execute-grasp`

### 4. 感知后真实抓取

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/foundationpose/demo_data/mustard0/mesh/textured_simple.obj \
  --object-label mustard \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml \
  --mask \
  --execute-grasp
```

作用：

- 先跑视觉定位
- 再把位姿交给抓取模块
- 执行 `home -> pregrasp -> grasp -> close -> retreat`

## 关键配置

- `/home/rm/Long_sequence_tasks/.env.example`
  全局环境变量模板
- `/home/rm/Long_sequence_tasks/planner/configs/*.yaml`
  规划提示词、技能配置、导航点位、场景模板
- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`
  抓取配置，包括坐标系、末端参数、退让偏移、抓取姿态参数

## 常见问题

### `tf2.LookupException: "base_left" passed to lookupTransform argument target_frame does not exist`

含义：

- 机械臂驱动或 TF 发布没有起来
- bringup 没有完整启动
- 配置里的基座坐标系和当前机器人实际 TF 不一致

建议先检查：

```bash
bash /home/rm/Long_sequence_tasks/scripts/check_system.sh
```

### `ModuleNotFoundError: No module named 'rospy'`

含义：

- 一个依赖 ROS 的脚本被错误地放在了 conda 环境里直接运行
- 没有走 ROS 的系统 Python

建议：

- 优先使用新的 pipeline 脚本和 bringup 脚本
- 它们会自动把 ROS 子进程切到 `/usr/bin/python3`

## 开源与提交注意事项

为了方便 GitHub 开源，运行产物和大体积模型权重不要提交到 Git：

- `vision_grasp/runtime/`
- `vision_grasp/foundationpose/weights/`
- `.run/`
