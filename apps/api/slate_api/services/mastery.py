"""Mastery per skill, from graded attempts.

Recent attempts count more than old ones (each step back in time weighs
0.85 as much), so a student who struggled early and now gets problems right
moves up quickly. First-try correct answers count fully; answers that came
after a miss on the same worksheet item count half. Correct checkpoint
answers in lessons count a quarter, as light evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, CheckpointAnswer

DECAY = 0.85
WINDOW = 20
MASTERED = 0.85
PRACTICED = 0.6
MIN_FOR_MASTERY = 5


@dataclass(frozen=True)
class Mastery:
    skill_id: str
    attempts: int
    mastery: float | None
    status: str  # new | learning | practiced | mastered


def _status(score: float | None, attempts: int) -> str:
    if score is None:
        return "new"
    if score >= MASTERED and attempts >= MIN_FOR_MASTERY:
        return "mastered"
    if score >= PRACTICED:
        return "practiced"
    return "learning"


def skill_mastery(db: Session, user_id: uuid.UUID, skill_ids: list[str]) -> dict[str, Mastery]:
    out: dict[str, Mastery] = {}
    for skill_id in skill_ids:
        attempts = list(db.scalars(
            select(Attempt).where(Attempt.user_id == user_id, Attempt.skill_id == skill_id)
            .order_by(Attempt.created_at.desc()).limit(WINDOW)
        ))
        checks = list(db.scalars(
            select(CheckpointAnswer).where(CheckpointAnswer.user_id == user_id, CheckpointAnswer.skill_id == skill_id)
            .order_by(CheckpointAnswer.created_at.desc()).limit(WINDOW)
        ))
        events: list[tuple[float, float]] = []  # (credit, weight)
        for age, a in enumerate(attempts):
            credit = (1.0 if a.first_try else 0.5) if a.status == "correct" else 0.0
            events.append((credit, DECAY**age))
        for age, c in enumerate(checks):
            events.append((1.0 if c.correct else 0.0, 0.25 * DECAY**age))
        if not events:
            out[skill_id] = Mastery(skill_id, 0, None, "new")
            continue
        total = sum(w for _, w in events)
        score = sum(c * w for c, w in events) / total
        out[skill_id] = Mastery(skill_id, len(attempts), round(score, 3), _status(score, len(attempts)))
    return out
