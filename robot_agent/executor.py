from __future__ import annotations

import asyncio
import time

from .deadlines import wait_with_deadline
from .schemas import Observation, SkillReply, ToolResult, Verification
from .tool_registry import ToolRejected


class ToolExecutor:
    def __init__(self, registry):
        self.registry = registry

    async def observe(self, mission):
        try:
            return Observation.model_validate(
                await wait_with_deadline(
                    self.registry.backend.observe_robot_state(mission),
                    self.registry.timeouts["observe_robot_state"],
                )
            )
        except Exception as exc:
            return Observation(source="observation_error", notes=[type(exc).__name__])

    async def _cancel_unknown(self, name, state, dispatched, *, attempt_stop=True):
        if dispatched and name in {"navigate_to", "grasp_object"}:
            state.uncertain_action = name
            state.uncertain_since = time.time()
            state.grasp_state = "UNKNOWN"
            state.current_location = None
            state.last_error = "MISSION_CANCELLED"
            if attempt_stop:
                try:
                    await asyncio.shield(
                        wait_with_deadline(
                            self.registry.backend.cancel_current_action(), 2.0
                        )
                    )
                except (Exception, asyncio.CancelledError):
                    pass
        state.current_action = None

    async def execute(self, decision, state):
        name = decision.tool_name
        started = time.time()
        tick = time.perf_counter()
        dispatched = False
        carrying = (
            state.grasped_object == state.mission.object_category
            and state.grasp_state == "HELD"
        )
        reply = SkillReply(status="UNKNOWN", error_code="TOOL_EXECUTION_UNKNOWN")
        observation = None
        try:
            # A model call can outlive the observation TTL. Refresh telemetry at
            # the execution boundary; a cached pose still keeps its original age.
            state.ingest(
                await self.observe(state.mission),
                self.registry.verifier,
                now=time.time(),
            )
            args = self.registry.validate(decision, state, now=time.time())
            pose = state.pose
            if name in {"navigate_to", "grasp_object"}:
                state.invalidate_for_motion(name)
            if name == "locate_object":
                state.pose = None
            dispatched = True
            if name == "observe_robot_state":
                observation = await self.observe(state.mission)
                reply = SkillReply()
            else:
                reply = await wait_with_deadline(
                    self.registry.invoke(name, args, state, pose=pose),
                    self.registry.timeouts[name],
                )
                reply = SkillReply.model_validate(reply)
        except ToolRejected as exc:
            reply = SkillReply(status="FAILED", error_code=exc.code)
        except asyncio.CancelledError:
            await self._cancel_unknown(name, state, dispatched)
            raise
        except asyncio.TimeoutError:
            reply = SkillReply(status="TIMEOUT", error_code="TOOL_TIMEOUT")
            if dispatched and name in {"navigate_to", "grasp_object"}:
                # Stop itself is awaitable and may be interrupted. Latch before
                # cleanup, so every exit path preserves physical uncertainty.
                state.uncertain_action = name
                state.uncertain_since = time.time()
                state.last_error = "TOOL_TIMEOUT"
            try:
                await wait_with_deadline(
                    self.registry.backend.cancel_current_action(), 2.0
                )
            except asyncio.CancelledError:
                await self._cancel_unknown(name, state, dispatched, attempt_stop=False)
                raise
            except Exception:
                pass  # Cancellation acknowledgement never clears the physical interlock.
        except Exception as exc:
            reply = SkillReply(
                status="UNKNOWN",
                error_code="TOOL_EXECUTION_UNKNOWN",
                result={"exception_type": type(exc).__name__},
            )
        if observation is None:
            try:
                observation = await self.observe(state.mission)
            except asyncio.CancelledError:
                await self._cancel_unknown(name, state, dispatched)
                raise
        if reply.observation is not None:
            # Only perception fields may be carried from a tool reply. Physical
            # telemetry is collected independently, not copied from success flags.
            percept = reply.observation
            observation = observation.model_copy(
                update={
                    "object_category": percept.object_category,
                    "object_detected": percept.object_detected,
                    "mask_valid": percept.mask_valid,
                    "pose": percept.pose,
                    "raw_result_reference": percept.raw_result_reference,
                    "notes": observation.notes + percept.notes,
                }
            )
        now = time.time()
        v = self.registry.verifier
        if name == "navigate_to":
            check = v.navigation(
                observation, target=decision.arguments.get("target", ""), now=now
            )
            if carrying and check.verified:
                held = v.grasp(observation, now=now)
                if held.grasp_state != "HELD":
                    check = Verification(
                        error_code="OBJECT_LOST_DURING_NAVIGATION"
                        if held.grasp_state == "NOT_HELD"
                        else "GRIPPER_FEEDBACK_UNAVAILABLE",
                        grasp_state=held.grasp_state,
                        evidence={"arrived": True, "carry": held.evidence},
                    )
        elif name == "locate_object":
            check = v.perception(
                observation,
                now=now,
                location=state.mission.source_location
                if state.current_location == state.mission.source_location
                else None,
                motion_epoch=state.motion_epoch,
                object_category=state.mission.object_category,
            )
        elif name == "grasp_object":
            check = v.grasp(observation, now=now)
            if check.grasp_state != "HELD":
                check = Verification(
                    error_code="GRASP_NOT_HELD"
                    if check.grasp_state == "NOT_HELD"
                    else check.error_code,
                    grasp_state=check.grasp_state,
                    evidence=check.evidence,
                )
        else:
            fresh = v.fresh(observation.timestamp, now)
            available = (
                observation.arm_idle is not None
                or observation.localization_confirmed is not None
                or bool(observation.gripper_samples)
            )
            check = Verification(
                verified=fresh and available,
                error_code=None if fresh and available else "STATE_UNAVAILABLE",
                evidence={"observation_source": observation.source},
            )
        status = reply.status
        error = reply.error_code
        if status == "SUCCEEDED" and not check.verified:
            status = "FAILED"
            error = check.error_code
        elif status != "SUCCEEDED":
            check = Verification(
                error_code=error or check.error_code,
                grasp_state=check.grasp_state,
                evidence=check.evidence,
            )
        uncertain = (
            dispatched
            and name in {"navigate_to", "grasp_object"}
            and (
                reply.status in {"TIMEOUT", "UNKNOWN"}
                or observation.motion_settled is not True
                or observation.arm_idle is not True
            )
        )
        result = ToolResult(
            tool_name=name,
            status=status,
            arguments=decision.arguments,
            result=reply.result,
            error_code=error,
            started_at=started,
            finished_at=now,
            duration_sec=time.perf_counter() - tick,
            observation=observation,
            verification=check,
            dispatched=dispatched,
            execution_uncertain=uncertain,
            carry_required=carrying and name == "navigate_to",
        )
        state.apply(result, v, now=now)
        return result
