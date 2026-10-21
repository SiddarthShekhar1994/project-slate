"""Behaviour that differs by machine: the grading sandbox's process start
method and which voice provider the keys select."""

import math
import multiprocessing as mp
from types import SimpleNamespace

from slate_api.services import sandbox, tts


def test_sandbox_falls_back_to_spawn_without_forkserver(monkeypatch):
    # Windows has only "spawn"; the grading sandbox must still work there.
    monkeypatch.setattr(sandbox, "_ctx", None)
    monkeypatch.setattr(mp, "get_all_start_methods", lambda: ["spawn"])
    monkeypatch.setattr(sandbox, "get_settings", lambda: SimpleNamespace(sandbox="process", grading_timeout_s=60))
    assert sandbox._context().get_start_method() == "spawn"
    assert sandbox.run(math.factorial, 5) == 120


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
