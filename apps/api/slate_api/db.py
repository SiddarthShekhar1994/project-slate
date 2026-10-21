"""Database engine, session factory and the FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


@cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()
