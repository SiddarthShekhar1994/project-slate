"""SM-2 spaced repetition on skills, not cards.

A "review" of a skill is a finished worksheet item (or exam answer) on that
skill. Its quality on SM-2's 0 to 5 scale comes from how it went:

    5  right on the first try with no hints
    4  right on the first try after a hint
    3  right after one miss
    2  right after two or more misses
    1  wrong or blank on an exam

Several items on the same skill in one sitting (three hours from the first
one) count as one review, using the mean quality rounded down, so a long
worksheet doesn't push a skill months into the future in one afternoon. The
card keeps its state from before the sitting and recomputes from it each
time a new item lands.

The update is the classic SM-2 rule: a quality below 3 resets the run of
successes and brings the skill back tomorrow; otherwise the interval grows
1 day, 6 days, then by the easiness factor, and easiness moves by
0.1 - (5 - q)(0.08 + (5 - q)0.02), never below 1.3.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SkillCard

MIN_EASINESS = 1.3
START_EASINESS = 2.5
SITTING = timedelta(hours=3)
# The queue shows what is due now and what comes up in the next week.
HORIZON = timedelta(days=7)


@dataclass(frozen=True)
class CardState:
    easiness: float = START_EASINESS
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


def item_quality(*, correct: bool, misses: int, hints_used: int) -> int:
    if not correct:
        return 1
    if misses == 0:
        return 5 if hints_used == 0 else 4
    return 3 if misses == 1 else 2


def session_quality(qualities: list[int]) -> int:
    if not qualities:
        raise ValueError("a review needs at least one item")
    return math.floor(sum(qualities) / len(qualities))


def review(card: CardState, quality: int) -> CardState:
    """The card after one review of the given quality."""
    if not 0 <= quality <= 5:
        raise ValueError("quality is 0 to 5")
    easiness = max(MIN_EASINESS, card.easiness + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if quality < 3:
        return replace(card, easiness=easiness, interval_days=1, repetitions=0, lapses=card.lapses + 1)
    repetitions = card.repetitions + 1
    if repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = max(1, round(card.interval_days * easiness))
    return replace(card, easiness=easiness, interval_days=interval, repetitions=repetitions)


def _state(card: SkillCard) -> CardState:
    return CardState(card.easiness, card.interval_days, card.repetitions, card.lapses)


def record(db: Session, user_id: uuid.UUID, skill_id: str, quality: int, now: datetime | None = None) -> SkillCard:
    """Count one finished item towards the skill's review schedule."""
    now = now or datetime.now(timezone.utc)
    card = db.scalars(select(SkillCard).where(SkillCard.user_id == user_id, SkillCard.skill_id == skill_id)).first()
    if card is None:
        card = SkillCard(user_id=user_id, skill_id=skill_id, sitting={})
        base, started, qualities = CardState(), now, []
        db.add(card)
    else:
        sitting = card.sitting or {}
        started = datetime.fromisoformat(sitting["started_at"]) if sitting.get("started_at") else None
        if started is not None and now - started < SITTING:
            base, qualities = CardState(**sitting["base"]), list(sitting["qualities"])
        else:
            base, started, qualities = _state(card), now, []
    qualities.append(quality)
    after = review(base, session_quality(qualities))
    card.easiness = round(after.easiness, 4)
    card.interval_days = after.interval_days
    card.repetitions = after.repetitions
    card.lapses = after.lapses
    card.due_at = started + timedelta(days=after.interval_days)
    card.last_reviewed_at = now
    card.sitting = {"started_at": started.isoformat(), "base": asdict(base), "qualities": qualities}
    db.flush()
    return card


def cards(db: Session, user_id: uuid.UUID) -> list[SkillCard]:
    return list(db.scalars(select(SkillCard).where(SkillCard.user_id == user_id).order_by(SkillCard.due_at)))


def due_skill_ids(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    return [c.skill_id for c in cards(db, user_id) if c.due_at <= now]


def queue_view(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Skills due now (overdue first) and the ones coming up within a week."""
    from slate_skills import get_skill

    now = now or datetime.now(timezone.utc)
    due, upcoming = [], []
    for card in cards(db, user_id):
        if card.due_at > now + HORIZON:
            continue
        entry = {
            "skill": {"id": card.skill_id, "title": get_skill(card.skill_id).title},
            "due_at": card.due_at.isoformat(),
            "interval_days": card.interval_days,
            "repetitions": card.repetitions,
            "lapses": card.lapses,
            "last_reviewed_at": card.last_reviewed_at.isoformat(),
            "overdue_days": max(0, (now - card.due_at).days),
        }
        (due if card.due_at <= now else upcoming).append(entry)
    return {"due": due, "upcoming": upcoming}
