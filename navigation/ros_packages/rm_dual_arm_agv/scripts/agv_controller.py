#!/usr/bin/env python3
# -*- coding=UTF-8 -*-

"""
版权所有 (c) 2024 [睿尔曼智能科技有限公司]。保留所有权利。
在满足以下条件的情况下，允许重新分发和使用源代码和二进制形式的代码，无论是否修改：
1. 重新分发的源代码必须保留上述版权声明、此条件列表和以下免责声明。
2. 以二进制形式重新分发的代码必须在随分发提供的文档和/或其他材料中复制上述版权声明、此条件列表和以下免责声明。

本软件由版权持有者和贡献者“按原样”提供，不提供任何明示或暗示的保证，
包括但不限于对适销性和特定用途适用性的暗示保证。
在任何情况下，即使被告知可能发生此类损害的情况下，
版权持有者或贡献者也不对任何直接的、间接的、偶然的、特殊的、惩罚性的或后果性的损害
（包括但不限于替代商品或服务的采购；使用、数据或利润的损失；或业务中断）负责，
无论是基于合同责任、严格责任还是侵权行为（包括疏忽或其他原因）。

此模块允许AGV底盘各个话题订阅者的回调函数直接调用，方便后续ROS节点相应功能的开发。

此模块提供[
    单目标预设点导航、单目标点位导航、多目标预设点导航、导航取消、获取机器人全局状态、
    矫正机器人位姿、获取AGV底盘电量、速度控制、各项最大速度设置、获取参数值、底盘RGB三色灯设置
]的功能。这些功能皆根据函数的形式封装，等待ROS话题订阅者调用。可理解为ROS与底盘的桥梁，扮演驱动的角色。

示例用法：
rospy.init_node('process', anonymous=True)
rospy.Subscriber("/robot_marker", String, 
                 callback_robot_marker)
其他函数功能使用方式类似。
"""

import socket
import json
import rospy
from std_msgs.msg import String
from std_msgs.msg import Float64

from rm_dual_arm_agv.msg import RobotLocation  
from rm_dual_arm_agv.msg import RobotJoyControl
from rm_dual_arm_agv.msg import RobotLedSetColor
from rm_dual_arm_agv.msg import RobotStatus


def callback_robot_marker(data: String):
    
    """话题/robot_marker的回调函数

    订阅话题/robot_marker的String类型数据，并将得到的结果发送至AGV，从而达到单点导航

    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_marker Received letter: {data.data}")
    target_marker = data.data
    move_command = f'/api/move?marker={target_marker}'	# /api/move?marker={dianA} ，移动至代号为"dianA"的目标点
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/move?marker={target_marker}")
        
def callback_robot_location(data: RobotLocation):
    
    """话题/robot_location的回调函数

    订阅话题/robot_location的RobotLocation类型数据，并将得到的结果发送至AGV，从而导航至指定坐标位置
 
    Args:
        data (RobotLocation): ROS中agv.msg下的RobotLocation数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_location Received letter: {data}")
    target_x_y_theta = f'{data.x},{data.y},{data.theta}'	# /api/move?location=15.0,4.0,1.5707963
    move_command = f'/api/move?location={target_x_y_theta}'	# 移动至location(15.0, 4.0, pai/2)的目标点
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/move?location={target_x_y_theta}")   
    full_response = ''
    
def callback_robot_multipoint(data: String):
    
    """话题/robot_multipoint的回调函数
 
    订阅话题/robot_multipoint的String类型数据，并将得到的结果发送至AGV，从而实现多目标点移动功能

    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_multipoint Received letter: {data.data}") 
    target_Multipoint_marker = data.data	#m1,m2,m3   /api/move?markers=m1,m2,m3&distance_tolerance=1.0&count=-1
    move_command = f'/api/move?markers={target_Multipoint_marker}&distance_tolerance=0.5&count=1'   #调用移动接口，移动至location(15.0, 4.0, pai/2)的目标点
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/move?markers={target_Multipoint_marker}&distance_tolerance=0.5&count=1")   

def callback_robot_move_cancel(data: String):
    
    """话题/robot_move_cancel的回调函数

    通过订阅/robot_move_cancel去取消当前正在进行的移动指令，停止规划器的工作

    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_move_cancel Received letter: {data.data}")
    move_command = f'/api/move/cancel'  
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/move/cancel0&count=-1")   

def callback_get_robot_status(data: String):
    """话题/robot_get_robot_status的回调函数

    通过订阅/robot_get_robot_status去获取AGV底盘当前全局状态

    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    rospy.loginfo(f"callback_get_robot_status Received letter: {data.data}")
    move_command = f'/api/robot_status'	#获得机器人当前的全局状态
    chassis_client.send(move_command.encode('utf-8'))        
    rospy.loginfo(f"send chassis_client :/api/robot_status")   
    full_response = ''
    
    
def callback_robot_position_adjust_marker(data: String):
    """话题/robot_position_adjust_marker的回调函数

    通过订阅/robot_position_adjust_marker话题去矫正AGV底盘运动位姿
 
    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_position_adjust_marker Received letter: {data.data}")
    target_marker = data.data                                         #指定marker校正机器人位置
    move_command = f'/api/position_adjust?marker={target_marker}'   #告知机器人当前处于代号为001的marker点位上
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/position_adjust?marker={target_marker}")
    
def callback_get_power_status(data: String):

    """话题/robot_get_power_status的回调函数

    通过订阅/robot_get_power_status话题去获取AGV底盘电量
 
    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_get_power_status Received letter: {data.data}")
    move_command = f'/api/get_power_status'                      #获取底盘电量
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/get_power_status")   
    full_response = ''
    
def callback_robot_joy_control(data: RobotJoyControl):
    """话题/robot_joy_control的回调函数

    通过订阅/robot_joy_control话题去直接控制基于机器全局坐标系的x, y轴上的速度变化
    
    Args:
        data (RobotJoyControl): ROS中agv.msg下的RobotJoyControl数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_joy_control Received letter: {data}")  #机器人直接控制指令，可以执行左传右转前进后退等
    angular_velocity = data.angular_velocity                    #机器人角速度设值范围为 (-1.0 ~ 1.0)rad/s  正 机器人原地左转;负 机器人原地右转
    linear_velocity = data.linear_velocity                      #机器人线速度设值范围为 (-0.5 ~ 0.5)m/s  正  机器人前进 ;负 机器人后退
    move_command = f'/api/joy_control?angular_velocity={angular_velocity}&linear_velocity={linear_velocity}'  
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/joy_control?angular_velocity={angular_velocity}&linear_velocity={linear_velocity}")   

def callback_robot_max_speed(data: Float64):
    """话题/robot_max_speed的回调函数

    通过订阅/robot_max_speed话题去直接设置AGV最大行进速度，范围[0.3, 0.7]
 
    Args:
        data (Float64): ROS中std_msgs.msg下的Float64数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_max_speed Received letter: {data.data}")
    target = data.data
    move_command = f'/api/set_params?max_speed={target}'   #机器人最大行进速度(百分比) 取值范围[0.3,0.7]
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/set_params?max_speed={target}")

def callback_robot_max_speed_ratio(data: Float64):
    """话题/robot_max_speed_ratio的回调函数

    通过订阅/robot_max_speed_ratio话题去直接设置AGV最大行进速度比，范围[0.3, 1.4] 
 
    Args:
        data (Float64): ROS中std_msgs.msg下的Float64数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_max_speed_ratio Received letter: {data.data}")
    target = data.data
    move_command = f'/api/set_params?max_speed_ratio={target}'     #机器人最大行进速度百分比 取值范围[0.3,1.4] 
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/set_params?max_speed_ratio={target}")

def callback_robot_max_speed_linear(data: Float64):
    """话题/robot_max_speed_linear的回调函数
    
    通过订阅/robot_max_speed_linear话题去直接设置AGV最大线速度(m/s)，范围[0.1, 1.0] 
    
    Args:
        data (Float64): ROS中std_msgs.msg下的Float64数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_max_speed_linear Received letter: {data.data}")
    target = data.data
    move_command = f'/api/set_params?max_speed_linear={target}'    #机器人最大线速度(m/s) 取值范围[0.1,1.0] 
    chassis_client.send(move_command.encode('utf-8'))               
    rospy.loginfo(f"send chassis_client :/api/set_params?max_speed_linear={target}")

def callback_robot_max_speed_angular(data: Float64):
    """话题/robot_max_speed_angular的回调函数
 
    通过订阅/robot_max_speed_angular话题去直接设置AGV最大角速度(rad/s)，范围[0.5,3.5] 

    Args:
        data (Float64): ROS中std_msgs.msg下的Float64数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_max_speed_angular Received letter: {data.data}")
    target = data.data
    move_command = f'/api/set_params?max_speed_angular={target}'     #机器人最大角速度(rad/s) 取值范围[0.5,3.5] 
    chassis_client.send(move_command.encode('utf-8'))
    rospy.loginfo(f"send chassis_client :/api/set_params?max_speed_angular={target}")

def callback_robot_get_params(data: String):
    """话题/robot_get_params的回调函数

    通过订阅/robot_get_params话题去获取参数列表和当前值
 
    Args:
        data (String): ROS中std_msgs.msg下的String数据类型，通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_get_params Received letter: {data.data}") 
    move_command = f'/api/get_params'                               #获取参数列表和当前值
    chassis_client.send(move_command.encode('utf-8')) 
    rospy.loginfo(f"send chassis_client :/api/get_params")	

def callback_robot_LED_set_color(data: RobotLedSetColor):
    """话题/robot_LED_set_color的回调函数
 
    通过订阅/robot_LED_set_color话题设置灯带颜色，RGB三通道数据范围皆是[0, 100]

    Args:
        data (RobotLedSetColor): ROS中agv.msg下的RobotLedSetColor数据类型，
          通过订阅话题而监听到的数据
    """
    
    rospy.loginfo(f"callback_robot_LED_set_color Received letter: {data}") 
    set_color_R = data.R
    set_color_G = data.G
    set_color_B = data.B
    move_command = f'/api/LED/set_color?r={set_color_R}&g={set_color_G}&b={set_color_B}'  #设置灯带颜色为绿色  /api/LED/set_color?r=100&g=100&b=0
    chassis_client.send(move_command.encode('utf-8')) 
    rospy.loginfo(f"send chassis_client :/api/LED/set_color?r={set_color_R}&g={set_color_G}&b={set_color_B}")


def get_robot_status(overtime: float=10):
    send_command = f'/api/robot_status'
    chassis_client.send(send_command.encode('utf-8'))
    # 设置延迟获取机器人状态
    begin_time = rospy.Time.now().to_sec()
    while not rospy.is_shutdown() and (rospy.Time.now().to_sec() - begin_time) <= overtime:
        recv_data = chassis_client.recv(1024).decode()
        if not recv_data:  # 如果接收到的数据为空
            continue
        try:
            json_data = json.loads(recv_data)
        except json.JSONDecodeError:  # 如果解析 JSON 数据失败
            continue
        if "command" not in json_data:
            continue  # 如果没有 command 键，继续等待
        if json_data["command"] == send_command and json_data["status"] == "OK":
            return json_data
    
    return None




if __name__ == '__main__':
    # 初始化节点名
    rospy.init_node('chassis_driver_node', anonymous=True)

    chassis_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    chassis_host = rospy.get_param("~chassis_ip", "192.168.10.10")
    chassis_port = rospy.get_param("~chassis_port", 31001)
    chassis_client.connect((chassis_host, chassis_port))
    rospy.loginfo('---------------------------start----------------------------')

    rospy.Subscriber("/robot_marker", String, callback_robot_marker)   # 单目标点移动,移动至代号为"target_name"的目标点
    rospy.Subscriber("/robot_location", RobotLocation, callback_robot_location) # 单目标点移动,移动至location(15.0, 4.0, pai/2)的目标点
    rospy.Subscriber("/robot_multipoint", String, callback_robot_multipoint)  # 多目标点移动
    rospy.Subscriber("/robot_move_cancel", String, callback_robot_move_cancel) # 取消当前正在进行的移动指令
    rospy.Subscriber("/robot_get_robot_status", String, callback_get_robot_status)   # 获取机器人当前全局状态
    rospy.Subscriber("/robot_position_adjust_marker", String, callback_robot_position_adjust_marker)  # 指定marker校正机器人位置
    rospy.Subscriber("/robot_get_power_status", String, callback_get_power_status)     # 获取底盘电量
    rospy.Subscriber("/robot_joy_control", RobotJoyControl, callback_robot_joy_control)   # 机器人直接控制指令，可以执行左传右转前进后退等
    rospy.Subscriber("/robot_max_speed", Float64, callback_robot_max_speed) # 机器人最大行进速度(百分比) 取值范围[0.3,0.7]
    rospy.Subscriber("/robot_max_speed_ratio", Float64, callback_robot_max_speed_ratio)  # 机器人最大行进速度百分比 取值范围[0.3,1.4] 
    rospy.Subscriber("/robot_max_speed_linear", Float64, callback_robot_max_speed_linear) # 机器人最大线速度(m/s) 取值范围[0.1,1.0] 
    rospy.Subscriber("/robot_max_speed_angular", Float64, callback_robot_max_speed_angular) # 机器人最大角速度(rad/s) 取值范围[0.5,3.5] 
    rospy.Subscriber("/robot_get_params", String, callback_robot_get_params) # 获取参数列表和当前值
    rospy.Subscriber("/robot_LED_set_color", RobotLedSetColor, callback_robot_LED_set_color) # 设置灯带颜色
    
    # 反馈导航结果
    pub_robot_status = rospy.Publisher('/robot_status', RobotStatus, queue_size=10)

    # 设置发布频率
    rate = rospy.Rate(1)
    while not rospy.is_shutdown():
        robot_status = get_robot_status()

        if robot_status is not None:
            status_data = RobotStatus()
            status_data.move_target = robot_status["results"]["move_target"]
            status_data.move_status = robot_status["results"]["move_status"]
            status_data.move_retry_times = robot_status["results"]["move_retry_times"]
            status_data.charge_state = robot_status["results"]["charge_state"]
            status_data.soft_estop_state = robot_status["results"]["soft_estop_state"]
            status_data.hard_estop_state = robot_status["results"]["hard_estop_state"]
            status_data.estop_state = robot_status["results"]["estop_state"]
            status_data.power_percent = robot_status["results"]["power_percent"]
            status_data.current_pose.x = robot_status["results"]["current_pose"]["x"]
            status_data.current_pose.y = robot_status["results"]["current_pose"]["y"]
            status_data.current_pose.theta = robot_status["results"]["current_pose"]["theta"]
            status_data.current_floor = robot_status["results"]["current_floor"]
            status_data.chargepile_id = robot_status["results"]["chargepile_id"]
            status_data.error_code = robot_status["results"]["error_code"]

            # 发布状态
            pub_robot_status.publish(status_data)
        else:
            rospy.logerr("The chassis status can't be obtained within 10s!")
            break

        rate.sleep()
    
    rospy.loginfo('---------------------------final----------------------------')