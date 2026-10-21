"""Exam mode: a timed set over chosen topics, weighted like the syllabus.

Two paces:

* ``exam``: the real thing. Every problem is on screen at once, there are no
  hints and no retries, and nothing is graded until the set is handed in (or
  the time runs out). Each answer is then graded symbolically, and every wrong
  one gets a mistake tag like any other miss.
* ``study``: the same problems with half as much time again, played through
  the normal practice loop (hints, similar problems after a miss).

Weights say how much of the set each topic gets. They default to what the
student's syllabus says ("Chain rule ... 20%") when a syllabus is uploaded,
otherwise to equal shares, and the student can change them.
"""

from __future__ import annotations

import math
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from slate_skills import get_skill
from slate_skills.core.types import DIFFICULTY_LABELS
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, MistakeTag, Source, SourceChunk, User, Worksheet, WorksheetItem
from . import review, sandbox
from .grading import Grade, grade_answer
from .ingest.match import match_skills
from .practice import MAX_WORKSHEET, PracticeError, attempt_view, load_problem, store_problem
from .problem_gen import build_worksheet
from .verify import ParseError, parse_answer

PACES = ("exam", "study")
# Minutes per problem at exam pace, by difficulty (easy to challenge).
MINUTES = {1: 2.0, 2: 3.0, 3: 5.0, 4: 7.0}
STUDY_FACTOR = 1.5
# Answers saved a little after the clock runs out still count (network lag).
GRACE = timedelta(seconds=20)

_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- weights ---------------------------------------------------------------------------


def syllabus_weights(db: Session, user_id: uuid.UUID) -> dict[str, dict]:
    """Percentages the student's syllabus gives each skill, with where it said so.

    A line that names a topic and a percentage ("Chain rule and implicit
    differentiation ... 25%") gives that share to the skills it names, split
    evenly. The first mention of a skill wins.
    """
    rows = db.execute(
        select(SourceChunk, Source).join(Source, SourceChunk.source_id == Source.id)
        .where(Source.user_id == user_id, Source.kind == "syllabus", Source.status == "ready")
        .order_by(Source.created_at, SourceChunk.ordinal)
    ).all()
    found: dict[str, dict] = {}
    for chunk, source in rows:
        for line in chunk.text.splitlines():
            pct = _PERCENT.search(line)
            if not pct:
                continue
            skills = [s for s, score in match_skills(line).items() if score >= 0.25]
            for skill_id in skills:
                found.setdefault(skill_id, {
                    "percent": float(pct.group(1)) / len(skills),
                    "source": {"title": source.title, "locator": chunk.locator, "line": line.strip()[:200]},
                })
    return found


def default_weights(db: Session, user_id: uuid.UUID, skill_ids: list[str]) -> list[dict]:
    """A weight per skill, summing to 100, from the syllabus where it says, otherwise equal."""
    from_syllabus = syllabus_weights(db, user_id)
    known = [from_syllabus[s]["percent"] for s in skill_ids if s in from_syllabus]
    fill = sum(known) / len(known) if known else 1.0
    raw = {s: from_syllabus[s]["percent"] if s in from_syllabus else fill for s in skill_ids}
    total = sum(raw.values()) or 1.0
    return [
        {"skill_id": s, "weight": round(100 * raw[s] / total, 1),
         "source": from_syllabus[s]["source"] if s in from_syllabus else None}
        for s in skill_ids
    ]


def allocate(weights: dict[str, float], count: int) -> dict[str, int]:
    """Split ``count`` problems by weight (largest remainder). Every weighted
    skill gets at least one problem when there are enough to go round."""
    positive = {s: w for s, w in weights.items() if w > 0}
    if not positive or count <= 0:
        return {s: 0 for s in weights}
    total = sum(positive.values())
    exact = {s: count * w / total for s, w in positive.items()}
    out = {s: math.floor(v) for s, v in exact.items()}
    order = sorted(positive, key=lambda s: (exact[s] - out[s], positive[s]), reverse=True)
    for s in order[: count - sum(out.values())]:
        out[s] += 1
    if count >= len(positive):
        for s in [s for s in positive if out[s] == 0]:
            donor = max(out, key=lambda k: (out[k], -positive[k]))
            out[donor] -= 1
            out[s] = 1
    return {s: out.get(s, 0) for s in weights}


def time_limit_seconds(difficulties: list[int], pace: str) -> int:
    minutes = sum(MINUTES[d] for d in difficulties)
    if pace == "study":
        minutes *= STUDY_FACTOR
    return int(math.ceil(minutes)) * 60


# --- creating and running an exam -----------------------------------------------------------


def create_exam(db: Session, user: User, weights: dict[str, float], count: int, pace: str,
                seed: int | None = None) -> Worksheet:
    if pace not in PACES:
        raise PracticeError("Pace is exam or study.", 422)
    skill_ids = [s for s, w in weights.items() if w > 0]
    if not skill_ids:
        raise PracticeError("Pick at least one topic.", 422)
    for skill_id in skill_ids:
        try:
            get_skill(skill_id)
        except KeyError:
            raise PracticeError(f"Unknown skill {skill_id}.", 422) from None
    count = max(1, min(count, MAX_WORKSHEET))
    counts = allocate({s: weights[s] for s in skill_ids}, count)
    skill_ids = [s for s in skill_ids if counts[s] > 0]
    seed = seed if seed is not None else secrets.randbits(31)
    problems = build_worksheet(skill_ids, count, seed, counts=[counts[s] for s in skill_ids])

    limit = time_limit_seconds([p.difficulty for p in problems], pace)
    total = sum(weights[s] for s in skill_ids)
    title = "Practice exam" if pace == "exam" else "Practice exam, study pace"
    sheet = Worksheet(
        user_id=user.id, title=title, skill_ids=skill_ids, mode="exam", seed=seed,
        settings={"pace": pace, "time_limit_s": limit,
                  "weights": {s: round(100 * weights[s] / total, 1) for s in skill_ids}},
        ends_at=_now() + timedelta(seconds=limit),
    )
    db.add(sheet)
    db.flush()
    for position, problem in enumerate(problems):
        row = store_problem(db, user, problem)
        db.add(WorksheetItem(
            worksheet_id=sheet.id, position=position, skill_id=problem.skill_id, difficulty=problem.difficulty,
            root_problem_id=row.id, current_problem_id=row.id, status="up_next",
        ))
    db.flush()
    db.refresh(sheet)
    return sheet


def is_exam_pace(sheet: Worksheet) -> bool:
    return sheet.mode == "exam" and (sheet.settings or {}).get("pace") == "exam"


def get_exam(db: Session, user: User, worksheet_id: uuid.UUID) -> Worksheet:
    sheet = db.get(Worksheet, worksheet_id)
    if sheet is None or sheet.user_id != user.id or not is_exam_pace(sheet):
        raise PracticeError("Exam not found.", 404)
    if sheet.completed_at is None and _time_up(sheet):
        finish_exam(db, sheet)
    return sheet


def _time_up(sheet: Worksheet, now: datetime | None = None) -> bool:
    return sheet.ends_at is not None and (now or _now()) > sheet.ends_at + GRACE


def save_answer(db: Session, user: User, item_id: uuid.UUID, raw: str) -> WorksheetItem:
    """Keep the student's answer for one exam problem. It is graded at hand-in.

    Input that can't be read is refused now, while there is time to fix it;
    whether it is right stays hidden.
    """
    item = db.get(WorksheetItem, item_id)
    if item is None or item.worksheet.user_id != user.id or not is_exam_pace(item.worksheet):
        raise PracticeError("Problem not found.", 404)
    sheet = item.worksheet
    if sheet.completed_at is not None:
        raise PracticeError("This exam has been handed in.")
    if _time_up(sheet):
        finish_exam(db, sheet)
        raise PracticeError("Time is up. Your exam has been handed in.")
    raw = raw.strip()
    if raw:
        try:
            parse_answer(raw, [_symbol(v) for v in item.current_problem.variables])
        except ParseError as exc:
            raise PracticeError(str(exc), 422) from None
    item.exam_answer = raw[:500] or None
    sheet.updated_at = _now()
    db.flush()
    return item


def _symbol(name: str):
    import sympy as sp

    return sp.Symbol(name)


def finish_exam(db: Session, sheet: Worksheet) -> Worksheet:
    """Grade every answer, tag the wrong ones and update the review schedule."""
    if sheet.completed_at is not None:
        return sheet
    now = _now()
    for item in sheet.items:
        problem_row = item.current_problem
        raw = (item.exam_answer or "").strip()
        grade: Grade | None = None
        if raw:
            try:
                grade = sandbox.run(grade_answer, load_problem(problem_row), raw)
            except sandbox.SandboxTimeout:
                grade = None
        if grade is not None and grade.status != "invalid":
            attempt = Attempt(
                user_id=sheet.user_id, problem_id=problem_row.id, worksheet_item_id=item.id, skill_id=item.skill_id,
                raw_input=raw, latex=grade.latex or "", normalized=grade.normalized or "", status=grade.status,
                method=grade.method, hints_used=0, first_try=True,
            )
            db.add(attempt)
            db.flush()
            if not grade.correct:
                mistake = grade.mistake
                assert mistake is not None
                db.add(MistakeTag(
                    attempt_id=attempt.id, user_id=sheet.user_id, skill_id=item.skill_id, tag=mistake.tag,
                    category=mistake.category, step_id=mistake.step_id, evidence=mistake.evidence,
                    where_to_look=mistake.where_to_look,
                ))
        correct = grade is not None and grade.correct
        item.status = "cleared" if correct else "missed"
        item.misses = 0 if correct else 1
        item.cleared_at = now if correct else None
        review.record(db, sheet.user_id, item.skill_id, review.item_quality(correct=correct, misses=0, hints_used=0),
                      now)
    sheet.completed_at = now
    sheet.updated_at = now
    db.flush()
    return sheet


# --- views ---------------------------------------------------------------------------------------


def exam_item_view(db: Session, item: WorksheetItem, finished: bool) -> dict:
    problem = item.current_problem
    skill = get_skill(item.skill_id)
    view = {
        "id": str(item.id),
        "position": item.position,
        "skill": {"id": skill.id, "title": skill.title},
        "difficulty": item.difficulty,
        "difficulty_label": DIFFICULTY_LABELS[item.difficulty],
        "problem": {
            "id": str(problem.id),
            "prompt": problem.prompt,
            "variables": problem.variables,
            "answer_kind": problem.answer_kind,
            "is_word": skill.family(problem.family).word,
        },
        "answer": item.exam_answer,
        "result": None,
    }
    if finished:
        attempt = db.scalars(select(Attempt).where(Attempt.worksheet_item_id == item.id)
                             .order_by(Attempt.created_at.desc()).limit(1)).first()
        view["result"] = {
            "status": "correct" if item.status == "cleared" else ("blank" if not item.exam_answer else "incorrect"),
            "attempt": attempt_view(attempt) if attempt else None,
            "answer_latex": problem.key_latex,
            "solution": problem.steps,
        }
    return view


def exam_stats(sheet: Worksheet) -> dict:
    items = sheet.items
    finished = sheet.completed_at is not None
    by_skill: dict[str, dict] = {}
    for item in items:
        entry = by_skill.setdefault(item.skill_id, {"skill": {"id": item.skill_id,
                                                              "title": get_skill(item.skill_id).title},
                                                    "total": 0, "correct": 0})
        entry["total"] += 1
        entry["correct"] += int(finished and item.status == "cleared")
    return {
        "total": len(items),
        "answered": sum(1 for i in items if i.exam_answer),
        "correct": sum(1 for i in items if i.status == "cleared") if finished else None,
        "incorrect": sum(1 for i in items if i.status == "missed" and i.exam_answer) if finished else None,
        "blank": sum(1 for i in items if not i.exam_answer) if finished else None,
        "by_skill": list(by_skill.values()) if finished else None,
    }


def exam_view(db: Session, sheet: Worksheet) -> dict:
    finished = sheet.completed_at is not None
    settings = sheet.settings or {}
    used = None
    if finished:
        used = min(settings.get("time_limit_s", 0), int((sheet.completed_at - sheet.created_at).total_seconds()))
    return {
        "id": str(sheet.id),
        "title": sheet.title,
        "pace": settings.get("pace", "exam"),
        "weights": settings.get("weights", {}),
        "time_limit_s": settings.get("time_limit_s"),
        "ends_at": sheet.ends_at.isoformat() if sheet.ends_at else None,
        "now": _now().isoformat(),
        "time_used_s": used,
        "finished": finished,
        "completed_at": sheet.completed_at.isoformat() if finished else None,
        "skills": [{"id": s, "title": get_skill(s).title} for s in sheet.skill_ids],
        "items": [exam_item_view(db, item, finished) for item in sheet.items],
        "stats": exam_stats(sheet),
    }
