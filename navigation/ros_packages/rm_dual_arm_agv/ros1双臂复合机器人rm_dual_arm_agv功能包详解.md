# 双臂复合机器人rm_dual_arm_agv功能包详解

## 一.rm_dual_arm_agv功能包说明

rm_dual_arm_agv功能包是为双臂复合机器人设计的ROS封装，用于控制云迹底盘（Yunji chassis）执行导航、速度控制和状态查询等功能。通过发布ROS话题将指令转换为底盘API调用，基于TCP socket通信（IP: 192.168.10.10, 端口: 31001）实现与硬件的交互。

## 二.rm_dual_arm_agv功能包功能架构说明

```
rm_dual_arm_agv
    ├── CMakeLists.txt                # ROS包的编译配置文件，用于构建和依赖管理
    ├── launch
    │   └── agv_start.launch          # 启动文件，运行agv_controller.py节点以初始化底盘控制
    ├── msg
    │   ├── RobotJoyControl.msg       # 定义速度控制消息（线速度和角速度）
    │   ├── RobotLedSetColor.msg      # 定义RGB灯带颜色设置消息
    │   └── RobotLocation.msg         # 定义目标坐标点消息（x, y, theta）
    ├── package.xml                    # ROS包的元数据，定义依赖和包信息
    ├── README_AGV.md                 # 功能包的使用说明和概述
    ├── ros1双臂复合机器人rm_dual_arm_agv功能包详解.md  # 本文档，详细介绍功能包
    └── scripts
        └── agv_controller.py         # 核心脚本，处理ROS话题订阅和底盘API通信

3 directories, 9 files
```


## 三.rm_dual_arm_agv功能包使用

在使用rm_dual_arm_agv功能包前，需确保ROS 1（推荐Noetic）环境已配置，工作空间已编译完成，且机器人已开机并可通过IP 192.168.10.10:31001访问。执行以下命令启动功能包：

```bash
cd ~/lt_ros_ws
source devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

## 四. rm_dual_arm_agv功能包话题

| 话题名称                           | 消息类型                              | 描述                                                         |
| ---------------------------------- | ------------------------------------- | ------------------------------------------------------------ |
| /navigation_marker                 | std_msgs/String                       | 触发单目标预设点导航，发送目标点代号（如 "dianA"）以移动至指定点。 |
| /navigation_location               | rm_dual_arm_agv/RobotLocation         | 触发单目标点导航，发送目标坐标 (x, y, theta) 以移动至指定位置。 |
| /navigation_multipoint             | std_msgs/String                       | 触发多目标预设点导航，发送多个目标点代号（如 "m1,m2,m3"）。  |
| /navigation_move_cancel            | std_msgs/String                       | 取消当前正在进行的移动指令，停止导航规划器的工作。           |
| /navigation_get_robot_status       | std_msgs/String                       | 获取AGV底盘当前全局状态。                                    |
| /navigation_position_adjust_marker | std_msgs/String                       | 矫正AGV底盘位姿，发送指定marker代号以校准机器人位置。        |
| /navigation_get_power_status       | std_msgs/String                       | 获取AGV底盘当前电量状态。                                    |
| /navigation_joy_control            | rm_dual_arm_agv/RobotJoyControl       | 直接控制AGV速度，设置线速度 (-0.5 ~ 0.5 m/s) 和角速度 (-1.0 ~ 1.0 rad/s)。 |
| /navigation_max_speed              | std_msgs/Float64                      | 设置AGV最大行进速度，范围 [0.3, 0.7]。                       |
| /navigation_max_speed_ratio        | std_msgs/Float64                      | 设置AGV最大行进速度百分比，范围 [0.3, 1.4]。                 |
| /navigation_max_speed_linear       | std_msgs/Float64                      | 设置AGV最大线速度 (m/s)，范围 [0.1, 1.0]。                   |
| /navigation_max_speed_angular      | std_msgs/Float64                      | 设置AGV最大角速度 (rad/s)，范围 [0.5, 3.5]。                 |
| /navigation_get_params             | std_msgs/String                       | 获取AGV参数列表及其当前值。                                  |
| /navigation_LED_set_color          | rm_dual_arm_agv/RobotLedSetColor      | 设置AGV底盘RGB灯带颜色，RGB值范围 [0, 100]。                 |
| /navigation_feedback               | std_msgs/String                       | 发布AGV底盘通过socket接收到的反馈信息。                      |

## 五.双臂复合机器人底盘二次开发参考资料

以下文档为双臂复合机器人底盘的二次开发提供支持：

- [底盘软件API使用手册](../rm_dual_arm_hardware_docs/robot_chassis/WATER（水滴）软件API手册V1.1.pdf)

  本ros包基于此底盘API开发而来

- [底盘户用使用手册](../rm_dual_arm_hardware_docs/robot_chassis/底盘户用使用手册V1.2.pdf)

- [关于水滴2到点误差大以及避障距离过长的解决方法](../rm_dual_arm_hardware_docs/关于水滴2到点误差大以及避障距离过长的解决方法.pdf)

- [云迹底盘小水滴电池拆卸说明](../rm_dual_arm_hardware_docs/云迹底盘小水滴电池拆卸说明.docx)

## 六. rm_dual_arm_agv功能包关键代码分析

### 6.1 功能概述

rm_dual_arm_agv功能包的核心脚本是scripts/agv_controller.py，它通过ROS节点与云迹底盘的API进行通信，充当ROS与AGV底盘之间的桥梁。该脚本通过socket连接（IP: 192.168.10.10, 端口: 31001）与底盘通信，订阅多个ROS话题以接收控制指令，并将指令转换为底盘API调用，同时通过/navigation_feedback话题发布底盘的反馈信息。主要功能包括：

- **导航控制**：支持单目标点导航（预设点和坐标点）、多目标点导航以及导航取消。
- **状态获取**：获取底盘全局状态和电量信息。
- **速度控制**：设置最大行进速度、速度百分比、线速度和角速度，或通过手柄控制直接调整速度。
- **位姿矫正**：通过指定marker校准机器人位置。
- **灯光控制**：设置底盘RGB灯带颜色。
- **参数管理**：获取和设置底盘参数。

### 6.2 关键代码结构

#### 初始化与连接

脚本在启动时初始化一个ROS节点（process），并通过socket.socket建立与底盘的TCP连接（chassis_client）。连接参数固定为IP地址192.168.10.10和端口31001。成功连接后，脚本订阅14个ROS话题，并定义对应的回调函数处理指令。

#### 话题订阅与回调函数

每个话题对应一个回调函数，负责将ROS消息转换为底盘API命令，并通过socket发送。例如：

- **/navigation_marker**：接收std_msgs/String消息，提取目标点代号，构造/api/move?marker={target_marker}命令，发送至底盘。
- **/navigation_joy_control**：接收RobotJoyControl消息，解析线速度和角速度，发送/api/joy_control?angular_velocity={angular_velocity}&linear_velocity={linear_velocity}命令。
- **/navigation_LED_set_color**：接收RobotLedSetColor消息，解析RGB值，发送/api/LED/set_color?r={R}&g={G}&b={B}命令。

回调函数使用rospy.loginfo记录接收到的消息和发送的命令，便于调试。所有命令通过chassis_client.send以UTF-8编码发送。

#### 反馈处理

脚本通过chassis_client.recv循环接收底盘的反馈数据，累积到full_response变量中。当接收到至少三个JSON对象（通过检查换行符\n计数）时，退出接收循环。反馈数据通过/navigation_feedback话题发布，供其他节点使用。如果发生socket.timeout，脚本记录错误日志并中断接收。

### 6.3 消息类型说明

功能包定义了三个自定义消息类型，位于msg/目录：

- **RobotJoyControl.msg**：包含float32 angular_velocity（角速度，-1.0 ~ 1.0 rad/s）和float32 linear_velocity（线速度，-0.5 ~ 0.5 m/s），用于速度控制。
- **RobotLocation.msg**：包含float32 x、float32 y和float32 theta，用于指定目标坐标点。
- **RobotLedSetColor.msg**：包含uint16 R、uint16 G和uint16 B（范围0 ~ 100），用于设置RGB灯带颜色。


