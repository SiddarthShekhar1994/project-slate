"""Lessons, where each student is in them, and their checkpoint answers and questions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    GUID,
    Base,
    JSONType,
    UTCDateTime,
    timestamp_column,
    uuid_column,
    verified_ok_constraints,
)


class Lesson(Base):
    """A lesson script. Built-in lessons have no owner; generated ones belong to a student.

    As with problems, the stored verification must say every claim checked out.
    """

    __tablename__ = "lessons"
    __table_args__ = verified_ok_constraints()

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                                      index=True)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    script: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("lessons.id", ondelete="CASCADE"),
                                                 primary_key=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = timestamp_column()


class CheckpointAnswer(Base):
    __tablename__ = "checkpoint_answers"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("lessons.id", ondelete="CASCADE"),
                                                 nullable=False)
    skill_id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id"), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    option_id: Mapped[str] = mapped_column(String(20), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class LessonQuestion(Base):
    """A question asked about a lesson step and the answer given."""

    __tablename__ = "lesson_questions"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("lessons.id", ondelete="CASCADE"),
                                                 nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
