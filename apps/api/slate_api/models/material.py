"""Problems and topics read from a student's course materials."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import GUID, Base, JSONType, timestamp_column, uuid_column

MATERIAL_STATUSES = ("ready", "unchecked", "unsupported")
MATERIAL_ORIGINS = ("sheet", "variant")


class Topic(Base):
    """A topic from a student's materials that no built-in skill covers (related rates, say).

    It has a row in ``skills`` with the same id, so attempts, mistake tags and
    review cards point at it like at any skill.
    """

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(120), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = timestamp_column()


class MaterialProblem(Base):
    """One problem from a sheet, or a similar problem written for practice.

    ``status`` is ``ready`` when SymPy's key agreed with the answer Claude gave
    for it; ``unchecked`` when they disagreed or a check failed, so Slate won't
    grade it; ``unsupported`` for kinds no computer can check (a proof, a
    sketch). ``reason`` says why, in words for the student. ``params`` hold
    what :func:`slate_api.services.materials.kinds.build` needs, including the
    key, so loading the problem never recomputes it.
    """

    __tablename__ = "material_problems"
    __table_args__ = (
        CheckConstraint(f"status IN {MATERIAL_STATUSES}", name="status_valid"),
        CheckConstraint(f"origin IN {MATERIAL_ORIGINS}", name="origin_valid"),
        CheckConstraint("difficulty BETWEEN 1 AND 4", name="difficulty_range"),
    )

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("sources.id", ondelete="CASCADE"),
                                                        index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("source_chunks.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("material_problems.id",
                                                                         ondelete="SET NULL"))
    skill_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("skills.id"), index=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="sheet")
    label: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claimed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    key_latex: Mapped[str | None] = mapped_column(Text)
    answer_kind: Mapped[str | None] = mapped_column(String(20))
    hints: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = timestamp_column()
