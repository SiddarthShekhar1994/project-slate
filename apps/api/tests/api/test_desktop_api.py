"""Desktop mode: the Windows app's single local profile and its Settings page."""

import json
import os

import pytest

from slate_api.config import get_settings
from slate_api.services import llm, stt, tts


@pytest.fixture
def desktop(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SLATE_DESKTOP", "1")
    monkeypatch.setenv("SLATE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SLATE_USER_NAME", "Ada")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TTS_PROVIDER", "STT_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    caches = (get_settings, llm.get_llm, tts.get_provider, stt.get_transcriber)
    for cached in caches:
        cached.cache_clear()
    yield client
    # Saving settings writes to os.environ directly; put it back.
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TTS_PROVIDER", "STT_PROVIDER"):
        os.environ.pop(key, None)
    monkeypatch.undo()
    for cached in caches:
        cached.cache_clear()


def test_desktop_needs_no_sign_in(desktop):
    session = desktop.get("/api/auth/session").json()
    assert session["desktop"] is True
    assert session["user"]["display_name"] == "Ada"
    # Everything works without a cookie, as the one local profile.
    r = desktop.post("/api/practice/worksheets", json={"skill_ids": ["calc1.derivatives.power_rule"], "count": 1})
    assert r.status_code == 201
    assert desktop.get("/api/practice/worksheets").json()["worksheets"][0]["id"] == r.json()["id"]
    # The profile is created once.
    assert desktop.get("/api/auth/session").json()["user"]["id"] == session["user"]["id"]


def test_website_still_requires_sign_in(client):
    assert client.get("/api/auth/session").json() == {"user": None, "desktop": False}
    assert client.get("/api/progress").status_code == 401
    assert client.get("/api/settings").status_code == 404


def test_settings_save_apply_and_never_echo_keys(desktop, tmp_path):
    view = desktop.get("/api/settings").json()
    assert view["keys"]["anthropic_api_key"] == {"set": False, "hint": ""}
    assert view["active"] == {"claude": False, "voice": None, "transcription": None}
    assert view["data_dir"] == str(tmp_path)

    r = desktop.put("/api/settings", json={"openai_api_key": "  sk-test-0123456789wxyz  "})
    assert r.status_code == 200
    body = r.json()
    assert body["keys"]["openai_api_key"] == {"set": True, "hint": "…wxyz"}
    # The key works straight away: an OpenAI key alone gives a voice and transcription.
    assert body["active"]["voice"] == "openai" and body["active"]["transcription"] == "openai"
    assert "sk-test" not in r.text and "sk-test" not in desktop.get("/api/settings").text
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved == {"OPENAI_API_KEY": "sk-test-0123456789wxyz"}

    # Omitted fields stay; an empty string clears.
    desktop.put("/api/settings", json={"anthropic_api_key": "sk-ant-0123456789abcd"})
    assert json.loads((tmp_path / "settings.json").read_text()).keys() == {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    assert desktop.get("/api/settings").json()["active"]["claude"] is True
    r = desktop.put("/api/settings", json={"openai_api_key": ""})
    assert r.json()["keys"]["openai_api_key"]["set"] is False and r.json()["active"]["voice"] is None


def test_settings_validation(desktop):
    assert desktop.put("/api/settings", json={"openai_api_key": "has spaces in it"}).status_code == 422
    assert desktop.put("/api/settings", json={"tts_provider": "robot"}).status_code == 422
    assert desktop.put("/api/settings", json={"tts_provider": "openai"}).json()["tts_provider"] == "openai"


def test_saved_settings_apply_at_startup(desktop, tmp_path):
    from slate_api.services import app_settings

    (tmp_path / "settings.json").write_text(json.dumps({"ELEVENLABS_API_KEY": "el-0123456789abcd", "BOGUS": "x"}))
    app_settings.apply_saved()
    assert os.environ["ELEVENLABS_API_KEY"] == "el-0123456789abcd"
    assert "BOGUS" not in os.environ
    assert tts.get_provider().name == "elevenlabs"
    # A corrupt file is ignored rather than stopping the app.
    (tmp_path / "settings.json").write_text("{not json")
    assert app_settings.load() == {}
