import asyncio
import ctypes
import os
import signal
import sys
import time
from pathlib import Path

import pytest
from robot_agent.adapters.process import ProcessRunner


def running(pid):
    if os.name == "nt":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        proc = Path("/proc") / str(pid) / "stat"
        return not proc.exists() or proc.read_text().split()[2] != "Z"
    except (ProcessLookupError, FileNotFoundError):
        return False


def test_exited_parent_does_not_leave_pipe_holding_descendant(tmp_path):
    marker = tmp_path / "child_pid.txt"
    child = "import time; time.sleep(15)"
    parent = (
        "import subprocess,sys,pathlib; p=subprocess.Popen([sys.executable,'-c',"
        + repr(child)
        + "]); pathlib.Path("
        + repr(str(marker))
        + ").write_text(str(p.pid))"
    )
    runner = ProcessRunner()
    try:
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(runner.run([sys.executable, "-c", parent], timeout_s=0.3))
        pid = int(marker.read_text())
        deadline = time.monotonic() + 1
        while running(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not running(pid), "owned descendant survived parent exit and timeout"
        assert not runner.active_pids
    finally:
        # Cleanup only this test's known child if the implementation is broken.
        if marker.exists():
            pid = int(marker.read_text())
            if running(pid):
                os.kill(pid, signal.SIGTERM)
