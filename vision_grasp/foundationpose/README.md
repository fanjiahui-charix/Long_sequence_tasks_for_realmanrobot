# FoundationPose Module

Chinese version: `README.zh-CN.md`

This directory contains the internal FoundationPose module used by
`Long_sequence_tasks` for 6D pose estimation.

It is kept inside `vision_grasp/` so the full visual grasping stack can be
published as one repository.

## What This Module Does

- single-frame 6D pose registration
- pose scoring and refinement
- mesh-based rendering support
- optional training and dataset code

## Important Files

- `estimater.py`
  main FoundationPose estimator logic
- `Utils.py`
  geometry and utility functions
- `learning/training/predict_pose_refine.py`
  refine network inference
- `learning/training/predict_score.py`
  score network inference
- `capture_object_rgbd.py`
  current-frame RGB-D capture plus depth-based mask generation
- `run_demo.py`
  original demo entrypoint

## Robot-Specific Notes

This project includes Jetson Xavier NX memory-related inference adjustments:

- safer mesh diameter computation
- chunked refine inference
- chunked score inference
- lower inference batch size for constrained memory

Those changes are used through:

- `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_foundationpose_single.py`
- `/home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py`

## Environment

FoundationPose runs in:

```bash
source /home/rm/miniforge3/bin/activate foundationpose
```

## Weights

Large weights are intentionally not tracked in Git. Put model files under the
expected FoundationPose weight locations before running real inference.
