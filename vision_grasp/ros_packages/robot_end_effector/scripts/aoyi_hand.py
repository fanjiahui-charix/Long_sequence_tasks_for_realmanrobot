#!/usr/bin/env python3
# -*- coding=UTF-8 -*-

import socket
import time
import rospy
from std_msgs.msg import Bool


class AoYiHand():
    def __init__(self):
        self.run_ros_node()  # 启动ROS节点
        # 从ROS参数服务器读取IP和端口
        self.ip = rospy.get_param('~Arm_Ip', "192.168.10.18")
        print(f"end ip={ self.ip }")
        self.port = rospy.get_param('~Arm_Port', 8080)
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect((self.ip, self.port))
        self.get_power_ready()  # modbus初始化

    def send_cmd(self, cmd_6axis):
        self.client.send(cmd_6axis.encode('utf-8'))
        return True

    def get_power_ready(self):
        """傲意灵巧手modbus初始化"""
        data = '{"command":"set_modbus_mode","port":1,"baudrate":115200,"timeout ":2}\r\n'
        _ = self.send_cmd(cmd_6axis=data)
        time.sleep(2)
        rospy.loginfo("配置通讯端口 ModbusRTU 模式")

    def open_hand(self):
        """傲意灵巧手打开"""
        data = '{"command":"write_registers","port":1,"address":1135,"num":6,"data":[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 0],"device":2}\r\n'
        _ = self.send_cmd(cmd_6axis=data)
        time.sleep(2)
        # rospy.loginfo(_)
        rospy.loginfo("  手张开")

    def catch_dumb(self):
        """傲意灵巧手抓东西"""
        data = '{"command":"write_registers","port":1,"address":1135,"num":6,"data":[255,255,255,255,255,255,255,255,255,255,0,0],"device":2}\r\n'
        _ = self.send_cmd(cmd_6axis=data)
        time.sleep(2)
        # rospy.loginfo(_)
        rospy.loginfo("  手闭合")

    def run_ros_node(self):
        """启动ROS节点，订阅消息并控制手部动作"""
        rospy.init_node('aoyi_hand_control', anonymous=True)  # 初始化ROS节点
        rospy.Subscriber("end_effector", Bool, self.hand_control_callback)  # 订阅ROS主题
        rospy.loginfo("ROS节点启动，等待ROS消息...")

    def hand_control_callback(self, msg):
        """ROS消息回调函数"""
        # rospy.loginfo("msg_state %s",msg.data)
        if msg.data:  # 如果消息是true，表示要抓取
            self.catch_dumb()
        else:  # 如果消息是false，表示要打开手
            self.open_hand()


if __name__ == "__main__":
    try:
        hand = AoYiHand()
        rospy.spin()  # 保持节点运行
    except rospy.ROSInterruptException:
        pass
