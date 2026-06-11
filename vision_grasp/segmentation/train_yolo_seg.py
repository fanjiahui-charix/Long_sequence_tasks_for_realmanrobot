#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a custom Ultralytics YOLO-seg model for visual grasping.")
    parser.add_argument("--data", required=True, help="Path to dataset YAML.")
    parser.add_argument("--model", default="yolov8n-seg.pt", help="Starting YOLO-seg weight or model name.")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0", help="0 for CUDA, cpu for CPU.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--name", default="glasses_case_box_seg")
    parser.add_argument("--project", default=None, help="Output root. Defaults to vision_grasp/weights/yolo_seg_runs.")
    parser.add_argument("--save-period", type=int, default=-1)
    parser.add_argument("--cache", action="store_true", help="Enable Ultralytics dataset cache.")
    parser.add_argument("--resume", action="store_true", help="Resume the latest run with the same name/project.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    script_dir = Path(__file__).resolve().parent
    project_dir = Path(args.project).expanduser() if args.project else (script_dir.parent / "weights" / "yolo_seg_runs")
    project_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    run_args = {
        "data": str(Path(args.data).expanduser()),
        "epochs": int(args.epochs),
        "imgsz": int(args.imgsz),
        "batch": int(args.batch),
        "device": args.device,
        "workers": int(args.workers),
        "patience": int(args.patience),
        "project": str(project_dir),
        "name": args.name,
        "save_period": int(args.save_period),
        "cache": bool(args.cache),
        "resume": bool(args.resume),
    }
    model.train(**run_args)

    summary = {
        "data": run_args["data"],
        "model": args.model,
        "project": str(project_dir),
        "name": args.name,
        "expected_run_dir": str(project_dir / args.name),
        "expected_best_weight": str(project_dir / args.name / "weights" / "best.pt"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

