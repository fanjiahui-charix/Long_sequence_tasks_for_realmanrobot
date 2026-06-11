#!/usr/bin/env bash
set -euo pipefail

unset PYTHONPATH
export PYTHONNOUSERSITE=1

exec /home/rm/miniforge3/envs/foundationpose/bin/python \
  /home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.py \
  "$@"
