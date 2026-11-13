# Hardware adaptation and deployment

No real robot action was executed during this refactor. Qwen API calls and software tests used the Mock backend. The following platform work remains explicit.

| Item | Retained capability | Required integration evidence |
|---|---|---|
| Navigation | Existing marker/status/cancel client | Actual A/B markers, map coordinates/tolerances and current positive localization validity |
| RGB-D | Existing RGB/depth/intrinsics capture | Actual depth scale, alignment, fresh synchronized samples and camera/TF clock agreement |
| Segmentation | Existing YOLO-seg CLI and mask output | Actual trained weights, correct category label and validated confidence policy |
| FoundationPose | Existing independent Conda runner and pose loader | Installed model dependencies, correct mesh scale, quality criteria and measured timing/TTL |
| Transform | Existing camera-to-base TF conversion | Actual frame names and confirmed extrinsics, including capture-time behavior |
| Grasp | Existing home/pregrasp/grasp/close/retreat | Actual arm/end effector, transport posture and confirmed grasp YAML |
| Width | Existing clients publish commands, not actual opening | Measured width reader, units, timestamps, empty/held intervals and stability calibration |
| State / stop | Plan_State is a trajectory result | Independent arm idle/settled source and confirmed stop/cancel port |
| Holding | Core distinguishes HELD/NOT_HELD/UNKNOWN | Carrying/drop tests; width alone cannot independently identify an object |

Old vendor documentation contains gripper readback and UDP hand-status protocols, but this is not proof of the installed firmware or device. Old hand feedback/command angle ranges differ, and force/current comments have inconsistent units. No old register, scale conversion or threshold was automatically inserted into the runtime.

The retained RGB-D capture helper does not export synchronized source header timestamps. This adapter uses capture-start wall time as a conservative age bound and requires timing_confirmed. It does not certify synchronization. TF reuses existing lookup behavior; a moving camera/arm requires a confirmed capture-time transform strategy before hardware qualification.

## Before real execution

- [ ] Confirm actual platform, arm side, end effector and complete grasp configuration. Retained local right-arm changes are not newly certified.
- [ ] Keep ROS Noetic and FoundationPose environments; create a separate Python >=3.10 agent environment.
- [ ] Implement timestamped read-only Observation and independent grasp stop commands.
- [ ] Measure empty/held width, resolution, stability and loss cases; use origin=measured. Synthetic calibration is rejected by real composition.
- [ ] Confirm A/B mapping, measured goal tolerances, positive localization evidence and safe arm posture during transport.
- [ ] Validate depth/mesh scale, extrinsics, source freshness, sensor synchronization and TF timing. Do not substitute example hardware values.
- [ ] Run offline preflight with the confirmed hardware YAML. The supplied example deliberately fails.
- [ ] Start with a human operator, accessible emergency stop and clear workspace; perform read-only state/vision checks first.
- [ ] Explicitly enable motion and qualify navigation, perception and one grasp before the complete mission.
- [ ] Exercise timeout, cancel, feedback loss, dropped object and restart recovery. Process exit does not prove physical stop.
- [ ] Independently verify return-to-A plus actual stable held width before reporting a physical mission completed.

The CLI requires --backend realman --enable-hardware and a passing hardware config. No supplied sample contains calibrated thresholds or can silently enable motion. Low-level utilities remain available to engineers and outside the model tool allowlist.
