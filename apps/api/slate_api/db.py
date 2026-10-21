"""Database engine, session factory and the FastAPI dependency.

PostgreSQL serves the website; the desktop app keeps everything in one SQLite
file. SQLite connections get write-ahead logging (readers never block the
writer), enforced foreign keys (off by default in SQLite, and the cascades
depend on them) and a generous busy timeout so a second writer waits instead
of failing.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    for pragma in ("foreign_keys=ON", "journal_mode=WAL", "synchronous=NORMAL", "busy_timeout=30000"):
        cursor.execute(f"PRAGMA {pragma}")
    cursor.close()


@cache
def get_engine() -> Engine:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True)
    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def upsert(db: Session, model: Any):
    """``INSERT ... ON CONFLICT`` for whichever database the session uses.

    Both dialects take the same ``on_conflict_do_update(index_elements=...,
    set_=...)`` and expose ``excluded``.
    """
    name = db.get_bind().dialect.name
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise NotImplementedError(f"no upsert for {name}")
    return insert(model)


@cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()
