"""Uploaded course materials, their extracted chunks, and what they were used for."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, timestamp_column, uuid_column

SOURCE_KINDS = ("slides", "textbook", "syllabus", "exam", "notes", "other")
SOURCE_STATUSES = ("processing", "ready", "failed")


class Source(Base):
    """One uploaded file. ``kind`` says whose voice it is: slides and notes are the
    professor's, a textbook chapter is the book's, and so on."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(f"kind IN {SOURCE_KINDS}", name="kind_valid"),
        CheckConstraint(f"status IN {SOURCE_STATUSES}", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int | None] = mapped_column(Integer)
    ocr_method: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = timestamp_column()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[list[SourceChunk]] = relationship(back_populates="source", cascade="all, delete-orphan",
                                                     order_by="SourceChunk.ordinal")


class SourceChunk(Base):
    """A topic-sized piece of a source: a slide or run of slides, a section, a page.

    ``locator`` is how a citation points at it ("slides 12-14", "p. 41").
    ``skills`` maps skill ids to match scores; ``notation`` records the
    notation styles seen in this chunk.
    """

    __tablename__ = "source_chunks"

    id: Mapped[uuid.UUID] = uuid_column()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"),
                                                 nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    locator: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict)
    notation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    top_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    source: Mapped[Source] = relationship(back_populates="chunks")


class Citation(Base):
    """A lesson or problem that drew on a chunk. The library's "used for" list reads these."""

    __tablename__ = "citations"
    __table_args__ = (CheckConstraint("(lesson_id IS NULL) <> (problem_id IS NULL)", name="one_target"),)

    id: Mapped[uuid.UUID] = uuid_column()
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("source_chunks.id", ondelete="CASCADE"),
                                                nullable=False, index=True)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"),
                                                        index=True)
    problem_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = timestamp_column()
