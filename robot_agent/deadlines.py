"""Cancellation-preserving deadlines on every supported Python version.

Python 3.10's wait_for can swallow outer cancellation when the child completes
in the same event-loop turn (CPython #86296). Explicit waiting and draining keep
that cancellation observable by the physical-action interlock.
"""

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


async def wait_with_deadline(awaitable: Awaitable[T], timeout: float) -> T:
    task = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait((task,), timeout=timeout)
    except asyncio.CancelledError:
        task.cancel()
        # Child cancellation is returned as a value; a new outer cancellation
        # still propagates. Never replace caller cancellation with child success.
        await asyncio.gather(task, return_exceptions=True)
        raise
    if task in done:
        return task.result()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    raise asyncio.TimeoutError
