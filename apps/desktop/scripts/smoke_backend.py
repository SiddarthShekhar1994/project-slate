"""Start a packaged Slate backend and grade a few answers, printing everything.

    uv run python apps/desktop/scripts/smoke_backend.py apps/desktop/build/backend/slate-api.exe

Used by the Windows build before the app is packaged: if grading is slow or
broken on Windows, the timings, the worker processes and the backend's own
log end up in the build log. Exits non-zero if anything fails.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base: str, method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:2000]}


def workers(exe: str) -> str:
    name = Path(exe).name
    if sys.platform == "win32":
        return subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"], capture_output=True, text=True).stdout
    found = subprocess.run(["pgrep", "-af", name], capture_output=True, text=True).stdout.splitlines()
    return "\n".join(line for line in found if "smoke_backend.py" not in line)


def main() -> int:
    exe = sys.argv[1]
    data = tempfile.mkdtemp(prefix="slate-smoke-")
    log_path = Path(data) / "backend.log"
    port = free_port()
    base = f"http://127.0.0.1:{port}/api"
    ok = True
    with open(log_path, "w") as log:
        t0 = time.monotonic()
        proc = subprocess.Popen([exe, "--port", str(port), "--data-dir", data, "--watch-stdin"],
                                stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        try:
            while True:
                if proc.poll() is not None:
                    print(f"backend exited with code {proc.returncode} while starting")
                    ok = False
                    break
                try:
                    if call(base, "GET", "/health", timeout=2)[0] == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() - t0 > 180:
                    print("backend didn't answer within 180 s")
                    ok = False
                    break
                time.sleep(0.5)
            if ok:
                print(f"backend up after {time.monotonic() - t0:.1f}s")
                status, sheet = call(base, "POST", "/practice/worksheets",
                                     {"skill_ids": ["calc1.derivatives.power_rule"], "count": 3})
                print(f"worksheet: HTTP {status}")
                ok = status == 201
                for item in sheet.get("items", []) if ok else []:
                    t = time.monotonic()
                    status, result = call(base, "POST", f"/practice/items/{item['id']}/answer",
                                          {"answer": "x + 1"}, timeout=300)
                    grade = result.get("grade", {}).get("status") if status == 200 else result
                    print(f"answer graded in {time.monotonic() - t:.2f}s: HTTP {status} {grade}")
                    ok = ok and status == 200 and grade in ("correct", "incorrect", "invalid")
            print("\nbackend processes:\n" + workers(exe))
        finally:
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(10)
                print(f"backend exited by itself (code {proc.returncode}) when its stdin closed")
            except subprocess.TimeoutExpired:
                print("backend did NOT exit when its stdin closed; killing it")
                proc.kill()
                ok = False
    time.sleep(2)
    left = workers(exe)
    if Path(exe).name.lower() in left.lower():
        print("processes still running after shutdown:\n" + left)
        ok = False
    print("\n----- backend log -----")
    print(log_path.read_text(errors="replace"))
    print("smoke test", "passed" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
