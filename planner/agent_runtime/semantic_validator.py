from __future__ import annotations

from .contracts import SkillContract
from .models import MissionPlan


class SemanticPlanValidator:
    def __init__(self, contracts: dict[str, SkillContract]) -> None:
        self.contracts = contracts

    def validate(self, plan: MissionPlan, initial_facts: set[str] | None = None) -> list[str]:
        errors: list[str] = []
        facts = set(initial_facts or {"HandEmpty"})
        seen_ids: set[str] = set()

        for step in plan.steps:
            duplicate = step.id in seen_ids
            if duplicate:
                errors.append(f"duplicate step id: {step.id}")

            for dependency in step.depends_on:
                if dependency not in seen_ids:
                    errors.append(f"step {step.id} depends on unknown or later step: {dependency}")

            contract = self.contracts.get(step.skill)
            if contract is None:
                errors.append(f"step {step.id} uses unknown skill: {step.skill}")
                seen_ids.add(step.id)
                continue

            for arg_error in contract.validate_args(step.args):
                errors.append(f"step {step.id} {arg_error}")

            required = contract.required_facts(step.args)
            missing = required - facts
            if missing:
                errors.append(
                    f"step {step.id} missing required facts: {', '.join(sorted(missing))}"
                )
            elif not duplicate and not contract.validate_args(step.args):
                facts.difference_update(contract.invalidated_facts(step.args, facts))
                facts.update(contract.produced_facts(step.args))

            seen_ids.add(step.id)

        return errors
