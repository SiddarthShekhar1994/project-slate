from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Skill(Base):
    """Mirror of the skills package, synced at startup so other tables can reference skills."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(60), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(60), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
