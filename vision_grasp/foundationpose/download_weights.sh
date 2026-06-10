#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/weights"
mkdir -p "${OUT_DIR}"

: "${GDOWN:=/home/rm/miniforge3/envs/foundationpose/bin/gdown}"

"${GDOWN}" --folder 'https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i?usp=sharing' -O "${OUT_DIR}"
"${GDOWN}" --folder 'https://drive.google.com/drive/folders/1pRyFmxYXmAnpku7nGRioZaKrVJtIsroP?usp=sharing' -O "${ROOT}/demo_data"
