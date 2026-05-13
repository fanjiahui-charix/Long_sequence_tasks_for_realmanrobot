#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-$HOME/lt_grasp_ws}"
SRC_DIR="$WORKSPACE/src"
BASE_DIR="/home/rm/Long_sequence_tasks/vision_grasp/ros_packages"

mkdir -p "$SRC_DIR"

for pkg in rm_dual_arm_arm_msgs robot_end_effector; do
  target="$SRC_DIR/$pkg"
  source_path="$BASE_DIR/$pkg"
  if [ ! -e "$target" ]; then
    ln -s "$source_path" "$target"
  fi
done

cd "$WORKSPACE"
catkin_make

cat <<EOF
Vision-grasp ROS workspace ready:
  $WORKSPACE

Next:
  source $WORKSPACE/devel/setup.bash
EOF
