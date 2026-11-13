from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass


class ProcessFailure(RuntimeError):
    def __init__(self, returncode):
        self.returncode = returncode
        super().__init__(f"robot worker exited with code {returncode}")


@dataclass(frozen=True)
class ProcessOutput:
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner:
    """Own and reap only subprocesses started here, including child workers.

    Reaping a worker never proves the robot stopped. The executor retains the
    physical uncertainty interlock until a fresh state observation resolves it.
    """

    def __init__(self):
        self.active_pids = set()

    async def _stop(self, process, job=None):
        if os.name == "nt":
            if job is not None:
                job.terminate()
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()

    async def run(self, command, *, timeout_s, cwd=None, isolated_python=False):
        if not command or any(not isinstance(s, str) or not s for s in command):
            raise ValueError("commands must be a nonempty argument list")
        env = os.environ.copy()
        for key in ["DASHSCOPE_API_KEY", "QWEN_API_KEY", "OPENAI_API_KEY"]:
            env.pop(key, None)
        if isolated_python:
            for key in ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"]:
                env.pop(key, None)
            env["PYTHONNOUSERSITE"] = "1"
        job = None
        if os.name == "nt":
            from .windows_job import WindowsJob

            job = WindowsJob()
        options = (
            {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
                | 0x4
            }
            if os.name == "nt"
            else {"start_new_session": True}
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
                **options,
            )
        except BaseException:
            if job:
                job.close()
            raise
        self.active_pids.add(process.pid)
        try:
            if job:
                job.assign_and_resume(process.pid)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s)
            result = ProcessOutput(
                process.returncode,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
            if result.returncode:
                raise ProcessFailure(result.returncode)
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await self._stop(process, job)
            # Drain closed pipes before the event loop is torn down.
            await process.communicate()
            raise
        except BaseException:
            await self._stop(process, job)
            raise
        finally:
            self.active_pids.discard(process.pid)
            if job:
                job.close()
