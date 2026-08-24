from __future__ import annotations

from typing import Any, Protocol, Sequence

from .contracts import SkillContract
from .models import FailureReport, MissionPlan, PlanStep
from .semantic_validator import SemanticPlanValidator
from .state import WorldState


class ReplanError(ValueError):
    pass


class Replanner(Protocol):
    def replan(
        self,
        *,
        original_plan: MissionPlan,
        committed_steps: Sequence[PlanStep],
        remaining_steps: Sequence[PlanStep],
        state: WorldState,
        failure: FailureReport,
        contracts: dict[str, SkillContract],
    ) -> MissionPlan | None:
        raise NotImplementedError


class NoOpReplanner:
    def replan(
        self,
        *,
        original_plan: MissionPlan,
        committed_steps: Sequence[PlanStep],
        remaining_steps: Sequence[PlanStep],
        state: WorldState,
        failure: FailureReport,
        contracts: dict[str, SkillContract],
    ) -> MissionPlan | None:
        del original_plan, committed_steps, remaining_steps, state, failure, contracts
        return None


class QwenReplanner:
    def __init__(self, client: Any) -> None:
        self.client = client

    def replan(
        self,
        *,
        original_plan: MissionPlan,
        committed_steps: Sequence[PlanStep],
        remaining_steps: Sequence[PlanStep],
        state: WorldState,
        failure: FailureReport,
        contracts: dict[str, SkillContract],
    ) -> MissionPlan | None:
        context = build_replan_context(
            original_plan,
            state,
            committed_steps,
            remaining_steps,
            failure,
            contracts,
        )
        payload = self.client.replan_remaining(context)
        if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
            raise ReplanError("replanner must return an object with a steps array")
        return apply_repaired_suffix(
            original=original_plan,
            committed_steps=committed_steps,
            returned_steps=payload["steps"],
            state=state,
            contracts=contracts,
        )


def build_replan_context(
    original_plan: MissionPlan,
    state: WorldState,
    committed_steps: Sequence[PlanStep],
    remaining_steps: Sequence[PlanStep],
    failure: FailureReport,
    contracts: dict[str, SkillContract],
) -> dict[str, Any]:
    return {
        "goal": original_plan.goal,
        "verified_world_state": state.snapshot(),
        "committed_steps": [step.to_dict() for step in committed_steps],
        "remaining_plan": [step.to_dict() for step in remaining_steps],
        "failure": failure.to_dict(),
        "available_skills": [
            {
                "name": contract.name,
                "required_args": list(contract.required_args),
                "requires": sorted(contract.required_facts({name: f"<{name}>" for name in contract.required_args})),
                "verifier": contract.verifier,
            }
            for contract in sorted(contracts.values(), key=lambda value: value.name)
        ],
    }


def apply_repaired_suffix(
    *,
    original: MissionPlan,
    committed_steps: Sequence[PlanStep],
    returned_steps: list[dict[str, Any]],
    state: WorldState,
    contracts: dict[str, SkillContract],
) -> MissionPlan:
    committed_ids = {step.id for step in committed_steps}
    parsed_steps: list[PlanStep] = []
    for payload in returned_steps:
        step = PlanStep.from_dict(payload)
        if step.id in committed_ids:
            raise ReplanError(f"repaired suffix reuses committed step id: {step.id}")
        dependencies = tuple(dep for dep in step.depends_on if dep not in committed_ids)
        parsed_steps.append(
            PlanStep(id=step.id, skill=step.skill, args=step.args, depends_on=dependencies)
        )
    if not parsed_steps:
        raise ReplanError("repaired suffix must contain at least one step")
    repaired = MissionPlan(
        plan_id=original.plan_id,
        version=original.version + 1,
        parent_version=original.version,
        goal=dict(original.goal),
        steps=tuple(parsed_steps),
    )
    errors = SemanticPlanValidator(contracts).validate(repaired, set(state.facts))
    if errors:
        raise ReplanError("invalid repaired suffix: " + "; ".join(errors))
    return repaired
