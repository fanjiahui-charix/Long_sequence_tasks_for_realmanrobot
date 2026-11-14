from __future__ import annotations

import time
import asyncio

from .executor import ToolExecutor
from .memory.consolidation import ExperienceConsolidator
from .schemas import AgentDecision, Episode, Verification
from .state import WorkingMemory
from .trace import MissionMetrics, MissionReport, TraceRecorder


class ReActAgent:
    def __init__(
        self,
        client,
        registry,
        *,
        memory=None,
        max_turns=30,
        max_failures=3,
        trace_path=None,
        consolidation_timeout_s=30,
        max_consolidations=6,
    ):
        self.client = client
        self.registry = registry
        self.memory = memory
        self.max_turns = max_turns
        self.max_failures = max_failures
        self.trace_path = trace_path
        if consolidation_timeout_s <= 0 or max_consolidations < 0:
            raise ValueError("invalid consolidation bounds")
        self.consolidation_timeout_s = consolidation_timeout_s
        self.max_consolidations = max_consolidations
        self._running = False
        self.state = None
        self.trace = None

    async def run(self, mission):
        if self._running:
            raise RuntimeError("one mission at a time per agent/backend")
        self._running = True
        try:
            return await self._run(mission)
        except asyncio.CancelledError:
            if self.state is not None:
                self.state.mission_status = "REQUEST_HELP"
                self.state.last_error = "MISSION_CANCELLED"
                self.state.current_action = None
                if self.memory:
                    self.memory.record_mission(self.state)
                if self.trace:
                    self.trace.add(
                        "cancelled",
                        uncertain_action=self.state.uncertain_action,
                        state=self.state.context(),
                    )
            raise
        finally:
            self._running = False

    async def _run(self, mission):
        state = WorkingMemory(mission=mission)
        self.state = state
        executor = ToolExecutor(self.registry)
        trace = TraceRecorder(self.trace_path)
        self.trace = trace
        metrics = MissionMetrics()
        started = time.perf_counter()
        final = Verification(error_code="FINAL_GOAL_NOT_VERIFIED")
        pending = []
        seen_failures = set()
        actions = []
        invalid_decisions = 0
        consolidation_attempts = {}
        consolidator = ExperienceConsolidator(
            self.client, timeout_s=self.consolidation_timeout_s
        )

        def retrieve(skill=None, error=None):
            if self.memory is None:
                return []
            tick = time.perf_counter()
            episodes = self.memory.retrieve(
                task_type=mission.task_type,
                object_category=mission.object_category,
                skill=skill,
                failure_type=error,
            )
            metrics.memory_retrieval_sec += time.perf_counter() - tick
            metrics.episodes_retrieved += len(episodes)
            # No historical pose, raw instructions or physical facts enter the prompt.
            context = [
                {
                    "episode_id": e.episode_id,
                    "executed_skill": e.executed_skill,
                    "failure_type": e.failure_type,
                    "recovery_strategy": e.recovery_strategy,
                    "verified": e.verified,
                    "experience": e.experience.model_dump(mode="json"),
                }
                for e in episodes
            ]
            trace.add(
                "memory_retrieval",
                skill=skill,
                failure_type=error,
                episode_ids=[e.episode_id for e in episodes],
            )
            return context

        episodes = retrieve()
        state.ingest(
            await executor.observe(mission), self.registry.verifier, now=time.time()
        )
        trace.add(
            "initial_observation",
            observation=state.last_observation.model_dump(mode="json"),
        )

        def account_request(tick, requests_before, *, consolidation=False):
            latency = time.perf_counter() - tick
            if consolidation:
                metrics.consolidation_latency_sec.append(latency)
            else:
                metrics.decision_latency_sec.append(latency)
            if getattr(self.client, "is_real_llm", True):
                calls = (
                    max(0, self.client.request_count - requests_before)
                    if requests_before is not None
                    else 1
                )
                metrics.llm_calls += calls
                if consolidation:
                    metrics.consolidation_llm_calls += calls
                if calls:
                    recorded = getattr(self.client, "latencies", [])
                    metrics.llm_latency_sec.extend(
                        recorded[-calls:] if recorded else [latency]
                    )
            return latency

        async def consolidate_episode(episode):
            if (
                self.memory is None
                or episode.experience_status == "READY"
                or consolidation_attempts.get(episode.episode_id, 0) >= 2
                or metrics.consolidation_calls >= self.max_consolidations
            ):
                return False
            consolidation_attempts[episode.episode_id] = (
                consolidation_attempts.get(episode.episode_id, 0) + 1
            )
            metrics.consolidation_calls += 1
            tick = time.perf_counter()
            requests_before = getattr(self.client, "request_count", None)
            try:
                experience = await consolidator.summarize(episode)
                provider = (
                    getattr(getattr(self.client, "config", None), "provider", "llm")
                    if getattr(self.client, "is_real_llm", True)
                    else "scripted"
                )
                self.memory.save_experience(
                    episode.episode_id, experience, provider=provider
                )
                metrics.experiences_created += 1
                trace.add(
                    "experience_consolidated",
                    episode_id=episode.episode_id,
                    recovery_verified=episode.verified,
                    provider=provider,
                    experience=experience.model_dump(mode="json"),
                )
            except Exception as exc:
                # Summary failures never invent experience or substitute for robot evidence.
                error_code = "SUMMARY_" + type(exc).__name__.upper()
                self.memory.fail_experience(episode.episode_id, error_code)
                metrics.consolidation_failures += 1
                trace.add(
                    "experience_consolidation_failed",
                    episode_id=episode.episode_id,
                    error_code=error_code,
                )
            finally:
                account_request(tick, requests_before, consolidation=True)
            # Model latency cannot keep previous physical claims fresh.
            state.ingest(
                await executor.observe(mission), self.registry.verifier, now=time.time()
            )
            return True

        for _ in range(self.max_turns):
            context = {
                "mission": mission.model_dump(mode="json"),
                "working_memory": state.context(),
                "episodic_memory": episodes,
                "tools": self.registry.describe(),
            }
            tick = time.perf_counter()
            requests_before = getattr(self.client, "request_count", None)
            metrics.decision_calls += 1
            try:
                decision = await self.client.decide(context)
                decision = AgentDecision.model_validate(decision)
            except Exception as exc:
                account_request(tick, requests_before)
                invalid_decisions += 1
                state.last_error = "INVALID_DECISION"
                trace.add("decision_error", error_type=type(exc).__name__)
                if invalid_decisions >= 2:
                    state.mission_status = "REQUEST_HELP"
                    break
                continue
            latency = account_request(tick, requests_before)
            state.begin(decision)
            trace.add(
                "decision",
                decision=decision.model_dump(mode="json"),
                latency_sec=latency,
                injected_episode_ids=[e["episode_id"] for e in episodes],
            )
            if decision.action_type in {"ABORT", "REQUEST_HELP"}:
                state.mission_status = (
                    "ABORTED" if decision.action_type == "ABORT" else "REQUEST_HELP"
                )
                state.current_action = None
                break
            if decision.action_type == "FINISH":
                # Always perform a new independent read, even if the previous turn looked successful.
                state.ingest(
                    await executor.observe(mission),
                    self.registry.verifier,
                    now=time.time(),
                )
                final = self.registry.verifier.final_goal(state, now=time.time())
                trace.add("final_verification", result=final.model_dump(mode="json"))
                state.current_action = None
                if final.verified:
                    state.mission_status = "COMPLETED"
                    break
                metrics.finish_rejections += 1
                state.last_error = "FINAL_GOAL_NOT_VERIFIED"
                if metrics.finish_rejections >= 3:
                    state.mission_status = "REQUEST_HELP"
                    break
                continue
            result = await executor.execute(decision, state)
            actions.append(result.tool_name)
            metrics.tool_execution_sec += result.duration_sec
            trace.add("tool", result=result.model_dump(mode="json"))
            if self.memory:
                self.memory.record_skill(mission.mission_id, result)
                self.memory.record_mission(state)
            if result.status == "SUCCEEDED" and result.verification.verified:
                resolved = []
                recovered_episodes = []
                recovery_now = time.time()
                # Commit all matches from this one verified result before any model wait
                # refreshes the physical state. Later observations are separate evidence.
                for item in pending:
                    carry_ok = not item["carry_required"] or (
                        state.grasp_state == "HELD"
                        and state.grasped_object == mission.object_category
                    )
                    same = (
                        item["skill"] == result.tool_name
                        and (
                            result.tool_name != "navigate_to"
                            or result.arguments.get("target") == item["target"]
                        )
                        and carry_ok
                    )
                    reconciled_grasp = (
                        item["skill"] == "grasp_object"
                        and result.tool_name == "observe_robot_state"
                        and state.grasped_object == mission.object_category
                        and state.grasp_state == "HELD"
                        and state.uncertain_action is None
                    )
                    reconciled_nav = (
                        item["skill"] == "navigate_to"
                        and result.tool_name == "observe_robot_state"
                        and state.uncertain_action is None
                        and carry_ok
                        and self.registry.verifier.navigation(
                            result.observation, target=item["target"], now=recovery_now
                        ).verified
                    )
                    if same or reconciled_grasp or reconciled_nav:
                        strategy = actions[item["action_index"] :]
                        evidence = result.verification.evidence | {
                            "grasp_state": state.grasp_state,
                            "location": state.current_location,
                        }
                        if self.memory:
                            recovered_episode = self.memory.mark_recovered(
                                item["episode_id"], strategy, evidence
                            )
                        metrics.recoveries += 1
                        trace.add(
                            "recovery_verified",
                            failed_skill=item["skill"],
                            failure_type=item["error"],
                            strategy=strategy,
                        )
                        if self.memory:
                            recovered_episodes.append(recovered_episode)
                        resolved.append(item)
                for item in resolved:
                    pending.remove(item)
                for episode in recovered_episodes:
                    await consolidate_episode(episode)
                if self.memory or not pending:
                    episodes = retrieve()
            else:
                metrics.failures += 1
                failure_key = (result.tool_name, result.error_code)
                if failure_key in seen_failures:
                    metrics.repeated_failures += 1
                seen_failures.add(failure_key)
                episode = Episode(
                    mission_id=mission.mission_id,
                    object_category=mission.object_category,
                    executed_skill=result.tool_name,
                    failure_type=result.error_code,
                    failure_observation=result.observation.model_dump(mode="json"),
                )
                if self.memory:
                    self.memory.save(episode)
                pending.append(
                    {
                        "episode_id": episode.episode_id,
                        "skill": result.tool_name,
                        "error": result.error_code,
                        "action_index": len(actions),
                        "target": result.arguments.get("target"),
                        "carry_required": result.carry_required,
                    }
                )
                episodes = retrieve(result.tool_name, result.error_code)
                if (
                    state.retry_counts.get(
                        result.tool_name
                        + ":"
                        + (result.error_code or "TOOL_EXECUTION_UNKNOWN"),
                        0,
                    )
                    >= self.max_failures
                ):
                    state.last_error = "MAX_RETRIES_EXCEEDED"
                    state.mission_status = "REQUEST_HELP"
                    break
        if state.mission_status == "RUNNING":
            state.mission_status = "REQUEST_HELP"
            state.last_error = "MAX_TURNS_EXCEEDED"
        state.current_action = None
        state.updated_at = time.time()
        if self.memory:
            terminal_summary_attempted = False
            for episode in self.memory.pending_experiences(mission.mission_id):
                terminal_summary_attempted = (
                    await consolidate_episode(episode) or terminal_summary_attempted
                )
            if terminal_summary_attempted and state.mission_status == "COMPLETED":
                state.ingest(
                    await executor.observe(mission),
                    self.registry.verifier,
                    now=time.time(),
                )
                final = self.registry.verifier.final_goal(state, now=time.time())
                trace.add(
                    "final_verification_after_consolidation",
                    result=final.model_dump(mode="json"),
                )
                if not final.verified:
                    state.mission_status = "REQUEST_HELP"
                    state.last_error = "FINAL_GOAL_NOT_VERIFIED"
            self.memory.record_mission(
                state, verified=state.mission_status == "COMPLETED" and final.verified
            )
        metrics.total_execution_sec = time.perf_counter() - started
        trace.add(
            "terminal",
            status=state.mission_status,
            metrics=metrics.model_dump(mode="json"),
        )
        return MissionReport(
            status=state.mission_status,
            state=state,
            final_verification=final,
            metrics=metrics,
            trace=trace.events,
            evaluation="Mock/API-level Evaluation"
            if not getattr(self.client, "is_real_llm", True)
            else "LLM + backend API-level Evaluation",
        )
