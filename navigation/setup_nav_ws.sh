#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-$HOME/lt_nav_ws}"
SRC_DIR="$WORKSPACE/src"
PKG_DIR="/home/rm/Long_sequence_tasks/navigation/ros_packages/rm_dual_arm_agv"

mkdir -p "$SRC_DIR"

if [ ! -e "$SRC_DIR/rm_dual_arm_agv" ]; then
  ln -s "$PKG_DIR" "$SRC_DIR/rm_dual_arm_agv"
fi

cd "$WORKSPACE"
catkin_make

cat <<EOF
Navigation ROS workspace ready:
  $WORKSPACE

Next:
  source $WORKSPACE/devel/setup.bash
  roslaunch rm_dual_arm_agv agv_start.launch
EOF
