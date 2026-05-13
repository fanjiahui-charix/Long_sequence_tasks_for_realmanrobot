#!/usr/bin/env python3
"""Open or close the five-finger dexterous hand through arm-driver ROS topics."""

import rospy

from rm_dual_arm_arm_msgs.msg import Hand_Angle, Hand_Force, Hand_Speed


def clamp_angle(value: int) -> int:
    return int(max(-1, min(1000, value)))


def main():
    rospy.init_node("dexterous_hand_smoke_test", anonymous=True)

    arm_ns = rospy.get_param("~arm_ns", "l_arm").strip("/")
    open_hand = rospy.get_param("~open", True)
    hand_speed = int(rospy.get_param("~hand_speed", 400))
    hand_force = int(rospy.get_param("~hand_force", 300))
    open_angles = list(rospy.get_param("~open_angles", [0, 0, 0, 0, 0, 1000]))
    close_angles = list(rospy.get_param("~close_angles", [1000, 1000, 1000, 1000, 1000, 0]))
    raw_angles = rospy.get_param("~angles", None)

    speed_pub = rospy.Publisher(f"/{arm_ns}/rm_driver/Hand_SetSpeed", Hand_Speed, queue_size=1)
    force_pub = rospy.Publisher(f"/{arm_ns}/rm_driver/Hand_SetForce", Hand_Force, queue_size=1)
    angle_pub = rospy.Publisher(f"/{arm_ns}/rm_driver/Hand_SetAngle", Hand_Angle, queue_size=1)

    rospy.sleep(1.0)

    speed_msg = Hand_Speed()
    force_msg = Hand_Force()
    speed_msg.hand_speed = max(1, min(1000, hand_speed))
    force_msg.hand_force = max(1, min(1000, hand_force))
    speed_pub.publish(speed_msg)
    force_pub.publish(force_msg)
    rospy.sleep(0.5)

    angle_msg = Hand_Angle()
    if raw_angles is not None:
        angles = list(raw_angles)
    else:
        angles = open_angles if open_hand else close_angles

    if len(angles) != 6:
        rospy.logerr("Hand angle array must have 6 entries, got %d", len(angles))
        return

    angle_msg.hand_angle = [clamp_angle(v) for v in angles]
    angle_pub.publish(angle_msg)

    rospy.loginfo(
        "Published dexterous hand command to /%s/rm_driver/Hand_SetAngle with angles=%s",
        arm_ns,
        angle_msg.hand_angle,
    )
    rospy.sleep(1.0)


if __name__ == "__main__":
    main()

