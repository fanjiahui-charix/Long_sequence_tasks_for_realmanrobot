# 真机部署与预检指南

本文介绍 RealMan 移动操作平台的环境配置、接口接入与联调流程。建议按“配置检查 → 状态读取 → 单项技能 → 完整任务”的顺序部署，便于分别确认导航、视觉、机械臂和夹爪反馈。

## 环境与资源

| 环境 | 负责内容 | 配置项 |
| --- | --- | --- |
| Agent Python 3.10+ | ReAct、工具调用、Memory 和执行管理 | 独立虚拟环境 |
| ROS Noetic | 底盘与机械臂通信、RGB-D 采集、坐标变换 | `ros_python` |
| 分割环境 | YOLO-seg 目标分割 | `segmentation_python` |
| FoundationPose Conda | 6D 位姿估计与模型推理 | `foundationpose_python` |

适配层通过独立进程调用各环境。模型权重、物体网格和平台标定由部署配置指定，ROS 与 FoundationPose 环境可沿用现有配置。

## 配置硬件接口

以 [hardware.example.yaml](../config/hardware.example.yaml) 为模板建立平台配置，并填写以下内容：

| 配置 | 需要确认的内容 |
| --- | --- |
| `chassis_host` / `chassis_port` | 底盘服务地址 |
| `location_mapping` / `waypoints` | A/B 标签对应的导航点、目标位置和到达容差 |
| `state_command` | 输出带时间戳 `Observation` JSON 的只读状态接口 |
| `grasp_stop_command` | 平台停止或取消操作的独立命令 |
| `grasp_config` | 相机与基座坐标系、机械臂侧、末端类型、预抓取和回撤设置 |
| `mesh_path` / `segmentation_weights` | 目标网格与分割模型权重 |
| `segmentation_label` / `segmentation_confidence` | 目标类别与分割阈值 |
| `pose_min_score` | 可选的位姿质量阈值；按所用模型输出定义配置 |
| `calibration` | 实测夹爪宽度标定 |
| `pose_ttl_s` / `observation_ttl_s` | 位姿与状态反馈的有效时间 |
| `stage_timeout_s` | 视觉流程中单个阶段的超时设置 |

完成平台接口核对后设置 `interfaces_confirmed`，完成 RGB-D 与坐标变换时序核对后设置 `timing_confirmed`。模板中的空值用于标识待填写项。

## 状态反馈与夹爪标定

`state_command` 返回当前位置、定位有效性、机械臂空闲状态、运动稳定状态、回撤状态和夹爪宽度样本。字段定义见 [机器人接口](BACKEND_API.md)。

夹爪标定模板见 [gripper_calibration.example.yaml](../config/gripper_calibration.example.yaml)。应测量空夹与持有目标时的宽度区间，并记录样本数量、稳定性、单位及采样时间；硬件配置使用 `origin: measured`。当末端只提供角度反馈时，需要先建立经过测量的角度—实际宽度关系。

导航和停止接口也需要配套状态读取：导航到达由位置、标记点和定位有效性共同判断；发出停止命令后，通过新的空闲与稳定反馈确认停止结果。

## RGB-D 与坐标时序

联调时核对深度单位、RGB/Depth 对齐、相机内参、网格尺度，以及 `camera_frame` 到 `base_frame` 的外参。相机或机械臂运动时，位姿转换还需要与采集时刻对应。

当前采集适配器以采集开始时刻作为位姿年龄的保守下界。部署时应结合传感器时间戳、相机与 TF 时钟，以及实际推理延迟设置有效时间；这些配置共同决定定位结果何时需要重新获取。

## 离线预检

填写自己的硬件 YAML 后运行：

```bash
python -m robot_agent preflight --hardware-config config/hardware.local.yaml
```

预检检查接口确认项、资源文件、A/B 导航配置、抓取配置和实测标定，不连接硬件或发出动作。可先用示例模板查看需要填写的字段：

```bash
python -m robot_agent preflight --hardware-config config/hardware.example.yaml
```

未填写完整时会返回 `hardware_ready: false` 和 `missing` 列表；补齐后再进行设备联调。

## 分阶段联调

1. **状态读取**：确认观察中的时间戳、定位、机械臂及夹爪反馈与实际设备一致。
2. **视觉定位**：采集目标 RGB-D，检查 Mask、6D 位姿、坐标系及视觉资源。
3. **导航**：逐个确认 A/B 导航点、位置容差，以及携物时的机械臂姿态。
4. **抓取**：在清空的工作区测试预抓取、闭合与回撤，检查实际宽度反馈和掉落情况。
5. **异常处理**：测试超时、取消、反馈丢失和重启后的状态恢复，确认停止接口与反馈链路。
6. **完整任务**：接通上述能力后，再运行 A→B→A 的取物任务。

联调时保留现场操作人员与可用的急停装置。机械臂配置、相机外参与夹爪标定按目标平台实测值填写。

完整任务的调用形式如下，`mission.local.json` 为已验证且与当前场景对应的任务描述：

```bash
python -m robot_agent demo --llm qwen --mission-file config/mission.local.json --memory --backend realman --enable-hardware --hardware-config config/hardware.local.yaml --output-dir runtime/hardware-mission
```

`--enable-hardware` 用于显式启用设备操作，加载配置时会再次执行预检。任务结果与执行轨迹写入指定输出目录，便于结合设备日志分析。
