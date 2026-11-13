# Audit and migration record

Date: 2026-11-13 (Asia/Shanghai).
Target: [Long_sequence_tasks_for_realmanrobot](https://github.com/fanjiahui-charix/Long_sequence_tasks_for_realmanrobot).

## Provenance

Original local HEAD cf97bbf80e98a45f3b778875119c26640661ee16 was 17 commits behind target GitHub HEAD 5280a21d4c7246dacc097895753db13626b9888f. A sibling Long_sequence_tasks_react checkout was created at the target SHA on feature/react-memory-agent. The original directory was left untouched.

A 302-file original source snapshot and a 282-file upstream file/import/symbol inventory were saved privately outside the repository. Credentials were excluded. The upstream 52 legacy unit tests passed before old-agent deletion; this is not a one-shot real-model task-success baseline.

## Capability review

| Capability | Sources reviewed | New integration |
|---|---|---|
| Navigation | chassis_client, direct API, ROS bridges and AGV driver | Existing client, independent arrival decoder |
| RGB-D | camera capture helpers and ROS image capture | Existing ROS interpreter worker |
| Segmentation | YOLO-seg capture/train/inference modules and configs | Existing segmentation CLI and mask metadata |
| FoundationPose | Integration runners/pose bridge, model inventory and environment manifests | Independent existing inference environment |
| Transform | pose_grasp.py and foundationpose_bridge.py | Existing TF conversion in read-only ROS worker |
| Grasp / gripper | Pose sequence, arm/end-effector clients, drivers/messages | Existing sequence with independent measured-state verification |
| Width | Bundled command clients plus old vendor reference | Command echoes rejected; generic actual-state port required |
| Qwen | Old qwen_client and ignored local configuration | Same compatible-mode transport, new prompts/Pydantic schemas |

The inventory covers all upstream files. Focused dependency/call review covered the above capability and environment boundaries. Third-party model algorithms were retained, not independently requalified.

## Removal and preservation

Removed 49 tracked planner files: one-shot planner/prompt/schema; AgentRuntime, state/contracts/replanner/recovery/executor/verifiers; old agent skills/mock backend; examples, tests and obsolete docs/configs. There is no new import of that execution logic. Git history preserves traceability.

Reusable robot configuration moved unchanged to config/robot: nav_targets.yaml, grasp.yaml and lab_scene_template.yaml. Navigation CLI's default map path was migrated. The old table labels are not automatically equated with new mission A/B labels.

Local modified right-arm grasp YAMLs, bringup/check scripts and FoundationPose integration README were preserved byte for byte. Original mesh/texture and optional low-level demo/pose visualizer were also retained. Local untracked mesh/texture remain gitignored deployment assets; they are kept in the working directory and original private snapshot, outside the public source patch. The migrated scene-template YAML only normalizes its trailing blank line. These remain original inputs rather than new calibration claims.

Upstream FoundationPose README.md/readme.md collided on Windows. The official lowercase document is retained as UPSTREAM_README.md; the local integration README stays README.md. Model source, vendor notices and environment definitions remain intact.

The upstream-tracked vision_grasp/demo/weights/best.pt (6,266,659 bytes) was removed from tracking while its local file was retained. Weights stay outside public source/evidence archives. The review patch records this deletion as metadata without embedding the old binary weight payload; Git history remains unchanged.

## Findings

- End-effector return values are commands. gripper_joint is derived from requested position, and its JointState assignment is commented. It is not actual opening.
- The complete local WATER v1.1 manual pp.15–16 defines succeeded as movement completion; idle means no command since service startup. running_status=idle also follows failures/cancel. The new decoder requires current target/pose checks and positive external localization evidence.
- WATER robot_status contains no positive localization-valid field; none was fabricated. The old vendor hand UDP contract likewise is not assumed to be installed.
- The ignored original .env supplied the existing Qwen credentials. qwen-vl-plus returned 404; the account model list included qwen3-vl-plus, which passed a JSON request and the full image-input Mock mission. Only the new private copy's model selection changed.

Protocol references: [Qwen compatible API](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope), [Qwen structured output](https://help.aliyun.com/en/model-studio/qwen-structured-output). Windows worker ownership follows [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects). Local Pydantic/evidence validation remains mandatory.

Implementation and local acceptance performed no real robot motion, ROS/CUDA upgrade or parameter recalibration. The maintainer subsequently authorized repository publication and updating main to this version. Publication preserves the old baseline under archive/pre-react-memory-agent-20261113 and advances main through the existing history. See EVALUATION.md for actual tests and evaluation limits.

## Demonstration media

The user-provided 51.39-second platform video is retained unchanged as docs/media/project-demo.mp4. A 3× looping GIF is embedded in both root READMEs. Its recording version has not been tied to the refactored Agent, so the caption identifies it as existing platform footage and points to the separately documented API-level evaluation.

## Publication compatibility check

The first feature-branch CI run exposed a Python 3.10.11 cancellation race, reproduced in an isolated local interpreter before fixing it. The deadline boundary now explicitly preserves outer cancellation, including when the inner task has just completed; see [CPython issue 86296](https://github.com/python/cpython/issues/86296). Timeout cleanup latches physical uncertainty before awaiting stop, and invalid backend results become structured unknown/rejection states. Event-synchronized regressions cover each boundary. Both Python 3.10.11 and 3.13.9 pass 59 tests locally; the current remote matrix remains visible in the repository's Actions page.
