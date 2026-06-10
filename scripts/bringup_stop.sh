#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="${ROOT_DIR}/.run/bringup/pids"

if [ ! -d "$PID_DIR" ]; then
  echo "No bringup pid directory found: $PID_DIR"
  exit 0
fi

for pid_file in "$PID_DIR"/*.pid; do
  [ -e "$pid_file" ] || continue
  name="$(basename "$pid_file" .pid)"
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "[stop] ${name} (pid ${pid})"
  else
    echo "[skip] ${name} already stopped"
  fi
  rm -f "$pid_file"
done
