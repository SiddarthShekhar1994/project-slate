import os
from pathlib import Path

# The session fixture rebuilds the whole schema, so never inherit DATABASE_URL:
# a dev URL exported in the shell (or loaded from .env) would be wiped.
# TEST_DATABASE_URL may be PostgreSQL or SQLite (the desktop app's database),
# e.g. sqlite:////tmp/slate_test.db; either way the name must end in _test.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL",
                                            "postgresql+psycopg://slate:slate@localhost:5432/slate_test")
os.environ["SANDBOX"] = "inline"
os.environ.setdefault("STORAGE_DIR", "/tmp/slate-test-storage")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from slate_api.db import get_engine
from slate_api.main import create_app
from slate_api.models import Base

API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
# Everything a test can create; skills and built-in lessons are synced at startup.
USER_TABLES = ("citations", "source_chunks", "sources", "lesson_questions", "checkpoint_answers", "lesson_progress",
               "skill_cards", "mistake_tags", "attempts", "worksheet_items", "worksheets", "problems",
               "auth_sessions", "users")


@pytest.fixture(scope="session", autouse=True)
def schema():
    engine = get_engine()
    url = engine.url
    name = Path(url.database or "").stem
    assert name.endswith("_test"), f"refusing to rebuild the schema of {name!r}: use a *_test database"
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    if engine.dialect.name == "sqlite":
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{url.database}{suffix}").unlink(missing_ok=True)
    else:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM lessons WHERE user_id IS NOT NULL"))
        if engine.dialect.name == "sqlite":
            # Children before parents, since foreign keys are enforced.
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in USER_TABLES:
                    conn.execute(table.delete())
        else:
            conn.execute(text(f"TRUNCATE {', '.join(USER_TABLES)} CASCADE"))


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def signed_in(client):
    r = client.post("/api/auth/signup", json={"email": "ada@example.com", "password": "correct horse",
                                              "display_name": "Ada"})
    assert r.status_code == 201, r.text
    return client
