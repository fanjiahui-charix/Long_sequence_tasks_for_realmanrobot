## **一.项目介绍**

本功能包是对云迹底盘的ros封装，通过发布对应话题可以执行对应命令。

## **二.代码结构**

rm_dual_arm_agv
    ├── rm_dual_arm_agv
    │   ├── CMakeLists.txt
    │   ├── include
    │   │   └── agv
    │   ├── launch
    │   │   └── agv_start.launch #底盘ros功能包的launch启动文件
    │   ├── msg                  #自定义的消息类型
    │   │   ├── RobotJoyControl.msg
    │   │   ├── RobotLedSetColor.msg
    │   │   └── RobotLocation.msg
    │   ├── package.xml
    │   ├── scripts
    │   │   └── agv_controller.py #封装的底盘ros功能包
    │   └── src




## **三.编译方法**

- 创建 文件夹
    - mkdir -p ~/lt_ros_ws/src
- 将 `Long_sequence_tasks/ros_packages/rm_dual_arm_agv` 放入工作空间 `~/lt_ros_ws/src/` 中
- 编译ros包

    - cd ~/lt_ros_ws
    - catkin_make

## **四.运行指令**

- 1.启动底盘ros功能包的launch
```bash
cd ~/lt_ros_ws
source devel/setup.bash
roslaunch rm_dual_arm_agv agv_start.launch
```

- 2.发送单点导航命令：
```bash
cd ~/lt_ros_ws
source devel/setup.bash
rostopic pub -1 /navigation_marker std_msgs/String "data: 'pointc'"
```

## **五.注意**
    运行的示例代码的时候需要注意，底盘移动到标记点之前需要先建图并设置标记点。
    （建图和设置标记点教程见链接：http://waterdocs.pages.yunjichina.com.cn/user_manual/exports/WATER%EF%BC%88%E6%B0%B4%E6%BB%B4%EF%BC%89%E7%94%A8%E6%88%B7%E4%BD%BF%E7%94%A8%E6%89%8B%E5%86%8C-v0.5.1.pdf）
