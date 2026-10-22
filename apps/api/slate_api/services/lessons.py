"""Lessons: loading built-in scripts, views for the player, progress and checkpoints.

Built-in scripts live in ``slate_api/lessons/builtin/*.json``. They are synced
into the ``lessons`` table at startup only if every claim and checkpoint in
them passes SymPy verification; a script that fails is skipped and logged, so
an unverified lesson is never served.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from slate_skills import get_skill
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import upsert
from ..models import CheckpointAnswer, Citation, Lesson, LessonProgress, MaterialProblem, User
from . import tts
from .llm import get_llm
from .mastery import skill_mastery
from .verify.claims import script_is_sound

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "lessons" / "builtin"
BUILTIN_NAMESPACE = uuid.UUID("6f1b2c9e-5a3d-4f0e-9b7a-1c2d3e4f5a6b")


class LessonError(ValueError):
    def __init__(self, message: str, code: int = 404):
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def verification_record(script: dict) -> dict:
    ok, results = script_is_sound(script)
    return {"ok": ok, "checks": [{"where": r.where, "ok": r.ok, "detail": r.detail} for r in results]}


def sync_builtin_lessons(db: Session, directory: Path = BUILTIN_DIR) -> list[str]:
    """Upsert every built-in lesson that verifies. Returns the slugs loaded."""
    loaded = []
    for path in sorted(directory.glob("*.json")):
        script = json.loads(path.read_text(encoding="utf-8"))
        record = verification_record(script)
        if not record["ok"]:
            failures = [c for c in record["checks"] if not c["ok"]]
            log.error("built-in lesson %s failed verification and was skipped: %s", path.name, failures)
            continue
        slug = script["id"]
        values = {
            "id": uuid.uuid5(BUILTIN_NAMESPACE, slug), "user_id": None, "skill_id": script["skillId"],
            "kind": "builtin", "slug": slug, "title": script["title"], "summary": script.get("summary", ""),
            "script": script, "verification": record, "verified_at": _now(),
        }
        stmt = upsert(db, Lesson).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Lesson.slug],
            set_={k: stmt.excluded[k] for k in ("skill_id", "title", "summary", "script", "verification", "verified_at")},
        )
        db.execute(stmt)
        loaded.append(slug)
    db.commit()
    return loaded


def visible_lessons(db: Session, user: User, skill_ids: list[str] | None = None) -> list[Lesson]:
    query = select(Lesson).where(or_(Lesson.user_id.is_(None), Lesson.user_id == user.id))
    if skill_ids is not None:
        query = query.where(Lesson.skill_id.in_(skill_ids))
    return list(db.scalars(query.order_by(Lesson.created_at)))


def get_lesson(db: Session, user: User, lesson_id: uuid.UUID) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or (lesson.user_id is not None and lesson.user_id != user.id):
        raise LessonError("Lesson not found.")
    return lesson


def _resume_step(db: Session, user: User, lesson: Lesson) -> int:
    progress = db.get(LessonProgress, (user.id, lesson.id))
    steps = len(lesson.script["steps"])
    return min(progress.step, steps - 1) if progress else 0


def _last_opened(db: Session, user: User, lesson: Lesson) -> str | None:
    progress = db.get(LessonProgress, (user.id, lesson.id))
    return progress.updated_at.isoformat() if progress else None


def tts_info() -> dict:
    provider = tts.get_provider()
    if provider is None:
        return {"available": False, "provider": None, "voices": [], "default_voice": None}
    voices = provider.voices()
    return {
        "available": True,
        "provider": provider.name,
        "voices": [{"id": v.id, "label": v.label} for v in voices],
        "default_voice": voices[0].id if voices else None,
    }


def lesson_summary(db: Session, user: User, lesson: Lesson) -> dict:
    skill = get_skill(lesson.skill_id)
    return {
        "id": str(lesson.id),
        "title": lesson.title,
        "skill": {"id": skill.id, "title": skill.title},
        "kind": lesson.kind,
        "steps": len(lesson.script["steps"]),
        "resume_step": _resume_step(db, user, lesson),
        "last_opened": _last_opened(db, user, lesson),
        "sources": len(lesson.script.get("sources", [])),
    }


def _outline(db: Session, user: User, skill_id: str) -> list[dict]:
    """The student's topics for the player's sidebar, this lesson's topic included."""
    from .topics import topic_ids

    ids = topic_ids(db, user.id)
    if skill_id not in ids:
        ids.insert(0, skill_id)
    mastery = skill_mastery(db, user.id, ids)
    return [{"id": s, "title": get_skill(s).title, "mastery": mastery[s].mastery, "status": mastery[s].status}
            for s in ids]


def lesson_view(db: Session, user: User, lesson: Lesson) -> dict:
    skill = get_skill(lesson.skill_id)
    return {
        "id": str(lesson.id),
        "script": lesson.script,
        "skill": {"id": skill.id, "title": skill.title},
        "outline": {"unit": "Your topics", "skills": _outline(db, user, skill.id)},
        "sources": [
            {"id": s["id"], "title": s["title"], "kind": s.get("kind", "source"), "locator": s.get("locator", "")}
            for s in lesson.script.get("sources", [])
        ],
        "tts": tts_info(),
        "resume_step": _resume_step(db, user, lesson),
    }


def _step(lesson: Lesson, index: int) -> dict:
    steps = lesson.script["steps"]
    if not 0 <= index < len(steps):
        raise LessonError("No such step.", 422)
    return steps[index]


def save_progress(db: Session, user: User, lesson: Lesson, step: int) -> None:
    _step(lesson, step)
    stmt = upsert(db, LessonProgress).values(user_id=user.id, lesson_id=lesson.id, step=step, updated_at=_now())
    stmt = stmt.on_conflict_do_update(
        index_elements=[LessonProgress.user_id, LessonProgress.lesson_id],
        set_={"step": stmt.excluded.step, "updated_at": stmt.excluded.updated_at},
    )
    db.execute(stmt)


def answer_checkpoint(db: Session, user: User, lesson: Lesson, step: int, option_id: str) -> bool:
    checkpoint = _step(lesson, step).get("checkpoint")
    if not checkpoint:
        raise LessonError("This step has no checkpoint.", 422)
    option = next((o for o in checkpoint["options"] if o["id"] == option_id), None)
    if option is None:
        raise LessonError("No such option.", 422)
    db.add(CheckpointAnswer(user_id=user.id, lesson_id=lesson.id, skill_id=lesson.skill_id, step=step,
                            option_id=option_id, correct=bool(option["correct"])))
    return bool(option["correct"])


def step_audio(lesson: Lesson, step: int, voice: str) -> dict:
    narration = _step(lesson, step)["narration"]
    try:
        audio = tts.step_audio(narration, voice)
    except tts.TTSError as exc:
        return {"status": "unavailable", "reason": str(exc)}
    return audio.as_dict(f"/api/media/{audio.key}")


def latest_lesson(db: Session, user: User) -> tuple[Lesson, int] | None:
    progress = db.scalars(
        select(LessonProgress).where(LessonProgress.user_id == user.id).order_by(LessonProgress.updated_at.desc())
    ).first()
    if progress is None:
        return None
    lesson = db.get(Lesson, progress.lesson_id)
    return (lesson, progress.step) if lesson else None


def topic_examples(db: Session, user_id: uuid.UUID, skill_id: str, limit: int = 6) -> list[dict]:
    """Checked problems on the topic from the student's materials, sheets first, for the lesson to teach toward."""
    rows = db.scalars(select(MaterialProblem).where(
        MaterialProblem.user_id == user_id, MaterialProblem.skill_id == skill_id, MaterialProblem.status == "ready",
    ).order_by(MaterialProblem.origin, MaterialProblem.position).limit(limit))
    return [{"statement": r.statement or r.prompt, "answer": r.claimed} for r in rows]


def can_write_lesson(skill_id: str, *, llm=None) -> bool:
    """Claude can write a lesson on anything; without it only built-in skills (the composer) can have one."""
    from .lesson_gen.generate import can_compose

    llm = llm if llm is not None else get_llm()
    return llm.available or can_compose(skill_id)


def generate_for_topic(db: Session, user: User, skill_id: str, *, llm=None, seed: int = 0) -> Lesson:
    """Write a lesson on ``skill_id`` (any topic), from the student's own sources when they cover it, verified."""
    from .lesson_gen import ChunkRef, generate_lesson_script
    from .sources import chunks_for_skill, notation_for_user

    llm = llm if llm is not None else get_llm()
    try:
        get_skill(skill_id)
    except KeyError:
        raise LessonError("Unknown topic.", 422) from None
    if not can_write_lesson(skill_id, llm=llm):
        raise LessonError("Writing a lesson on this topic needs a Claude API key. Add one in Settings.", 409)
    found = chunks_for_skill(db, user.id, skill_id)
    refs = [
        ChunkRef(id=str(chunk.id), source_title=source.title, source_kind=source.kind, locator=chunk.locator,
                 heading=chunk.heading, text=chunk.text)
        for chunk, source in found
    ]
    try:
        result = generate_lesson_script(skill_id, refs, notation_for_user(db, user.id), llm=llm, seed=seed,
                                        examples=topic_examples(db, user.id, skill_id))
    except ValueError as exc:
        log.info("no lesson for %s: %s", skill_id, exc)
        raise LessonError("Slate couldn't write a lesson whose math all checked out. Try again in a minute.",
                          502) from None
    record = {**result.record, "method": result.method}
    if not record.get("ok"):
        raise LessonError("Slate couldn't write a lesson whose math all checked out. Try again in a minute.", 502)
    lesson = Lesson(user_id=user.id, skill_id=skill_id, kind="generated", slug=None,
                    title=result.script["title"][:200], summary=result.script.get("summary", ""),
                    script=result.script, verification=record, verified_at=_now())
    db.add(lesson)
    db.flush()
    cited = {s["id"] for s in result.script.get("sources", [])}
    for chunk, _ in found:
        if str(chunk.id) in cited:
            db.add(Citation(chunk_id=chunk.id, lesson_id=lesson.id))
    db.flush()
    return lesson
