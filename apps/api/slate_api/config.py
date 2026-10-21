"""Settings read from the environment (see .env.example at the repo root)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path


def _env(name: str, default: str) -> str:
    """The variable's value; blank counts as unset, as in a half-filled .env."""
    raw = os.environ.get(name, "").strip()
    return raw or default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def default_data_dir() -> str:
    """Where the desktop app keeps its database, uploads and settings."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return str(base / "Slate")
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support" / "Slate")
    return str(Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "slate")


@dataclass(frozen=True)
class Settings:
    # Desktop mode (the Windows app): one local profile, no sign-in, SQLite and
    # uploads under data_dir, API keys from the Settings screen.
    desktop: bool
    data_dir: str
    database_url: str
    session_cookie: str
    session_days: int
    cookie_secure: bool
    grading_timeout_s: float
    sandbox: str
    storage_dir: str
    anthropic_api_key: str | None
    anthropic_model: str
    worksheet_size: int


@cache
def get_settings() -> Settings:
    desktop = _bool("SLATE_DESKTOP", False)
    data_dir = _env("SLATE_DATA_DIR", default_data_dir())
    local_db = "sqlite:///" + (Path(data_dir) / "slate.db").as_posix()
    server_db = "postgresql+psycopg://slate:slate@localhost:5432/slate"
    return Settings(
        desktop=desktop,
        data_dir=data_dir,
        database_url=_env("DATABASE_URL", local_db if desktop else server_db),
        session_cookie=_env("SESSION_COOKIE", "slate_session"),
        session_days=int(_env("SESSION_DAYS", "30")),
        cookie_secure=_bool("COOKIE_SECURE", False),
        grading_timeout_s=float(_env("GRADING_TIMEOUT_S", "4")),
        # "process" isolates each grading call in a child process that can be
        # killed on timeout; "inline" is for tests and debugging.
        sandbox=_env("SANDBOX", "process"),
        storage_dir=_env("STORAGE_DIR", str(Path(data_dir) / "storage") if desktop else "var/storage"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-opus-5-5"),
        worksheet_size=int(_env("WORKSHEET_SIZE", "6")),
    )
