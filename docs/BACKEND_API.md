# Platform-neutral robot integration

Implement robot_agent.backends.base.RobotBackend. The core depends on this protocol rather than a private SDK, device register or ROS distribution. See examples/custom_backend.py.

| Async method | Contract |
|---|---|
| navigate_to(target, mission) | Complete using operator-owned marker mapping; ACK is insufficient |
| locate_object(category, mission, motion_epoch=...) | Fresh RGB-D/mask/6D pose/base transform; return a PoseReference |
| grasp_object(pose, mission) | Pregrasp/grasp/close/retreat, followed by independent measured feedback |
| observe_robot_state(mission) | Current timestamped Observation, independent from target commands |
| cancel_current_action() | Attempt platform stop; only later feedback proves settled state |

Observation carries source/timestamp, optional current location and positive localization validity, navigation status, arm_idle, motion_settled, retreat_complete, and measured width samples. Each WidthSample carries its own timestamp, width_mm, measured flag, source and post-retreat flag. Unsupported fields remain None/UNKNOWN; unavailable width uses an empty list.

Convert physical readback through your platform's confirmed calibration. Never echo a requested opening, infer jaw width from an uncalibrated commanded finger angle, or reuse old sensor values with a new timestamp. HELD requires enough distinct fresh stable samples in the measured held interval after retreat. Empty calibrated width establishes NOT_HELD. All other cases are UNKNOWN.

JsonStateReader optionally runs an operator-owned read-only bridge command. Stdout must contain exactly one Observation JSON object with an explicit timestamp; diagnostics go to stderr. This command is deployment configuration, never a model tool argument. The separate grasp stop command attempts cancellation without asserting that physical motion stopped.

The optional RealMan implementation composes retained ChassisNavigationClient, ROS RGB-D capture, YOLO-seg, FoundationPose, TF and execute_pose_grasp_from_config. Other platforms implement the same port directly.

WATER status verification requires succeeded, a matching marker, current pose within explicit tolerances and independent positive localization validity. status=OK and running_status=idle alone are insufficient. No localization-valid field is invented in the documented status response.

The vision adapter preserves capture-start age and caches opaque references. The grasp adapter verifies the camera-pose and grasp-config hashes; a model cannot choose an arbitrary file or calibration. Source sensor/TF synchronization still requires hardware qualification.

All adapters remain subject to the same core verifier. A missing platform capability must reject or return UNKNOWN, never synthesize success.
