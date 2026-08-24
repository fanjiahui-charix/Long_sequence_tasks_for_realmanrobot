from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class RetryMode(str, Enum):
    SAFE = "safe"
    VERIFY_BEFORE_RETRY = "verify_before_retry"
    NEVER = "never"


FactResolver = Callable[[dict[str, Any]], set[str]]
ArgumentValidator = Callable[[dict[str, Any]], str | None]


def _no_facts(_args: dict[str, Any]) -> set[str]:
    return set()


def _valid_args(_args: dict[str, Any]) -> str | None:
    return None


def at_fact(location: Any) -> str:
    return f"At({location})"


def localized_fact(obj: Any) -> str:
    return f"ObjectLocalized({obj})"


def holding_fact(obj: Any) -> str:
    return f"Holding({obj})"


def placed_fact(target: Any) -> str:
    return f"Placed({target})"


@dataclass(frozen=True)
class SkillContract:
    name: str
    timeout_s: float
    max_attempts: int
    retry_mode: RetryMode
    side_effecting: bool
    verifier: str
    required_args: tuple[str, ...] = ()
    requires: FactResolver = _no_facts
    produces: FactResolver = _no_facts
    invalidates: FactResolver = _no_facts
    invalidates_prefixes: tuple[str, ...] = ()
    argument_validator: ArgumentValidator = _valid_args
    pose_ttl_s: float | None = None

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        errors = [f"missing required argument: {name}" for name in self.required_args if name not in args]
        custom_error = self.argument_validator(args)
        if custom_error:
            errors.append(custom_error)
        return errors

    def required_facts(self, args: dict[str, Any]) -> set[str]:
        return set(self.requires(args))

    def produced_facts(self, args: dict[str, Any]) -> set[str]:
        return set(self.produces(args))

    def invalidated_facts(self, args: dict[str, Any], current_facts: set[str]) -> set[str]:
        invalidated = set(self.invalidates(args))
        for prefix in self.invalidates_prefixes:
            invalidated.update(fact for fact in current_facts if fact.startswith(prefix))
        return invalidated


def _navigation_target(args: dict[str, Any]) -> Any:
    return args.get("target") or args.get("marker") or args.get("table") or "coordinates"


def _validate_navigation_args(args: dict[str, Any]) -> str | None:
    if any(args.get(name) not in (None, "") for name in ("target", "marker", "table")):
        return None
    if all(name in args for name in ("x", "y", "theta")):
        return None
    return "requires target, marker, table, or x/y/theta"


def _place_requires(args: dict[str, Any]) -> set[str]:
    obj = args.get("object")
    return {holding_fact(obj)} if obj else set()


def default_contracts() -> dict[str, SkillContract]:
    contracts = [
        SkillContract(
            name="locate_table",
            timeout_s=10.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=False,
            verifier="control",
            required_args=("label",),
            produces=lambda args: {f"TableLocated({args['label']})"},
        ),
        SkillContract(
            name="plan_path",
            timeout_s=10.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=False,
            verifier="control",
            required_args=("from_table", "to_table"),
            produces=lambda args: {f"PathPlanned({args['from_table']},{args['to_table']})"},
        ),
        SkillContract(
            name="navigate_to",
            timeout_s=180.0,
            max_attempts=2,
            retry_mode=RetryMode.VERIFY_BEFORE_RETRY,
            side_effecting=True,
            verifier="navigation",
            argument_validator=_validate_navigation_args,
            produces=lambda args: {at_fact(_navigation_target(args))},
            invalidates_prefixes=("At(",),
        ),
        SkillContract(
            name="align_to_table",
            timeout_s=30.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=True,
            verifier="control",
            required_args=("table",),
        ),
        SkillContract(
            name="look_at",
            timeout_s=15.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=True,
            verifier="control",
            required_args=("target",),
        ),
        SkillContract(
            name="detect_object",
            timeout_s=30.0,
            max_attempts=2,
            retry_mode=RetryMode.SAFE,
            side_effecting=False,
            verifier="perception",
            required_args=("object",),
            produces=lambda args: {localized_fact(args["object"])},
            pose_ttl_s=2.0,
        ),
        SkillContract(
            name="pick_object",
            timeout_s=40.0,
            max_attempts=2,
            retry_mode=RetryMode.VERIFY_BEFORE_RETRY,
            side_effecting=True,
            verifier="grasp",
            required_args=("object",),
            requires=lambda args: {localized_fact(args["object"]), "HandEmpty"},
            produces=lambda args: {holding_fact(args["object"])},
            invalidates=lambda _args: {"HandEmpty"},
            pose_ttl_s=2.0,
        ),
        SkillContract(
            name="place_object",
            timeout_s=40.0,
            max_attempts=2,
            retry_mode=RetryMode.VERIFY_BEFORE_RETRY,
            side_effecting=True,
            verifier="place",
            required_args=("target",),
            requires=_place_requires,
            produces=lambda args: {"HandEmpty", placed_fact(args["target"])},
            invalidates_prefixes=("Holding(",),
        ),
        SkillContract(
            name="ask_human",
            timeout_s=1.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=False,
            verifier="control",
            required_args=("question",),
        ),
        SkillContract(
            name="abort",
            timeout_s=1.0,
            max_attempts=1,
            retry_mode=RetryMode.NEVER,
            side_effecting=False,
            verifier="control",
            required_args=("reason",),
        ),
    ]
    return {contract.name: contract for contract in contracts}
