"""Problems, worksheets, attempts and mistake tags."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, timestamp_column, uuid_column

ITEM_STATUSES = ("up_next", "retrying", "cleared", "cleared_after_retry")


class Problem(Base):
    """A problem as served to one student.

    Rows are written only from a ``VerifiedProblem``. ``verified_at`` is not
    nullable and the check constraint requires the stored report to say it
    passed, so the database itself refuses an unverified problem.
    """

    __tablename__ = "problems"
    __table_args__ = (
        CheckConstraint("(verification ->> 'ok') = 'true'", name="verified_ok"),
        CheckConstraint("difficulty BETWEEN 1 AND 4", name="difficulty_range"),
    )

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="template")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("problems.id"))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    answer_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    key_latex: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    hints: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = timestamp_column()


class Worksheet(Base):
    __tablename__ = "worksheets"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    skill_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="practice")
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[WorksheetItem]] = relationship(
        back_populates="worksheet", order_by="WorksheetItem.position", cascade="all, delete-orphan"
    )


class WorksheetItem(Base):
    """One slot on a worksheet. Its current problem changes as similar problems are served."""

    __tablename__ = "worksheet_items"
    __table_args__ = (
        UniqueConstraint("worksheet_id", "position"),
        CheckConstraint(f"status IN {ITEM_STATUSES}", name="status_valid"),
        CheckConstraint("hint_level BETWEEN 0 AND 3", name="hint_level_range"),
    )

    id: Mapped[uuid.UUID] = uuid_column()
    worksheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    root_problem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("problems.id"), nullable=False)
    current_problem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("problems.id"),
                                                          nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="up_next")
    misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    problems_served: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hint_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_new_problem: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    worksheet: Mapped[Worksheet] = relationship(back_populates="items")
    current_problem: Mapped[Problem] = relationship(foreign_keys=[current_problem_id])


class Attempt(Base):
    """A graded answer. Unreadable input is not stored: it is not a miss."""

    __tablename__ = "attempts"
    __table_args__ = (CheckConstraint("status IN ('correct', 'incorrect')", name="status_valid"),)

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"),
                                                  nullable=False, index=True)
    worksheet_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("worksheet_items.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False, index=True)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    latex: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    method: Mapped[str | None] = mapped_column(String(60))
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_try: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = timestamp_column()

    mistake: Mapped[MistakeTag | None] = relationship(back_populates="attempt", uselist=False,
                                                      cascade="all, delete-orphan")


class MistakeTag(Base):
    """The mistake type assigned to a wrong attempt. The Progress page ranks these."""

    __tablename__ = "mistake_tags"

    id: Mapped[uuid.UUID] = uuid_column()
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(60))
    evidence: Mapped[str] = mapped_column(String(160), nullable=False)
    where_to_look: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()

    attempt: Mapped[Attempt] = relationship(back_populates="mistake")
