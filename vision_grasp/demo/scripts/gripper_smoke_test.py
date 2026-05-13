#!/usr/bin/env python3
"""Open or close the Inspire two-finger gripper."""

import rospy

from rm_dual_arm_arm_msgs.msg import Gripper_Pick, Gripper_Set


def main():
    rospy.init_node("gripper_smoke_test", anonymous=True)

    arm_ns = rospy.get_param("~arm_ns", "l_arm").strip("/")
    open_gripper = rospy.get_param("~open", True)
    open_position = int(rospy.get_param("~open_position", 1000))
    pick_speed = int(rospy.get_param("~pick_speed", 400))
    pick_force = int(rospy.get_param("~pick_force", 300))

    set_pub = rospy.Publisher(f"/{arm_ns}/rm_driver/Gripper_Set", Gripper_Set, queue_size=1)
    pick_pub = rospy.Publisher(f"/{arm_ns}/rm_driver/Gripper_Pick", Gripper_Pick, queue_size=1)

    rospy.sleep(1.0)

    if open_gripper:
        msg = Gripper_Set()
        msg.position = max(1, min(1000, open_position))
        set_pub.publish(msg)
        rospy.loginfo("Published gripper open command to /%s/rm_driver/Gripper_Set", arm_ns)
    else:
        msg = Gripper_Pick()
        msg.speed = max(1, min(1000, pick_speed))
        msg.force = max(1, min(1000, pick_force))
        pick_pub.publish(msg)
        rospy.loginfo("Published gripper close command to /%s/rm_driver/Gripper_Pick", arm_ns)

    rospy.sleep(1.0)


if __name__ == "__main__":
    main()

