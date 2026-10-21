"""Run SymPy work on student input in a child process that can be killed.

SymPy has no cancellation, and a determined student can find inputs that make
simplification crawl. Grading therefore runs in a separate process with a hard
timeout. Children come from a forkserver started before the web server spawns
threads, with SymPy and the skills preloaded, so each call costs a few
milliseconds instead of a cold import.
"""

from __future__ import annotations

import multiprocessing as mp
import threading
from typing import Any, Callable

from ..config import get_settings

_PRELOAD = ["sympy", "slate_skills", "slate_api.services.grading", "slate_api.services.problem_gen"]
_ctx: Any = None
_lock = threading.Lock()
# Bound concurrent children so a burst of submissions cannot fork-bomb the host.
_slots = threading.BoundedSemaphore(8)


class SandboxTimeout(TimeoutError):
    pass


class SandboxError(RuntimeError):
    pass


def _context():
    global _ctx
    with _lock:
        if _ctx is None:
            # Windows has no forkserver; spawn works there but re-imports SymPy
            # for every answer, so grading is slower (keep GRADING_TIMEOUT_S >= 4).
            if "forkserver" in mp.get_all_start_methods():
                _ctx = mp.get_context("forkserver")
                _ctx.set_forkserver_preload(_PRELOAD)
            else:
                _ctx = mp.get_context("spawn")
        return _ctx


def warm_up() -> None:
    """Start the forkserver now (call at app startup, before threads exist)."""
    if get_settings().sandbox == "process":
        run(_noop, timeout=30)


def _noop() -> None:
    return None


def _child(conn, fn, args, kwargs) -> None:
    try:
        conn.send(("ok", fn(*args, **kwargs)))
    except BaseException as exc:  # report anything back to the parent
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def run(fn: Callable[..., Any], *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
    """Call ``fn(*args, **kwargs)`` in a child process, or inline when sandboxing is off."""
    settings = get_settings()
    if settings.sandbox == "inline":
        return fn(*args, **kwargs)
    limit = timeout if timeout is not None else settings.grading_timeout_s
    ctx = _context()
    with _slots:
        parent, child = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=_child, args=(child, fn, args, kwargs), daemon=True)
        proc.start()
        child.close()
        try:
            if not parent.poll(limit):
                raise SandboxTimeout(f"{getattr(fn, '__name__', 'task')} took longer than {limit}s")
            status, payload = parent.recv()
        except EOFError:
            raise SandboxError("worker exited without a result") from None
        finally:
            parent.close()
            if proc.is_alive():
                proc.kill()
            proc.join(1)
    if status == "error":
        raise SandboxError(payload)
    return payload
