#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.run/bringup"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"

MODE="minimal"
ARM_TYPE="RM65"
ARM_DOF="6"
END_EFFECTOR="aoyi_hand"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --arm-type)
      ARM_TYPE="$2"
      shift 2
      ;;
    --arm-dof)
      ARM_DOF="$2"
      shift 2
      ;;
    --end-effector)
      END_EFFECTOR="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$MODE" != "minimal" && "$MODE" != "full" ]]; then
  echo "--mode must be minimal or full" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$PID_DIR"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  kill -0 "$pid" 2>/dev/null
}

start_component() {
  local name="$1"
  local command="$2"
  local pid_file="${PID_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"

  if is_running "$pid_file"; then
    echo "[skip] ${name} already running (pid $(cat "$pid_file"))"
    return
  fi

  nohup bash -lc "$command" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[start] ${name} -> pid $(cat "$pid_file"), log ${log_file}"
}

topic_exists() {
  local topic="$1"
  bash -lc "source /opt/ros/noetic/setup.bash && rostopic list 2>/dev/null | grep -Fx '${topic}' >/dev/null"
}

node_exists() {
  local node_name="$1"
  bash -lc "source /opt/ros/noetic/setup.bash && rosnode list 2>/dev/null | grep -Fx '${node_name}' >/dev/null"
}

if ! bash -lc "source /opt/ros/noetic/setup.bash && rosnode list >/dev/null 2>&1"; then
  start_component "roscore" "source /opt/ros/noetic/setup.bash && roscore"
  sleep 3
else
  echo "[skip] roscore already available"
fi

if topic_exists "/navigation_marker"; then
  echo "[skip] navigation base appears active via /navigation_marker"
else
  start_component \
    "navigation_base" \
    "source /opt/ros/noetic/setup.bash && source \$HOME/rmc_dual_arm_robot/devel/setup.bash && roslaunch rm_dual_arm_agv agv_start.launch"
fi

if topic_exists "/camera/color/image_raw"; then
  echo "[skip] head camera appears active via /camera/color/image_raw"
else
  start_component \
    "camera_head" \
    "source /opt/ros/noetic/setup.bash && source \$HOME/rmc_dual_arm_robot/devel/setup.bash && roslaunch rm_dual_arm_camera rm_dual_arm_camera_single.launch"
fi

if topic_exists "/l_arm/rm_driver/Plan_State"; then
  echo "[skip] arm driver appears active via /l_arm/rm_driver/Plan_State"
else
  start_component \
    "arm_driver" \
    "source /opt/ros/noetic/setup.bash && source \$HOME/lt_grasp_ws/devel/setup.bash && bash ${ROOT_DIR}/vision_grasp/bringup/start_hand_driver.sh ${ARM_TYPE} ${ARM_DOF} ${END_EFFECTOR}"
fi

if node_exists "/robot_state_publisher"; then
  echo "[skip] robot_state_publisher already active"
else
  start_component \
    "robot_description" \
    "source /opt/ros/noetic/setup.bash && source \$HOME/rmc_dual_arm_robot/devel/setup.bash && xacro \$(rospack find robot_description)/urdf/robots/embodied_dual_arms.urdf.xacro arm_type:=rm65 end_effector:=rmg24 > /tmp/long_tasks_robot_description.urdf && rosparam set /robot_description -t /tmp/long_tasks_robot_description.urdf && rosrun robot_state_publisher robot_state_publisher"
fi

if node_exists "/base_left_to_base_left_trans"; then
  echo "[skip] robot TF tree already active"
else
  start_component \
    "robot_tftree" \
    "source /opt/ros/noetic/setup.bash && source \$HOME/rmc_dual_arm_robot/devel/setup.bash && roslaunch rm_dual_arm_tftree rm_dual_arm_tftree.launch display:=false arm_type:=RM65"
fi

if [[ "$MODE" = "full" ]]; then
  if topic_exists "/navigation_feedback"; then
    echo "[skip] AGV socket bridge appears active via /navigation_feedback"
  else
    start_component \
      "agv_socket_bridge" \
      "source /opt/ros/noetic/setup.bash && source \$HOME/rmc_dual_arm_robot/devel/setup.bash && /usr/bin/python3 ${ROOT_DIR}/navigation/ros_bridge/agv_socket_bridge.py"
  fi
fi

cat <<EOF

Long Tasks bringup complete.
Mode: ${MODE}

Logs:
  ${LOG_DIR}

Stop all:
  bash ${ROOT_DIR}/scripts/bringup_stop.sh

Check system:
  bash ${ROOT_DIR}/scripts/check_system.sh
EOF
