"""Behaviour that differs by machine: the grading sandbox's process start
method and which voice provider the keys select."""

import math
import multiprocessing as mp
import os
import sys
import time
from types import SimpleNamespace

import pytest

from slate_api.services import sandbox, tts


@pytest.fixture
def windows_sandbox(monkeypatch):
    """The sandbox as it runs on Windows: no forkserver, so the warm spawn pool."""
    monkeypatch.setattr(sandbox, "_ctx", None)
    monkeypatch.setattr(sandbox, "_the_pool", None)
    monkeypatch.setattr(mp, "get_all_start_methods", lambda: ["spawn"])
    monkeypatch.setattr(sandbox, "get_settings", lambda: SimpleNamespace(sandbox="process", grading_timeout_s=30))
    yield sandbox
    pool = sandbox._the_pool
    if pool is not None:
        while not pool.idle.empty():
            pool.idle.get().stop()


def test_windows_pool_grades_in_a_warm_reused_worker(windows_sandbox):
    assert windows_sandbox._context().get_start_method() == "spawn"
    # Starting a worker imports SymPy, which takes longer than this limit; it
    # must not count against the task's own time.
    first = windows_sandbox.run(os.getpid, timeout=0.5)
    assert first != os.getpid()
    assert windows_sandbox.run(math.factorial, 5, timeout=0.5) == 120
    # The pool keeps warm workers around: later calls land on one of them.
    pids = {windows_sandbox.run(os.getpid, timeout=0.5) for _ in range(6)}
    assert len(pids) <= sandbox.POOL_SIZE + 1


def test_windows_pool_kills_a_runaway_task_and_recovers(windows_sandbox):
    windows_sandbox.run(os.getpid)  # warm
    with pytest.raises(sandbox.SandboxTimeout):
        windows_sandbox.run(time.sleep, 5, timeout=0.3)
    assert windows_sandbox.run(math.factorial, 4, timeout=5) == 24


def test_windows_pool_reports_errors(windows_sandbox):
    with pytest.raises(sandbox.SandboxError, match="ValueError"):
        windows_sandbox.run(math.sqrt, -1)
    assert windows_sandbox.run(math.sqrt, 16) == 4.0


def test_windows_pool_grades_a_real_answer(windows_sandbox):
    from slate_api.services.grading import grade_answer
    from slate_api.services.problem_gen import generate

    problem = generate("calc1.derivatives.power_rule", 1, 7)
    key = str(problem.built.key).replace("**", "^")
    assert windows_sandbox.run(grade_answer, problem, key).status == "correct"
    assert windows_sandbox.run(grade_answer, problem, key + " + 1").status == "incorrect"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no forkserver to select")
def test_sandbox_uses_forkserver_where_it_exists(monkeypatch):
    monkeypatch.setattr(sandbox, "_ctx", None)
    monkeypatch.setattr(mp, "get_all_start_methods", lambda: ["fork", "spawn", "forkserver"])
    assert sandbox._context().get_start_method() == "forkserver"


def test_tts_provider_follows_the_keys(monkeypatch):
    for key in ("TTS_PROVIDER", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def provider():
        tts.get_provider.cache_clear()
        p = tts.get_provider()
        return p.name if p else None

    assert provider() is None
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert provider() == "openai"  # an OpenAI key alone is enough for a voice
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
    assert provider() == "elevenlabs"
    monkeypatch.setenv("TTS_PROVIDER", "openai")
    assert provider() == "openai"
    monkeypatch.setenv("TTS_PROVIDER", "silent")
    assert provider() == "silent"
    tts.get_provider.cache_clear()


def test_blank_settings_mean_defaults(monkeypatch):
    # A copied .env has blank lines like GRADING_TIMEOUT_S= ; they must not crash
    # startup or replace a default with an empty value.
    from slate_api.config import get_settings

    for name in ("GRADING_TIMEOUT_S", "WORKSHEET_SIZE", "SESSION_DAYS", "SANDBOX", "COOKIE_SECURE", "ANTHROPIC_MODEL",
                 "ANTHROPIC_API_KEY", "DATABASE_URL"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert (s.grading_timeout_s, s.worksheet_size, s.session_days, s.sandbox) == (4.0, 6, 30, "process")
        assert s.cookie_secure is False and s.anthropic_api_key is None
        assert s.anthropic_model == "claude-opus-5-5" and s.database_url.endswith("/slate")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_blank_voice_list_keeps_the_default_voices(monkeypatch):
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
    monkeypatch.setenv("ELEVENLABS_VOICES", "")
    monkeypatch.setenv("ELEVENLABS_MODEL", "")
    tts.get_provider.cache_clear()
    try:
        provider = tts.get_provider()
        assert [v.label for v in provider.voices()] == ["Rachel", "Adam", "Antoni"]
        assert provider.model == "eleven_multilingual_v2"
    finally:
        tts.get_provider.cache_clear()
