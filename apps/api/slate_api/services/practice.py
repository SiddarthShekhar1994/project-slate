"""Worksheets and the retry loop.

A worksheet is a list of items ordered easy to hard. Each item holds one
problem at a time:

* ``up_next``: not answered yet.
* ``retrying``: missed at least once. After a miss the item is locked until the
  student asks for a similar problem (same skill, same difficulty, new
  mathematics). This repeats until they get one right.
* ``cleared``: right on the first problem.
* ``cleared_after_retry``: right after one or more misses.

Wrong answers are stored with their mistake tag. Unreadable input is reported
back to the student but is not a miss.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from slate_skills import get_skill
from slate_skills.core.types import DIFFICULTY_LABELS
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, MistakeTag, Problem, User, Worksheet, WorksheetItem
from . import sandbox
from .grading import Grade, grade_answer
from .problem_gen import VerifiedProblem, build_worksheet, restore, similar
from .verify import VerificationReport

MAX_WORKSHEET = 12


class PracticeError(ValueError):
    """A request that does not fit the item's state. ``code`` maps to an HTTP status."""

    def __init__(self, message: str, code: int = 409):
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- storing and loading problems ---------------------------------------------------


def store_problem(db: Session, user: User, problem: VerifiedProblem, parent_id: uuid.UUID | None = None) -> Problem:
    built = problem.built
    row = Problem(
        user_id=user.id,
        skill_id=problem.skill_id,
        family=problem.family,
        difficulty=problem.difficulty,
        seed=problem.seed,
        params=problem.params,
        signature=problem.signature,
        origin=problem.origin,
        parent_id=parent_id,
        prompt=built.prompt,
        variables=[s.name for s in built.symbols],
        answer_kind="number" if built.at else "expression",
        key_latex=_latex(built.key),
        steps=[{"id": s.id, "title": s.title, "latex": s.latex} for s in built.steps],
        hints=[problem.hints.nudge, problem.hints.bigger, problem.hints.full_step],
        verification=problem.report.as_dict(),
        verified_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


def _latex(expr) -> str:
    from slate_skills.core.text import tex

    return tex(expr)


def load_problem(row: Problem) -> VerifiedProblem:
    return restore(row.skill_id, row.family, row.params, row.seed,
                   VerificationReport.from_dict(row.verification), row.signature, origin=row.origin)


# --- worksheets -----------------------------------------------------------------------


def _title(skill_ids: list[str]) -> str:
    titles = [get_skill(s).title for s in skill_ids]
    if len(titles) == 1:
        return f"{titles[0]} practice"
    return "Mixed practice: " + ", ".join(t.lower() if i else t for i, t in enumerate(titles))


def create_worksheet(db: Session, user: User, skill_ids: list[str], count: int, seed: int | None = None,
                     mode: str = "practice", title: str | None = None) -> Worksheet:
    if not skill_ids:
        raise PracticeError("Pick at least one skill.", 422)
    for skill_id in skill_ids:
        try:
            get_skill(skill_id)
        except KeyError:
            raise PracticeError(f"Unknown skill {skill_id}.", 422) from None
    count = max(1, min(count, MAX_WORKSHEET))
    seed = seed if seed is not None else secrets.randbits(31)
    problems = build_worksheet(skill_ids, count, seed)

    sheet = Worksheet(user_id=user.id, title=title or _title(skill_ids), skill_ids=skill_ids, mode=mode, seed=seed)
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


def get_worksheet(db: Session, user: User, worksheet_id: uuid.UUID) -> Worksheet:
    sheet = db.get(Worksheet, worksheet_id)
    if sheet is None or sheet.user_id != user.id:
        raise PracticeError("Worksheet not found.", 404)
    return sheet


def recent_worksheets(db: Session, user: User, limit: int = 10) -> list[Worksheet]:
    return list(db.scalars(
        select(Worksheet).where(Worksheet.user_id == user.id).order_by(Worksheet.updated_at.desc()).limit(limit)
    ))


def _item(db: Session, user: User, item_id: uuid.UUID) -> WorksheetItem:
    item = db.get(WorksheetItem, item_id)
    if item is None or item.worksheet.user_id != user.id:
        raise PracticeError("Problem not found.", 404)
    return item


def _touch(item: WorksheetItem) -> None:
    item.worksheet.updated_at = _now()


# --- the retry loop ---------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitResult:
    grade: Grade
    item: WorksheetItem
    attempt: Attempt | None


def submit_answer(db: Session, user: User, item_id: uuid.UUID, raw: str, duration_ms: int | None = None) -> SubmitResult:
    item = _item(db, user, item_id)
    if item.status in ("cleared", "cleared_after_retry"):
        raise PracticeError("This problem is already cleared.")
    if item.needs_new_problem:
        raise PracticeError("Ask for a similar problem to try again.")

    problem_row = item.current_problem
    problem = load_problem(problem_row)
    try:
        grade: Grade = sandbox.run(grade_answer, problem, raw)
    except sandbox.SandboxTimeout:
        return SubmitResult(Grade(status="invalid", message="That answer took too long to check. "
                                  "Try writing it more simply."), item, None)

    if grade.status == "invalid":
        return SubmitResult(grade, item, None)

    first_try = item.misses == 0
    attempt = Attempt(
        user_id=user.id, problem_id=problem_row.id, worksheet_item_id=item.id, skill_id=item.skill_id,
        raw_input=raw[:500], latex=grade.latex or "", normalized=grade.normalized or "", status=grade.status,
        method=grade.method, hints_used=item.hint_level, first_try=first_try,
        duration_ms=duration_ms if duration_ms and duration_ms > 0 else None,
    )
    db.add(attempt)
    db.flush()

    if grade.correct:
        item.status = "cleared" if item.misses == 0 else "cleared_after_retry"
        item.cleared_at = _now()
        sheet = item.worksheet
        if all(i.status in ("cleared", "cleared_after_retry") for i in sheet.items):
            sheet.completed_at = _now()
    else:
        mistake = grade.mistake
        assert mistake is not None
        db.add(MistakeTag(
            attempt_id=attempt.id, user_id=user.id, skill_id=item.skill_id, tag=mistake.tag,
            category=mistake.category, step_id=mistake.step_id, evidence=mistake.evidence,
            where_to_look=mistake.where_to_look,
        ))
        item.misses += 1
        item.status = "retrying"
        item.needs_new_problem = True
    _touch(item)
    db.flush()
    return SubmitResult(grade, item, attempt)


def serve_similar(db: Session, user: User, item_id: uuid.UUID) -> WorksheetItem:
    item = _item(db, user, item_id)
    if item.status != "retrying":
        raise PracticeError("A similar problem is offered after a missed answer.")
    current = load_problem(item.current_problem)
    seen = set(db.scalars(
        select(Problem.signature).where(Problem.user_id == user.id, Problem.skill_id == item.skill_id)
    ))
    fresh = similar(current, attempt=item.problems_served, exclude=seen)
    row = store_problem(db, user, fresh, parent_id=item.current_problem_id)
    item.current_problem_id = row.id
    item.problems_served += 1
    item.hint_level = 0
    item.needs_new_problem = False
    _touch(item)
    db.flush()
    db.refresh(item)
    return item


def reveal_hint(db: Session, user: User, item_id: uuid.UUID, level: int) -> WorksheetItem:
    item = _item(db, user, item_id)
    if not 1 <= level <= 3:
        raise PracticeError("Hints go from 1 to 3.", 422)
    if level > item.hint_level + 1:
        raise PracticeError("Open the hints in order.", 422)
    if item.status in ("cleared", "cleared_after_retry"):
        raise PracticeError("This problem is already cleared.")
    item.hint_level = max(item.hint_level, level)
    _touch(item)
    db.flush()
    return item


# --- views ---------------------------------------------------------------------------------


def item_view(db: Session, item: WorksheetItem) -> dict:
    problem = item.current_problem
    skill = get_skill(item.skill_id)
    cleared = item.status in ("cleared", "cleared_after_retry")
    last = db.scalars(
        select(Attempt).where(Attempt.worksheet_item_id == item.id, Attempt.problem_id == problem.id)
        .order_by(Attempt.created_at.desc()).limit(1)
    ).first()
    return {
        "id": str(item.id),
        "position": item.position,
        "status": item.status,
        "misses": item.misses,
        "problems_served": item.problems_served,
        "needs_new_problem": item.needs_new_problem,
        "hint_level": item.hint_level,
        "skill": {"id": skill.id, "title": skill.title},
        "difficulty": item.difficulty,
        "difficulty_label": DIFFICULTY_LABELS[item.difficulty],
        "problem": {
            "id": str(problem.id),
            "prompt": problem.prompt,
            "variables": problem.variables,
            "answer_kind": problem.answer_kind,
            "is_word": skill.family(problem.family).word,
            "hints": problem.hints[: item.hint_level],
            "solution": problem.steps if cleared else None,
            "answer_latex": problem.key_latex if cleared else None,
        },
        "last_attempt": attempt_view(last) if last else None,
    }


def attempt_view(attempt: Attempt) -> dict:
    mistake = attempt.mistake
    return {
        "id": str(attempt.id),
        "status": attempt.status,
        "latex": attempt.latex,
        "mistake": None if mistake is None else mistake_view(mistake),
    }


def mistake_view(mistake: MistakeTag) -> dict:
    from slate_skills.core.mistakes import mistake_type

    kind = mistake_type(mistake.tag)
    return {
        "tag": mistake.tag,
        "label": kind.label,
        "category": mistake.category,
        "step_id": mistake.step_id,
        "where_to_look": mistake.where_to_look,
    }


def stats(sheet: Worksheet) -> dict:
    items = sheet.items
    return {
        "total": len(items),
        "first_try": sum(1 for i in items if i.status == "cleared"),
        "after_retry": sum(1 for i in items if i.status == "cleared_after_retry"),
        "retrying": sum(1 for i in items if i.status == "retrying"),
        "up_next": sum(1 for i in items if i.status == "up_next"),
        "misses": sum(i.misses for i in items),
        "completed": sheet.completed_at is not None,
    }


def worksheet_view(db: Session, sheet: Worksheet) -> dict:
    return {
        "id": str(sheet.id),
        "title": sheet.title,
        "mode": sheet.mode,
        "skills": [{"id": s, "title": get_skill(s).title} for s in sheet.skill_ids],
        "created_at": sheet.created_at.isoformat(),
        "completed_at": sheet.completed_at.isoformat() if sheet.completed_at else None,
        "items": [item_view(db, item) for item in sheet.items],
        "stats": stats(sheet),
    }


def worksheet_summary(sheet: Worksheet) -> dict:
    return {
        "id": str(sheet.id),
        "title": sheet.title,
        "mode": sheet.mode,
        "updated_at": sheet.updated_at.isoformat(),
        "completed_at": sheet.completed_at.isoformat() if sheet.completed_at else None,
        "stats": stats(sheet),
    }
