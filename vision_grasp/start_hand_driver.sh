#!/usr/bin/env bash
set -euo pipefail

ARM_TYPE="${1:-RM65}"
ARM_DOF="${2:-6}"
END_EFFECTOR="${3:-aoyi_hand}"

source /opt/ros/noetic/setup.bash
source "${HOME}/lt_grasp_ws/devel/setup.bash"

exec roslaunch rm_dual_arm_arm_driver rm_dual_arm_arm_driver.launch \
  Arm_Type:="${ARM_TYPE}" \
  Arm_Dof:="${ARM_DOF}" \
  end_effector:="${END_EFFECTOR}"
