# 机器人接口

`RobotBackend` 定义导航、视觉定位、抓取和状态读取的统一接口。Agent 通过该接口调用机器人能力，具体平台可以使用自己的 SDK、ROS 节点或设备通信协议。

接口定义见 [backends/base.py](../robot_agent/backends/base.py)，自定义实现参考 [custom_backend.py](../examples/custom_backend.py)。

## 异步方法

| 方法 | 输入与返回 |
| --- | --- |
| `navigate_to(target, mission) -> SkillReply` | 输入任务位置标签，执行导航并返回状态及结果 |
| `locate_object(object_category, mission, *, motion_epoch) -> SkillReply` | 执行视觉定位，在 `observation.pose` 中返回当前 `PoseReference` |
| `grasp_object(pose, mission) -> SkillReply` | 根据给定定位完成预抓取、抓取、闭合及回撤 |
| `observe_robot_state(mission) -> Observation` | 读取带时间戳的当前位置、运动与夹爪反馈 |
| `cancel_current_action() -> None` | 向平台发出停止或取消请求 |

`SkillReply` 包含 `status`、`result`、`error_code` 和可选的 `observation`。执行器汇总技能回复与独立观察，再进行结果检查。

## Observation

`Observation` 的主要字段如下，具体类型见 [schemas.py](../robot_agent/schemas.py)：

| 字段 | 内容 |
| --- | --- |
| `timestamp` / `source` | 状态采样或接收时间、来源标识 |
| `robot_location` / `localization_confirmed` | 当前任务位置标签与定位有效性 |
| `navigation_status` | 导航运行状态 |
| `arm_idle` / `motion_settled` | 机械臂空闲及整体运动稳定状态 |
| `retreat_complete` | 抓取回撤状态 |
| `gripper_samples` | 带独立时间戳的实际夹爪宽度样本 |
| `object_category` / `object_detected` / `mask_valid` | 检测类别、目标检测和分割结果 |
| `pose` | 当前目标位姿及其采集、坐标与运动信息 |

尚未支持或无法读取的字段使用 `None / UNKNOWN`；夹爪宽度不可读时，`gripper_samples` 为空。这样可将“尚不确定”与已确认的状态区分开。

## 夹爪宽度反馈

每个 `WidthSample` 提供 `timestamp`、`width_mm`、`measured`、`source` 和 `after_retreat`。宽度单位为毫米，时间戳对应实际测量或接收时间。

实现状态读取时应接入设备反馈，并使用平台的标定换算。命令目标开合量与实际测量值分别处理；若反馈为手指角度，需要先标定它与夹持宽度的关系。

持物判断使用 [GripperCalibration](../robot_agent/schemas.py) 的空夹区间、持物区间、样本数量、稳定性与时间要求。持物确认还结合回撤状态和目标身份；无法确认时保留 `UNKNOWN`，由后续观察或任务恢复继续处理。

## JSON 状态桥接

`JsonStateReader` 支持调用部署配置中的只读命令。该命令向标准输出写入一个 `Observation` JSON 对象，至少显式提供 `timestamp` 与 `source`；调试日志写入标准错误。

`state_command` 与 `grasp_stop_command` 都是平台配置中的参数数组。前者读取状态，后者执行停止；停止是否完成仍由随后采集的空闲和稳定反馈判断。

## RealMan 适配

现有实现组合以下能力：

- `ChassisNavigationClient`：底盘导航、标记点与取消操作。
- ROS RGB-D 采集与 YOLO-seg：生成当前图像、深度与目标 Mask。
- FoundationPose 与 TF：估计目标 6D 位姿，转换到机械臂基座坐标系。
- `execute_pose_grasp_from_config`：执行配置中的预抓取、闭合和回撤。
- 平台状态桥接：读取定位、机械臂、运动及实际夹爪反馈。

WATER 底盘到达检查结合完成状态、匹配的标记点、位置容差与独立定位有效性。状态桥应根据所用平台提供定位有效性来源。

视觉适配器保留采集时间和位姿引用；抓取适配器校验对应位姿文件与抓取配置。RGB-D 同步、相机外参和移动时的 TF 时间对应关系在设备联调阶段确认。

## 接入顺序

建议先实现 `observe_robot_state` 和停止接口，再依次接入导航、视觉与抓取。用 Mock Backend 检查 Agent 数据流后，按 [部署指南](HARDWARE_VALIDATION.md) 验证目标平台配置，逐步运行单项技能与完整任务。
