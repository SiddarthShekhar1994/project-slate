"""What the Progress page shows: the skill map, ranked mistakes, the review
queue and the formula sheet.

Mistakes are ranked by a recency-weighted count: each tagged answer counts
half as much for every two weeks of age, so a habit the student has already
fixed sinks below the one they are still making.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from slate_skills import courses, get_skill
from slate_skills.core.mistakes import CATEGORIES, mistake_type
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Attempt, MistakeTag, Topic, Worksheet, WorksheetItem
from . import review
from .ingest.notation import apply_notation
from .mastery import skill_mastery

HALF_LIFE_DAYS = 14.0
MAX_MISTAKES = 8
RECENT_DAYS = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def skill_map(db: Session, user_id: uuid.UUID) -> list[dict]:
    """Courses, units and skills with mastery, first-try rate and review dates."""
    all_ids = [s.id for c in courses() for s in c.skills]
    mastery = skill_mastery(db, user_id, all_ids)
    counts = dict(db.execute(
        select(Attempt.skill_id, func.count()).where(Attempt.user_id == user_id).group_by(Attempt.skill_id)
    ).all())
    first = dict(db.execute(
        select(Attempt.skill_id, func.count()).where(Attempt.user_id == user_id, Attempt.first_try,
                                                     Attempt.status == "correct").group_by(Attempt.skill_id)
    ).all())
    firsts = dict(db.execute(
        select(Attempt.skill_id, func.count()).where(Attempt.user_id == user_id, Attempt.first_try)
        .group_by(Attempt.skill_id)
    ).all())
    last = dict(db.execute(
        select(Attempt.skill_id, func.max(Attempt.created_at)).where(Attempt.user_id == user_id)
        .group_by(Attempt.skill_id)
    ).all())
    cards = {c.skill_id: c for c in review.cards(db, user_id)}
    topics = list(db.scalars(select(Topic).where(Topic.user_id == user_id).order_by(Topic.created_at)))
    mastery.update(skill_mastery(db, user_id, [t.id for t in topics]) if topics else {})

    def row(skill_id: str, title: str, summary: str, prerequisites: tuple[str, ...] = (), lessons: bool = True) -> dict:
        return {
            "id": skill_id,
            "title": title,
            "summary": summary,
            "mastery": mastery[skill_id].mastery,
            "status": mastery[skill_id].status,
            "attempts": counts.get(skill_id, 0),
            "first_try_rate": (round(first.get(skill_id, 0) / firsts[skill_id], 3)
                               if firsts.get(skill_id) else None),
            "last_practiced_at": last[skill_id].isoformat() if skill_id in last else None,
            "due_at": cards[skill_id].due_at.isoformat() if skill_id in cards else None,
            "prerequisites": list(prerequisites),
            "lessons": lessons,
        }

    out = []
    for course in courses():
        out.append({
            "id": course.id,
            "title": course.title,
            "units": [{
                "id": unit.id,
                "title": unit.title,
                "skills": [row(skill.id, skill.title, skill.summary, skill.prerequisites) for skill in unit.skills],
            } for unit in course.units],
        })
    if topics:
        # Topics Slate found in the student's own uploads, beyond the built-in course.
        out.append({
            "id": "materials",
            "title": "From your materials",
            "units": [{"id": "materials", "title": "Topics from your uploads",
                       "skills": [row(t.id, t.title, t.summary, lessons=False) for t in topics]}],
        })
    return out


def ranked_mistakes(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> list[dict]:
    now = now or _now()
    tags = list(db.scalars(select(MistakeTag).where(MistakeTag.user_id == user_id)
                           .order_by(MistakeTag.created_at.desc())))
    groups: dict[str, dict] = {}
    for tag in tags:
        age_days = max(0.0, (now - tag.created_at).total_seconds() / 86400)
        group = groups.get(tag.tag)
        if group is None:
            kind = mistake_type(tag.tag)
            group = groups[tag.tag] = {
                "tag": tag.tag,
                "label": kind.label,
                "description": kind.description,
                "category": tag.category,
                "category_label": CATEGORIES.get(tag.category, tag.category),
                "count": 0,
                "recent": 0,
                "score": 0.0,
                "last_seen_at": tag.created_at.isoformat(),
                "skills": {},
                # The newest note is the most useful "where to look".
                "example": tag.where_to_look,
            }
        group["count"] += 1
        group["recent"] += int(age_days <= RECENT_DAYS)
        group["score"] += 0.5 ** (age_days / HALF_LIFE_DAYS)
        group["skills"][tag.skill_id] = group["skills"].get(tag.skill_id, 0) + 1
    ranked = sorted(groups.values(), key=lambda g: (-g["score"], -g["count"], g["label"]))[:MAX_MISTAKES]
    for group in ranked:
        group["score"] = round(group["score"], 3)
        group["skills"] = [{"id": s, "title": get_skill(s).title, "count": n}
                           for s, n in sorted(group["skills"].items(), key=lambda kv: -kv[1])]
    return ranked


def summary(db: Session, user_id: uuid.UUID) -> dict:
    total = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == user_id)) or 0
    first_tries = db.scalar(select(func.count()).select_from(Attempt)
                            .where(Attempt.user_id == user_id, Attempt.first_try)) or 0
    first_right = db.scalar(select(func.count()).select_from(Attempt)
                            .where(Attempt.user_id == user_id, Attempt.first_try, Attempt.status == "correct")) or 0
    cleared = db.scalar(
        select(func.count()).select_from(WorksheetItem).join(Worksheet, WorksheetItem.worksheet_id == Worksheet.id)
        .where(WorksheetItem.status.in_(("cleared", "cleared_after_retry")), Worksheet.user_id == user_id)
    ) or 0
    return {
        "answers": total,
        "problems_cleared": cleared,
        "first_try_rate": round(first_right / first_tries, 3) if first_tries else None,
    }


def progress_view(db: Session, user_id: uuid.UUID) -> dict:
    return {
        "summary": summary(db, user_id),
        "courses": skill_map(db, user_id),
        "mistakes": ranked_mistakes(db, user_id),
        "review": review.queue_view(db, user_id),
    }


def formula_sheet(db: Session, user_id: uuid.UUID, skill_ids: list[str]) -> dict:
    """Formula sheet entries for the chosen skills, grouped by unit, in the
    professor's notation where Slate can rewrite it."""
    from .sources import best_chunk_for_skill, citation_view, notation_for_user

    chosen = set(skill_ids)
    notation = notation_for_user(db, user_id)
    units = []
    for course in courses():
        for unit in course.units:
            entries = []
            for skill in unit.skills:
                if skill.id not in chosen:
                    continue
                entries.append({
                    "skill": {"id": skill.id, "title": skill.title},
                    "title": skill.formula.title,
                    "latex": apply_notation(skill.formula.latex, notation),
                    "note": skill.formula.note,
                    "source": citation_view(best_chunk_for_skill(db, user_id, skill.id)),
                })
            if entries:
                units.append({"id": unit.id, "title": unit.title, "course": course.title, "entries": entries})
    return {
        "units": units,
        "notation": notation.describe() if notation is not None else None,
    }
