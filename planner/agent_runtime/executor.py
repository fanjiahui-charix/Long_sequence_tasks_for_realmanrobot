from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from .contracts import SkillContract
from .models import ExecStatus, FailureCode, SkillResult


class SkillExecutor:
    """Invoke one skill under its trusted contract timeout."""

    def execute(
        self,
        skill: Any,
        contract: SkillContract,
        args: dict[str, Any],
    ) -> SkillResult:
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"skill-{contract.name}")
        future = pool.submit(skill.run, **args)
        try:
            result = future.result(timeout=contract.timeout_s)
        except FutureTimeoutError:
            future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            if contract.side_effecting:
                return SkillResult.unknown(
                    FailureCode.PROTOCOL_ERROR,
                    message=f"{contract.name} timed out; physical outcome is unknown",
                    data={"timeout_s": contract.timeout_s},
                )
            return SkillResult(
                status=ExecStatus.TIMEOUT,
                failure_code=FailureCode.BUDGET_EXHAUSTED,
                message=f"{contract.name} timed out after {contract.timeout_s}s",
                data={"timeout_s": contract.timeout_s},
            )
        except Exception as exc:
            pool.shutdown(wait=False, cancel_futures=True)
            return SkillResult.failed(
                FailureCode.INTERNAL_ERROR,
                message=f"{type(exc).__name__}: {exc}",
            )
        else:
            pool.shutdown(wait=True)

        if not isinstance(result, SkillResult):
            return SkillResult.unknown(
                FailureCode.PROTOCOL_ERROR,
                message=f"{contract.name} returned {type(result).__name__}, expected SkillResult",
            )
        return result
