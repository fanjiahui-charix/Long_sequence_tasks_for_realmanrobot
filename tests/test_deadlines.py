import asyncio

import pytest

from robot_agent.deadlines import wait_with_deadline


def test_outer_cancellation_wins_when_inner_finishes_in_the_same_loop_turn():
    async def exercise():
        outer = asyncio.current_task()

        async def immediate():
            asyncio.get_running_loop().call_soon(outer.cancel)
            return "already finished"

        with pytest.raises(asyncio.CancelledError):
            await wait_with_deadline(immediate(), 1)

    asyncio.run(exercise())


def test_timeout_cancels_and_drains_the_inner_coroutine():
    async def exercise():
        cleaned = []

        async def worker():
            try:
                await asyncio.sleep(60)
            finally:
                cleaned.append(True)

        with pytest.raises(asyncio.TimeoutError):
            await wait_with_deadline(worker(), 0.01)
        assert cleaned == [True]

    asyncio.run(exercise())


def test_inner_exception_propagates():
    async def broken():
        raise RuntimeError("sensor failed")

    with pytest.raises(RuntimeError, match="sensor failed"):
        asyncio.run(wait_with_deadline(broken(), 1))


def test_outer_cancellation_survives_an_inner_coroutine_suppressing_cancel():
    async def exercise():
        started = asyncio.Event()

        async def worker():
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                return "stopped"

        outer = asyncio.create_task(wait_with_deadline(worker(), 1))
        await started.wait()
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer

    asyncio.run(exercise())
