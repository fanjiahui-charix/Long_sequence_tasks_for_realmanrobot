#!/usr/bin/env python3
# -*- coding=UTF-8 -*-

import rospy
from std_msgs.msg import Bool
from rm_dual_arm_arm_msgs.msg import Gripper_Pick, Gripper_Set

class GripperController:
    def __init__(self):
        # 初始化ROS节点
        rospy.init_node('gripper_controller', anonymous=True)
        
        # 创建两个发布者，分别用于闭合和打开夹爪
        self.pub_gripper_pick = rospy.Publisher('rm_driver/Gripper_Pick', Gripper_Pick, queue_size=10)
        self.pub_gripper_set = rospy.Publisher('rm_driver/Gripper_Set', Gripper_Set, queue_size=10)
        
        # 订阅一个自定义的控制话题，类型为Bool
        rospy.Subscriber('end_effector', Bool, self.control_callback)
        
        rospy.loginfo("Gripper controller started, waiting for commands...")

    def control_callback(self, msg):
        """根据接收到的Bool消息控制夹爪开合"""
        if msg.data:  # 如果是True，则夹爪闭合
            self.close_gripper()
        else:        # 如果是False，则夹爪打开
            self.open_gripper()

    def open_gripper(self):
        """打开夹爪"""
        gripper_set_msg = Gripper_Set()
        gripper_set_msg.position = 1000  # 0-1000，数值越大夹爪越开
        self.pub_gripper_set.publish(gripper_set_msg)
        rospy.loginfo("Gripper opened")

    def close_gripper(self):
        """闭合夹爪"""
        gripper_pick_msg = Gripper_Pick()
        gripper_pick_msg.speed = 500
        gripper_pick_msg.force = 500
        self.pub_gripper_pick.publish(gripper_pick_msg)
        rospy.loginfo("Gripper closed")

if __name__ == '__main__':
    try:
        controller = GripperController()
        rospy.spin()  # 保持节点运行，等待回调函数的触发
    except rospy.ROSInterruptException:
        pass
