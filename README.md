# Long Sequence Tasks

This folder is a prototype workspace for large-model-driven long-sequence robot tasks.

Current goal:

1. Send one lab image plus a user task to Qwen.
2. Generate a structured planning JSON.
3. Keep robot skills as a local whitelist.
4. Later connect the executor to ROS navigation, perception, grasping, and placement nodes.

## Layout

```text
Long sequence tasks/
  configs/                 Runtime configuration
  examples/                Local demos
  executor/                Plan execution and skill dispatch
  llm/                     Qwen API client, prompts, schemas
  ros_nodes/               Future ROS service/topic wrappers
  skills/                  Robot skill interfaces and implementations
  tests/                   Lightweight tests
```

## Quick Start

Install dependencies:

```powershell
pip install -r "Long sequence tasks/requirements.txt"
```

Set your DashScope key:

```powershell
$env:DASHSCOPE_API_KEY="your_api_key_here"
```

Run the image planning demo:

```powershell
python "Long sequence tasks/examples/run_qwen_planner_demo.py" `
  --image "C:\Users\fjh\Desktop\rm\lab_image_with_labels.jpg" `
  --task "move from table 1 to table 2 and check whether table 2 has an apple"
```

The output is a JSON plan. The default demo does not move the robot.

Run the full mock chain:

```powershell
python "Long sequence tasks/examples/run_full_mock_demo.py" `
  --image "C:\Users\fjh\Desktop\rm\lab_image_with_labels.jpg" `
  --task "move from table 1 to table 2 and check whether table 2 has an apple"
```

This calls Qwen, validates the plan, and dispatches it to local mock skills.

## Skill Idea

The LLM does not execute code directly. It outputs skill calls like:

```json
{"skill": "navigate_to", "args": {"table": "2"}}
```

Then the local executor validates and dispatches that step to a local Python skill.
