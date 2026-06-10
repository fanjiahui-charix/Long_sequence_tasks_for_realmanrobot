#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/scripts/env/source_all.sh"

echo "== ROS nodes =="
rosnode list 2>/dev/null || true
echo

echo "== Key topics =="
rostopic list 2>/dev/null | grep -E '^/camera_middle/|^/camera/|^/navigation_|^/l_arm/|^/r_arm/' || true
echo

echo "== TF sanity check =="
/usr/bin/python3 - <<'PY'
import sys
try:
    import rospy
    import tf2_ros
except Exception as exc:
    print(f"TF check skipped: {exc}")
    sys.exit(0)

if not rospy.core.is_initialized():
    rospy.init_node("long_tasks_check_system", anonymous=True, disable_signals=True)

buffer = tf2_ros.Buffer()
listener = tf2_ros.TransformListener(buffer)
rospy.sleep(1.0)

pairs = [
    ("required", "base_left", "camera_middle"),
    ("optional", "base_left", "map"),
]
for level, target, source in pairs:
    try:
        buffer.lookup_transform(target, source, rospy.Time(0), rospy.Duration(1.5))
        print(f"OK: {target} <- {source}")
    except Exception as exc:
        prefix = "MISSING" if level == "required" else "INFO"
        print(f"{prefix}: {target} <- {source}: {exc}")
PY
