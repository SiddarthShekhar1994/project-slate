"""Settings read from the environment (see .env.example at the repo root)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
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
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "postgresql+psycopg://slate:slate@localhost:5432/slate"),
        session_cookie=os.environ.get("SESSION_COOKIE", "slate_session"),
        session_days=int(os.environ.get("SESSION_DAYS", "30")),
        cookie_secure=_bool("COOKIE_SECURE", False),
        grading_timeout_s=float(os.environ.get("GRADING_TIMEOUT_S", "4")),
        # "process" isolates each grading call in a child process that can be
        # killed on timeout; "inline" is for tests and debugging.
        sandbox=os.environ.get("SANDBOX", "process"),
        storage_dir=os.environ.get("STORAGE_DIR", "var/storage"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
        worksheet_size=int(os.environ.get("WORKSHEET_SIZE", "6")),
    )
