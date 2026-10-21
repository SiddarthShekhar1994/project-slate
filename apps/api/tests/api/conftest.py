import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://slate:slate@localhost:5432/slate_test")
os.environ["SANDBOX"] = "inline"
os.environ.setdefault("STORAGE_DIR", "/tmp/slate-test-storage")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from slate_api.db import get_engine
from slate_api.main import create_app

API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="session", autouse=True)
def schema():
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with get_engine().begin() as conn:
        conn.execute(text(
            "TRUNCATE citations, source_chunks, sources, lesson_questions, checkpoint_answers, lesson_progress, "
            "skill_cards, mistake_tags, attempts, worksheet_items, worksheets, problems, auth_sessions, users CASCADE"
        ))
        conn.execute(text("DELETE FROM lessons WHERE user_id IS NOT NULL"))


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
