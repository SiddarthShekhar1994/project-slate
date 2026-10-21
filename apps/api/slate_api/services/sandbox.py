"""Run SymPy work on student input in a child process that can be killed.

SymPy has no cancellation, and a determined student can find inputs that make
simplification crawl. Grading therefore runs in a separate process with a hard
timeout.

On macOS and Linux, children come from a forkserver started before the web
server spawns threads, with SymPy and the skills preloaded, so each call costs
a few milliseconds instead of a cold import and every answer gets a fresh
process.

Windows has no fork, and starting a fresh Python that imports SymPy takes a
second or more, which would eat most of the grading timeout. There, a small
pool of worker processes is kept warm: each has already imported SymPy and
the skills and waits for work. A worker that runs past the timeout is killed
and replaced in the background; healthy workers are reused for a bounded
number of tasks and then retired.
"""

from __future__ import annotations

import importlib
import logging
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

_PRELOAD = ["sympy", "slate_skills", "slate_api.services.grading", "slate_api.services.problem_gen"]
_ctx: Any = None
_lock = threading.Lock()
# Bound concurrent children so a burst of submissions cannot fork-bomb the host.
_slots = threading.BoundedSemaphore(8)

POOL_SIZE = 2
MAX_TASKS_PER_WORKER = 200
# Starting a worker includes importing SymPy; in a packaged app on a slow disk
# that can take a while, and it must never count against the grading timeout.
WORKER_START_TIMEOUT = 120.0


class SandboxTimeout(TimeoutError):
    pass


class SandboxError(RuntimeError):
    pass


def _context():
    global _ctx
    with _lock:
        if _ctx is None:
            # SLATE_SANDBOX_START=spawn tries the Windows pool on any platform (for testing builds).
            forced = os.environ.get("SLATE_SANDBOX_START", "")
            if forced in mp.get_all_start_methods() and forced != "forkserver":
                _ctx = mp.get_context(forced)
            elif "forkserver" in mp.get_all_start_methods():
                _ctx = mp.get_context("forkserver")
                _ctx.set_forkserver_preload(_PRELOAD)
            else:
                _ctx = mp.get_context("spawn")
        return _ctx


def _uses_pool() -> bool:
    return _context().get_start_method() != "forkserver"


def warm_up() -> None:
    """Start the forkserver or the warm pool now (call at app startup, before threads exist)."""
    if get_settings().sandbox != "process":
        return
    if _uses_pool():
        threading.Thread(target=_pool().fill, name="sandbox-warm-up", daemon=True).start()
    else:
        run(_noop, timeout=30)


def _noop() -> None:
    return None


# --- one fresh process per call (forkserver) -------------------------------------------


def _child(conn, fn, args, kwargs) -> None:
    try:
        conn.send(("ok", fn(*args, **kwargs)))
    except BaseException as exc:  # report anything back to the parent
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _run_fresh(ctx, fn: Callable[..., Any], args, kwargs, limit: float) -> tuple[str, Any]:
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, fn, args, kwargs), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(limit):
            raise SandboxTimeout(f"{getattr(fn, '__name__', 'task')} took longer than {limit}s")
        return parent.recv()
    except EOFError:
        raise SandboxError("worker exited without a result") from None
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(1)


# --- warm workers (spawn, i.e. Windows) ------------------------------------------------------

CREATE_NO_WINDOW = 0x08000000


class _NoWindowWinapi:
    """``_winapi`` as multiprocessing's spawn sees it, with workers started windowless.

    The Windows app starts the backend without a console. A worker is a
    console program too, and Windows gives a console program started without
    one a new console window: a black window would flash up for every
    worker. Only this module's view of CreateProcess changes.
    """

    def __init__(self, real) -> None:
        self._real = real

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def CreateProcess(self, *args):  # noqa: N802 - mirrors _winapi
        args = list(args)
        args[5] |= CREATE_NO_WINDOW  # creation flags
        return self._real.CreateProcess(*args)


def _hide_worker_windows() -> None:
    if sys.platform != "win32":
        return
    from multiprocessing import popen_spawn_win32

    if not isinstance(popen_spawn_win32._winapi, _NoWindowWinapi):
        popen_spawn_win32._winapi = _NoWindowWinapi(popen_spawn_win32._winapi)



def _serve(conn, preload: list[str]) -> None:
    """Worker loop: import the heavy modules once, then run tasks until told to stop."""
    try:
        for name in preload:
            importlib.import_module(name)
    except BaseException:
        # A spawned worker's own output goes nowhere on Windows, so report to the parent.
        import traceback

        conn.send(("failed", traceback.format_exc()))
        return
    conn.send(("ready", None))
    while True:
        try:
            task = conn.recv()
        except EOFError:
            return
        if task is None:
            return
        fn, args, kwargs = task
        try:
            conn.send(("ok", fn(*args, **kwargs)))
        except BaseException as exc:  # includes a result that can't be pickled
            conn.send(("error", f"{type(exc).__name__}: {exc}"))


class _Worker:
    def __init__(self, ctx) -> None:
        self.started = time.monotonic()
        self.conn, child = ctx.Pipe(duplex=True)
        self.proc = ctx.Process(target=_serve, args=(child, _PRELOAD), daemon=True)
        self.proc.start()
        child.close()
        self.tasks = 0
        log.info("grading worker %s starting", self.proc.pid)

    def wait_ready(self) -> None:
        reason = "it didn't answer"
        try:
            if self.conn.poll(WORKER_START_TIMEOUT):
                status, detail = self.conn.recv()
                if status == "ready":
                    log.info("grading worker %s ready after %.1fs", self.proc.pid, time.monotonic() - self.started)
                    return
                reason = detail
        except EOFError:
            reason = f"it exited with code {self.proc.exitcode}"
        log.error("grading worker %s failed to start after %.1fs: %s", self.proc.pid,
                  time.monotonic() - self.started, reason)
        self.stop()
        raise SandboxError("a grading worker failed to start")

    def stop(self) -> None:
        try:
            self.conn.close()
        finally:
            if self.proc.is_alive():
                self.proc.kill()
            self.proc.join(1)


class _Pool:
    def __init__(self, ctx) -> None:
        _hide_worker_windows()
        self.ctx = ctx
        self.idle: queue.Queue[_Worker] = queue.Queue()
        self.starting = 0
        self.lock = threading.Lock()

    def _start(self) -> _Worker:
        worker = _Worker(self.ctx)
        worker.wait_ready()
        return worker

    def fill(self) -> None:
        """Top the idle queue up to POOL_SIZE, counting workers already on their way."""
        while True:
            with self.lock:
                if self.idle.qsize() + self.starting >= POOL_SIZE:
                    return
                self.starting += 1
            try:
                self.idle.put(self._start())
            except SandboxError:
                return
            finally:
                with self.lock:
                    self.starting -= 1

    def refill_later(self) -> None:
        threading.Thread(target=self.fill, name="sandbox-refill", daemon=True).start()

    def run(self, fn: Callable[..., Any], args, kwargs, limit: float) -> tuple[str, Any]:
        try:
            worker = self.idle.get(timeout=WORKER_START_TIMEOUT if self.starting else 0)
        except queue.Empty:
            worker = self._start()  # nothing warm and nothing coming: start one now
        self.refill_later()
        try:
            worker.conn.send((fn, args, kwargs))
            finished = worker.conn.poll(limit)
            result = worker.conn.recv() if finished else None
        except (EOFError, OSError):
            worker.stop()
            raise SandboxError("worker exited without a result") from None
        if not finished:
            # SandboxTimeout is an OSError (TimeoutError), so it is raised outside the handler above.
            log.warning("grading worker %s ran past %ss; replacing it", worker.proc.pid, limit)
            worker.stop()
            raise SandboxTimeout(f"{getattr(fn, '__name__', 'task')} took longer than {limit}s")
        worker.tasks += 1
        if worker.tasks >= MAX_TASKS_PER_WORKER or not worker.proc.is_alive():
            worker.stop()
        else:
            self.idle.put(worker)
        return result


_the_pool: _Pool | None = None


def _pool() -> _Pool:
    global _the_pool
    with _lock:
        if _the_pool is None:
            _the_pool = _Pool(mp.get_context("spawn") if _ctx is None else _ctx)
        return _the_pool


# --- entry point ----------------------------------------------------------------------------


def run(fn: Callable[..., Any], *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
    """Call ``fn(*args, **kwargs)`` in a child process, or inline when sandboxing is off."""
    settings = get_settings()
    if settings.sandbox == "inline":
        return fn(*args, **kwargs)
    limit = timeout if timeout is not None else settings.grading_timeout_s
    ctx = _context()
    with _slots:
        if ctx.get_start_method() == "forkserver":
            status, payload = _run_fresh(ctx, fn, args, kwargs, limit)
        else:
            status, payload = _pool().run(fn, args, kwargs, limit)
    if status == "error":
        raise SandboxError(payload)
    return payload
