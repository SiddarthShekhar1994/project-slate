"""Run pytest on the Windows runner so the step always ends, with pytest's output.

    python .github/scripts/run_pytest.py <limit-seconds> [pytest args...]

On the Windows runner a stuck test run never ended its step: not at the
step's time limit, not under `timeout`, not when the run was cancelled, and
its log never came back. Here pytest runs as a separate process that writes
to a file, and this script never waits on it past the limit: it stops it if
it can, prints the file and ends either way. While pytest runs, every
thread's stack goes into the file once a minute, so a stall shows where it
is. Standard library only, and nothing that touches WMI.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time

LAUNCH = """\
import faulthandler, os, sys
out = os.dup(2)  # pytest captures fd 2 while it works; keep a copy for the stacks
faulthandler.enable(file=out)
faulthandler.dump_traceback_later(60, repeat=True, file=out)
import pytest
sys.exit(pytest.main(sys.argv[1:]))
"""


def memory_load() -> int | None:
    """Percent of physical memory in use (Windows only)."""
    if sys.platform != "win32":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total", "avail", "page_total", "page_avail",
                                                    "virt_total", "virt_avail", "ext_avail")]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.dwMemoryLoad


def python_processes() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return sum(1 for line in out.splitlines() if line.startswith('"python.exe"'))


def stop(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(proc.pid, 9)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"couldn't stop pytest: {exc}")


def main() -> int:
    limit = float(sys.argv[1])
    args = ["-v", "-p", "no:cacheprovider", "-p", "no:faulthandler", "--durations=10", *sys.argv[2:]]
    log_path = os.path.join(tempfile.mkdtemp(prefix="pytest-run-"), "pytest.log")
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    start = time.monotonic()
    with open(log_path, "wb") as log:
        proc = subprocess.Popen([sys.executable, "-c", LAUNCH, *args], stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, **kwargs)
    status = None
    reason = ""
    next_report = 0.0
    while True:
        elapsed = time.monotonic() - start
        status = proc.poll()
        if status is not None:
            break
        load = memory_load()
        if elapsed >= next_report:
            count = python_processes()
            extra = "" if load is None else f"; memory {load}% used; {count} python processes"
            print(f"[{elapsed:5.0f}s] pytest running{extra}", flush=True)
            next_report += 30
        if load is not None and load >= 92:
            reason = f"memory is {load}% used"
            break
        if elapsed >= limit:
            reason = f"it ran past {limit:.0f}s"
            break
        time.sleep(1)
    if status is None:
        print(f"Stopping pytest: {reason}.", flush=True)
        stop(proc)
    with open(log_path, encoding="utf-8", errors="replace") as log:
        print(log.read())
    if status is None:
        print(f"::error::pytest was stopped because {reason}; the stacks above show where it was")
        return 124
    print(f"pytest exited with code {status} after {time.monotonic() - start:.0f}s")
    return status


if __name__ == "__main__":
    sys.exit(main())
