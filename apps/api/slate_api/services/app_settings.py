"""API keys and provider choices for the desktop app.

On the website these come from the server's environment. In the desktop app
the student enters them on the Settings page; they are kept in settings.json
in the app's data folder (under %APPDATA%, readable only by that Windows
user) and applied to the environment, so the rest of the code reads them
exactly as on the server. Saved keys are never sent back to the page: it only
learns whether each one is set and its last four characters.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

KEYS = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
}
CHOICES = {
    "tts_provider": ("TTS_PROVIDER", ("", "elevenlabs", "openai")),
    "stt_provider": ("STT_PROVIDER", ("", "openai", "elevenlabs")),
}
MAX_KEY = 300


class SettingsError(ValueError):
    pass


def settings_path() -> Path:
    return Path(get_settings().data_dir) / "settings.json"


def load() -> dict[str, str]:
    """The saved values by environment variable name; {} if nothing is saved or the file is unreadable."""
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        log.warning("ignoring unreadable settings file %s", path)
        return {}
    known = set(KEYS.values()) | {env for env, _ in CHOICES.values()}
    return {k: str(v) for k, v in data.items() if k in known and isinstance(v, str)}


def apply(values: dict[str, str]) -> None:
    """Put saved values into the environment and drop everything cached from the old ones."""
    for env in list(KEYS.values()) + [env for env, _ in CHOICES.values()]:
        if values.get(env):
            os.environ[env] = values[env]
        else:
            os.environ.pop(env, None)
    from . import llm, stt, tts

    get_settings.cache_clear()
    llm.get_llm.cache_clear()
    tts.get_provider.cache_clear()
    stt.get_transcriber.cache_clear()


def apply_saved() -> None:
    """At startup in desktop mode: saved settings win over anything inherited."""
    if get_settings().desktop:
        apply(load())


def save(updates: dict[str, str | None]) -> None:
    """Change some settings. A missing field is left alone; an empty string clears it."""
    values = load()
    for field, value in updates.items():
        if value is None:
            continue
        value = value.strip()
        if field in KEYS:
            if len(value) > MAX_KEY or any(c.isspace() for c in value):
                raise SettingsError("That doesn't look like an API key. Paste it again without spaces.")
            env = KEYS[field]
        elif field in CHOICES:
            env, allowed = CHOICES[field]
            if value not in allowed:
                raise SettingsError(f"Unknown choice for {field}.")
        else:
            raise SettingsError(f"Unknown setting {field}.")
        if value:
            values[env] = value
        else:
            values.pop(env, None)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:  # Windows: the file inherits the user-only ACL of %APPDATA%
        pass
    tmp.replace(path)
    apply(values)


def view() -> dict:
    from . import llm, stt, tts

    values = load()

    def key(env: str) -> dict:
        value = values.get(env, "")
        return {"set": bool(value), "hint": f"…{value[-4:]}" if len(value) >= 8 else ("set" if value else "")}

    voice = tts.get_provider()
    transcriber = stt.get_transcriber()
    return {
        "keys": {field: key(env) for field, env in KEYS.items()},
        "tts_provider": values.get("TTS_PROVIDER", ""),
        "stt_provider": values.get("STT_PROVIDER", ""),
        "active": {
            "claude": llm.get_llm().available,
            "voice": voice.name if voice else None,
            "transcription": transcriber.name if transcriber else None,
        },
        "data_dir": get_settings().data_dir,
    }
