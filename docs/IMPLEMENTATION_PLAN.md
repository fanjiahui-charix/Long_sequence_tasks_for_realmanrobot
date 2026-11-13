# ReAct + Memory implementation plan

Goal: replace planner/ entirely with a small, independently executable agent.
Architecture: one typed decision per turn; four high-level tools; measurements pass deterministic verification before becoming facts. RobotBackend is a platform-neutral port; existing RealMan code is an optional adapter. Qwen is the preferred real provider; no credentials are required for mock evaluation.
Stack: Python >=3.10, Pydantic 2, SQLite, stdlib HTTP/asyncio; ROS Noetic and FoundationPose remain in their existing interpreters.

- [x] Contracts / evidence verifier: write tests rejecting low-level parameters, unmeasured width, missing calibration, stale/wrong-frame pose and stale final evidence; run them red; implement schemas.py, verifier.py, state.py and rerun.
- [x] Memory: test SQLite persistence/filtering and unverified episode exclusion; implement memory/episodic.py with bound SQL values and verified recovery promotion.
- [x] Tools / loop: test A→B→A, faults, timeout interlocks, premature FINISH and bounded retries; implement tool_registry.py, executor.py, agent.py and backends/mock_robot.py. Run python -m pytest tests -q.
- [x] Model / mission: test HTTP payloads, structured JSON, bad outputs, image forwarding and trusted location mapping; implement llm_adapter.py and mission.py with Qwen compatible-mode transport and explicit Ollama option.
- [x] Hardware ports: test ACK != arrival, process cancellation, capture timestamp preservation, trusted pose lookup and disabled hardware; implement isolated adapters around navigation/ and vision_grasp/, using no guessed state fields or calibration.
- [x] Demo / experiments: run python -m robot_agent demo and python -m robot_agent evaluate; use the same scripted policy and fault suite in A/B, with real SQLite retrieval in B. Label results Mock/API-level Evaluation and never infer physical performance.
- [x] Cleanup: migrate reusable configuration out of planner/configs; remove planner code/prompts/tests; retain navigation, vision, drivers, object models, calibration and launch scripts. Check import inventory and original hashes.
- [x] Delivery: update README, SYSTEM_DESIGN, AUDIT, HARDWARE_VALIDATION and EVALUATION; review full diff, tests and package outputs. No push, merge or real robot motion.

Verification examples:
```python
assert verifier.grasp(observation_without_measured_width).grasp_state == "UNKNOWN"
assert not verifier.final_goal(state_without_return).verified
assert store.retrieve(skill="grasp_object", failure_type="POSE_STALE", object_category="glasses_case") == []
```

Baseline: upstream 5280a21d4c7246dacc097895753db13626b9888f, 52 legacy unit tests passed before deletion. Original local cf97bbf80e98a45f3b778875119c26640661ee16 was 17 commits behind. No one-shot real-model baseline is claimed.

Publication follow-up: after local acceptance, the maintainer authorized pushing the feature branch and updating main. Keep the baseline in the archive/pre-react-memory-agent-20261113 tag and advance main without rewriting existing history.
