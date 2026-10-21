from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    MetaData,
    TypeDecorator,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# The same models run on PostgreSQL (the website) and SQLite (the desktop app).
# JSON is JSONB on PostgreSQL; GUID is a native UUID there and CHAR(32) on SQLite.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """A timezone-aware UTC datetime on every database.

    SQLite has no timezone support: SQLAlchemy would drop the offset on the
    way in and hand back naive datetimes, which can't be compared with the
    aware ones the app uses. This stores UTC and reattaches it on the way out.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if dialect.name == "sqlite":
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class GUID(TypeDecorator):
    """A UUID column that also accepts its string form, as PostgreSQL does.

    Ids arrive as strings from JSON, URLs and scripts; on SQLite the plain
    Uuid type only binds uuid.UUID objects.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if isinstance(value, str):
            return uuid.UUID(value)
        return value


def verified_ok_constraints() -> tuple[CheckConstraint, CheckConstraint]:
    """The database itself refuses rows whose verification report didn't pass.
    JSON is read differently on each database, so there is one CHECK per dialect."""
    return (
        CheckConstraint("(verification ->> 'ok') = 'true'", name="verified_ok").ddl_if(dialect="postgresql"),
        CheckConstraint("json_extract(verification, '$.ok') = 1", name="verified_ok").ddl_if(dialect="sqlite"),
    )


def uuid_column() -> Mapped[uuid.UUID]:
    return mapped_column(GUID, primary_key=True, default=uuid.uuid4)


def timestamp_column() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, nullable=False, server_default=func.now(), default=utcnow)
