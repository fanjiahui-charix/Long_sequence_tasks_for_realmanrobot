# Planner 中文说明

`planner/` 是长序列任务里的推理与执行层，负责把任务文本和场景上下文转成结构化计划，并把计划交给导航与操作技能执行。

英文版说明见：`README.md`

## 核心功能

这个模块主要解决：

- 文本到计划的生成
- 计划格式校验
- 基于技能的任务执行
- 在接真实硬件前先用 mock 做安全验证

## 代码结构

```text
planner/
  configs/         运行配置、场景模板、技能配置、后端配置
  examples/        示例脚本和主入口
  executor/        计划执行与校验
  llm/             Qwen 客户端、schema、prompt 构造
  skills/          导航、感知、操作、人机交互技能
  tests/           轻量测试
```

### 文件职责

- `examples/run_long_task.py`
  一条命令跑完整长任务的主示例
- `examples/run_qwen_planner_demo.py`
  输入图像和任务文本，生成计划
- `examples/run_executor_demo.py`
  从已有 plan JSON 执行
- `executor/task_executor.py`
  逐步执行生成后的任务计划
- `llm/qwen_client.py`
  规划模型客户端
- `llm/prompt_builder.py`
  负责拼装提示词
- `skills/navigation_skill.py`
  封装导航动作
- `skills/perception_skill.py`
  封装感知结果，包括 FoundationPose pose 文件读取
- `skills/manipulation_skill.py`
  封装抓取与手部动作

## 运行环境

- 规划本体：
  `python3`
- 使用 ROS 抓取时：
  先 source 对应 ROS 工作空间

## 常用命令

### 根据图像生成计划

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_qwen_planner_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to table 2 and check whether there is an apple"
```

作用：

- 调用 LLM 规划器
- 输出结构化长序列计划

### 执行已有计划

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_executor_demo.py \
  --plan /home/rm/Long_sequence_tasks/planner/examples/sample_plan.json
```

作用：

- 读取计划文件
- 调用执行器和技能层执行

### 完整 mock demo

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_full_mock_demo.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and inspect the table"
```

作用：

- 端到端干跑
- 不会真实驱动底盘和抓取硬件

### 一条命令跑长任务

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc and pick the mustard bottle" \
  --nav-backend tcp \
  --manipulation-backend ros \
  --pick-mode pose_grasp
```

作用：

- 先生成任务计划
- 用选定导航后端执行移动
- 用选定操作后端执行抓取

## 后端说明

### 导航后端

- `mock`
  不动真实底盘
- `tcp`
  直接控制底盘
- `ros`
  通过 ROS 话题路径控制

### 操作后端

- `mock`
  不动真实机械臂
- `ros`
  执行真实末端控制和 pose grasp

## 关键参数

### `run_long_task.py`

- `--image`
  场景图像路径
- `--camera-name`
  不用本地图像，而是从 ROS 相机直接采当前画面
- `--task`
  自然语言任务描述
- `--nav-backend`
  `mock`、`tcp` 或 `ros`
- `--manipulation-backend`
  `mock` 或 `ros`
- `--pick-mode`
  `as_planned`、`close_only`、`pick_demo`、`pose_grasp`
- `--verbose`
  打印更详细的规划和执行信息

## 配置文件

- `configs/lab_scene_template.yaml`
  场景模板
- `configs/nav_targets.yaml`
  命名导航目标
- `configs/skills.yaml`
  技能注册和技能元数据
- `configs/llm.yaml`
  规划模型设置

操作模块当前使用统一抓取配置：

- `/home/rm/Long_sequence_tasks/vision_grasp/configs/grasp_config.example.yaml`

如果要替换：

```bash
export LONG_TASKS_GRASP_CONFIG=/custom/path/grasp_config.yaml
```

## 推荐使用方式

### 完全干跑

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc" \
  --nav-backend mock \
  --manipulation-backend mock
```

### 真实底盘，假抓取

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --image /path/to/lab_scene.jpg \
  --task "go to pointc" \
  --nav-backend tcp \
  --manipulation-backend mock
```

### 真实底盘，真实抓取

先执行项目 bringup：

```bash
bash /home/rm/Long_sequence_tasks/scripts/bringup_long_tasks.sh --mode minimal
```

然后执行：

```bash
python3 /home/rm/Long_sequence_tasks/planner/examples/run_long_task.py \
  --camera-name camera_middle \
  --task "go to pointc and pick the mustard bottle" \
  --nav-backend tcp \
  --manipulation-backend ros \
  --pick-mode pose_grasp \
  --verbose
```
