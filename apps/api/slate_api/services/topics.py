"""The student's topics: what the dashboard, the sidebar and each topic's page show.

A topic is one of the student's own (a :class:`Topic`, found in an upload or
added by name: related rates, L'Hopital's rule, anything) or a built-in skill
on their dashboard (a :class:`TopicPin`). Every topic gets a lesson, problems
and worksheets. For the student's own topics Claude writes the lesson and the
problems in the background, and SymPy checks both before anything is shown;
built-in skills make their problems from templates.

``build`` on the topic (or pin) records that background work per part
(``problems``, ``lesson``): queued, pending (started), done or failed.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from slate_skills import all_skills, get_skill, is_builtin, register_extra
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_engine
from ..models import (
    Attempt,
    Lesson,
    MaterialProblem,
    MistakeTag,
    Problem,
    Skill,
    Source,
    SourceChunk,
    Topic,
    TopicPin,
    User,
    Worksheet,
)
from . import lessons as lesson_service
from .llm import LLMRefused, LLMUnavailable, get_llm
from .mastery import skill_mastery
from .materials import service as materials
from .materials.kinds import KIND_INFO
from .materials.variants import plan_topic
from .practice import worksheet_summary

log = logging.getLogger(__name__)

# A part that started this long ago and never finished died with its process; it can start again.
STALE_PENDING = timedelta(minutes=20)
STALE_QUEUED = timedelta(hours=2)
NEW_TOPIC_PROBLEMS = 8
MIN_PROBLEMS = 4
MAX_LESSONS_PER_SOURCE = 12
MAX_TOPIC_WORKSHEETS = 8
MIN_SOURCE_SCORE = 0.3  # as sources.MIN_SKILL_SCORE: a chunk this strongly about a topic covers it

# Quick picks on the dashboard. The ones a built-in skill covers work without Claude.
SUGGESTIONS: tuple[tuple[str, str | None], ...] = (
    ("Limits", "Finding limits by algebra, from one side, and at infinity."),
    ("L'Hôpital's rule", "Limits of the form 0/0 or ∞/∞, by differentiating the top and the bottom."),
    ("Power rule", None),
    ("Product rule", None),
    ("Quotient rule", None),
    ("Chain rule", None),
    ("Implicit differentiation", None),
    ("Related rates", "How fast one quantity changes when it is tied to others that are changing."),
    ("Linear approximation", "Estimating a function's values with its tangent line."),
    ("Critical points and extrema", "Where a function turns, and its largest and smallest values."),
    ("Optimization", "Word problems about making something as large or as small as possible."),
    ("The Mean Value Theorem", "Where the instantaneous rate of change equals the average rate."),
    ("Antiderivatives", "Working backward from a derivative to the function."),
    ("Definite integrals", "Areas and accumulated change, with the Fundamental Theorem of Calculus."),
    ("U-substitution", "Integrals made simpler by a change of variable."),
)


class TopicError(ValueError):
    def __init__(self, message: str, code: int = 404):
        super().__init__(message)
        self.code = code


class NotMath(ValueError):
    """What the student typed isn't a topic Slate can teach."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def builtin_for(name: str) -> str | None:
    """The built-in skill a typed name means ("chain rule", "The Product Rule"), if any."""
    wanted = materials.normalize_title(name)
    for skill in all_skills():
        names = {skill.title, skill.slug.replace("_", " "), *skill.keywords[:1]}
        if wanted in {materials.normalize_title(n) for n in names}:
            return skill.id
    return None


# --- which topics a student has ---------------------------------------------------------------


def _own(db: Session, user_id: uuid.UUID) -> list[Topic]:
    return list(db.scalars(select(Topic).where(Topic.user_id == user_id, Topic.hidden.is_(False))))


def _pins(db: Session, user_id: uuid.UUID) -> list[TopicPin]:
    return list(db.scalars(select(TopicPin).where(TopicPin.user_id == user_id)))


def topic_ids(db: Session, user_id: uuid.UUID) -> list[str]:
    """The student's topics in the order they arrived."""
    entries = [(t.created_at, t.id) for t in _own(db, user_id)] + [(p.created_at, p.skill_id) for p in _pins(db, user_id)]
    return [skill_id for _, skill_id in sorted(entries)]


def _holder(db: Session, user_id: uuid.UUID, skill_id: str) -> Topic | TopicPin | None:
    """The row that says this topic is the student's, and holds its build record."""
    if is_builtin(skill_id):
        return db.get(TopicPin, (user_id, skill_id))
    topic = db.get(Topic, skill_id)
    return topic if topic is not None and topic.user_id == user_id else None


def _mark(holder: Topic | TopicPin, part: str, status: str, error: str | None = None) -> None:
    build = dict(holder.build or {})
    build[part] = {"status": status, "at": _now().isoformat(), **({"error": error} if error else {})}
    holder.build = build


def _part(build: dict | None, part: str) -> tuple[str, str | None]:
    """A part's state for the student: writing, failed, done or none (never started, or died)."""
    entry = (build or {}).get(part) or {}
    status = entry.get("status")
    if status in ("queued", "pending"):
        try:
            at = datetime.fromisoformat(entry["at"])
        except (KeyError, ValueError):
            return "none", None
        limit = STALE_QUEUED if status == "queued" else STALE_PENDING
        return ("writing", None) if _now() - at < limit else ("none", None)
    if status == "failed":
        return "failed", entry.get("error")
    return ("done", None) if status == "done" else ("none", None)


def has_lesson(db: Session, user_id: uuid.UUID, skill_id: str) -> bool:
    return db.scalar(select(func.count()).select_from(Lesson).where(
        Lesson.skill_id == skill_id, or_(Lesson.user_id.is_(None), Lesson.user_id == user_id))) > 0


# --- what the dashboard shows -----------------------------------------------------------------


def _sources_by_topic(db: Session, user_id: uuid.UUID, ids: list[str]) -> dict[str, list[dict]]:
    wanted = set(ids)
    found: dict[str, dict[str, dict]] = {}
    rows = db.execute(select(SourceChunk.skills, Source.id, Source.title).join(Source, Source.id == SourceChunk.source_id)
                      .where(Source.user_id == user_id, Source.status == "ready").order_by(Source.created_at)).all()
    for skills, source_id, title in rows:
        for skill_id, score in (skills or {}).items():
            if skill_id in wanted and float(score) >= MIN_SOURCE_SCORE:
                found.setdefault(skill_id, {})[str(source_id)] = {"id": str(source_id), "title": title}
    return {skill_id: list(sources.values()) for skill_id, sources in found.items()}


def cards(db: Session, user: User, ids: list[str]) -> list[dict]:
    """One card per topic: progress, what's ready, what Slate is still writing, where it came from."""
    if not ids:
        return []
    llm_ok = get_llm().available
    mastery = skill_mastery(db, user.id, ids)
    lessons = dict(db.execute(select(Lesson.skill_id, func.count()).where(
        Lesson.skill_id.in_(ids), or_(Lesson.user_id.is_(None), Lesson.user_id == user.id)).group_by(Lesson.skill_id)).all())
    problems = dict(db.execute(select(MaterialProblem.skill_id, func.count()).where(
        MaterialProblem.user_id == user.id, MaterialProblem.status == "ready", MaterialProblem.skill_id.in_(ids))
        .group_by(MaterialProblem.skill_id)).all())
    sources = _sources_by_topic(db, user.id, ids)
    out = []
    for skill_id in ids:
        skill = get_skill(skill_id)
        builtin = is_builtin(skill_id)
        holder = _holder(db, user.id, skill_id)
        build = holder.build if holder is not None else None
        # Writing (a first lesson or a new one) shows as writing; otherwise a topic with a lesson is done,
        # and the error from a new lesson that didn't work out stays visible next to the old one.
        lesson_state, lesson_error = _part(build, "lesson")
        if lesson_state != "writing" and lessons.get(skill_id):
            lesson_state = "done"
        if lesson_state == "none" and not lesson_service.can_write_lesson(skill_id):
            lesson_state = "needs_key"
        practice_state, practice_error = _part(build, "problems")
        if practice_state != "writing" and (builtin or problems.get(skill_id)):
            practice_state = "done"
        if practice_state == "none" and not llm_ok:
            practice_state = "needs_key"
        out.append({
            "id": skill_id,
            "title": skill.title,
            "summary": skill.summary,
            "builtin": builtin,
            "origin": "builtin" if builtin else (holder.origin if isinstance(holder, Topic) else "upload"),
            "on_dashboard": holder is not None and not (isinstance(holder, Topic) and holder.hidden),
            "mastery": mastery[skill_id].mastery,
            "status": mastery[skill_id].status,
            "lessons": lessons.get(skill_id, 0),
            "problems": problems.get(skill_id, 0),
            "lesson": lesson_state,
            "lesson_error": lesson_error,
            "practice": practice_state,
            "practice_error": practice_error,
            "sources": sources.get(skill_id, []),
        })
    return out


def suggestions(db: Session, user: User, have: list[str]) -> list[dict]:
    titles = {materials.normalize_title(get_skill(s).title) for s in have}
    out = []
    for title, summary in SUGGESTIONS:
        builtin = builtin_for(title)
        if builtin in have or materials.normalize_title(title) in titles:
            continue
        out.append({"title": title, "summary": summary or get_skill(builtin).summary, "builtin": builtin is not None})
    return out


def pending_work(db: Session, user: User) -> list[tuple[str, tuple[str, ...]]]:
    """What to write now, marked queued: work that died with its process (the app was closed mid-write),
    and a first lesson (and problems) for topics that never had any written, such as topics read from
    an upload before Slate wrote lessons for every topic."""
    llm_ok = get_llm().available
    ready = dict(db.execute(select(MaterialProblem.skill_id, func.count()).where(
        MaterialProblem.user_id == user.id, MaterialProblem.status == "ready").group_by(MaterialProblem.skill_id)).all())
    out = []
    for holder in [*_own(db, user.id), *_pins(db, user.id)]:
        skill_id = holder.id if isinstance(holder, Topic) else holder.skill_id
        build = holder.build or {}
        parts = []
        for part in ("problems", "lesson"):
            status = (build.get(part) or {}).get("status")
            if status in ("queued", "pending"):
                if _part(build, part)[0] == "none":  # started long ago and never finished
                    parts.append(part)
            elif status is None:
                if part == "problems":
                    if isinstance(holder, Topic) and llm_ok and ready.get(skill_id, 0) < MIN_PROBLEMS:
                        parts.append(part)
                elif not has_lesson(db, user.id, skill_id) and lesson_service.can_write_lesson(skill_id):
                    parts.append(part)
        if parts:
            for part in parts:
                _mark(holder, part, "queued")
            out.append((skill_id, tuple(parts)))
    return out


def build_all(user_id: uuid.UUID, work: list[tuple[str, tuple[str, ...]]], *, llm=None) -> None:
    """Write several topics one after another (background)."""
    for skill_id, parts in work:
        build_topic(skill_id, user_id, parts, llm=llm)


def dashboard(db: Session, user: User) -> dict:
    ids = topic_ids(db, user.id)
    return {"topics": cards(db, user, ids), "suggestions": suggestions(db, user, ids),
            "claude": get_llm().available}


# --- adding and removing ----------------------------------------------------------------------


def add_topic(db: Session, user: User, name: str, *, llm=None) -> tuple[str, tuple[str, ...]]:
    """Put a topic on the student's dashboard. Returns its id and the parts Slate now has to write."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name:
        raise TopicError("Type the topic you want to learn.", 422)
    if len(name) > 120:
        raise TopicError("Keep the topic's name under 120 characters.", 422)
    builtin = builtin_for(name)
    if builtin:
        materials.pin_skill(db, user.id, builtin)
        if has_lesson(db, user.id, builtin):
            return builtin, ()
        _mark(_holder(db, user.id, builtin), "lesson", "queued")
        return builtin, ("lesson",)
    existing = materials.find_topic(db, user.id, name)
    if existing is not None:
        existing.hidden = False
        return existing.id, ()
    llm = llm if llm is not None else get_llm()
    if not llm.available:
        raise TopicError("Slate needs a Claude API key to teach topics beyond its built-in ones. "
                         "Add one in Settings.", 409)
    topic_id = materials.ensure_topic(db, user.id, name, origin="added")
    topic = db.get(Topic, topic_id)
    _mark(topic, "problems", "queued")
    _mark(topic, "lesson", "queued")
    return topic_id, ("problems", "lesson")


def remove_topic(db: Session, user: User, skill_id: str) -> None:
    """Take a topic off the dashboard. Its history stays, and adding it again brings it back."""
    holder = _holder(db, user.id, skill_id)
    if holder is None or (isinstance(holder, Topic) and holder.hidden):
        raise TopicError("That topic isn't on your dashboard.")
    if isinstance(holder, TopicPin):
        db.delete(holder)
    else:
        holder.hidden = True


def request_build(db: Session, user: User, skill_id: str, part: str) -> tuple[str, ...]:
    """The student asked for a (new) lesson or more problems. Returns the parts to run."""
    if part not in ("lesson", "problems"):
        raise TopicError("Unknown part.", 422)
    holder = _holder(db, user.id, skill_id)
    if holder is None and is_builtin(skill_id):
        materials.pin_skill(db, user.id, skill_id)
        holder = _holder(db, user.id, skill_id)
    if holder is None:
        raise TopicError("That topic isn't on your dashboard.")
    if part == "problems" and is_builtin(skill_id):
        raise TopicError("Slate makes new problems for this topic every time you practice.", 409)
    if _part(holder.build, part)[0] == "writing":
        raise TopicError("Slate is already writing that. It'll show up here when it's ready.", 409)
    if part == "lesson" and not lesson_service.can_write_lesson(skill_id):
        raise TopicError("Writing a lesson on this topic needs a Claude API key. Add one in Settings.", 409)
    if part == "problems" and not get_llm().available:
        raise TopicError("Writing problems for this topic needs a Claude API key. Add one in Settings.", 409)
    _mark(holder, part, "queued")
    return (part,)


# --- writing a topic's lesson and problems (background) ------------------------------------------


def _write_problems(db: Session, user: User, topic: Topic, llm) -> int:
    rows = list(db.scalars(select(MaterialProblem).where(
        MaterialProblem.user_id == user.id, MaterialProblem.skill_id == topic.id, MaterialProblem.status == "ready",
    ).order_by(MaterialProblem.origin, MaterialProblem.position)))
    if topic.origin == "added" and not rows:
        plan = plan_topic(llm, name=topic.title, count=NEW_TOPIC_PROBLEMS)
        if not plan.is_math:
            raise NotMath(topic.title)
        if plan.title.strip():
            topic.title = plan.title.strip()[:120]
        if plan.summary.strip():
            topic.summary = plan.summary.strip()
        skill = db.get(Skill, topic.id)
        if skill is not None:
            skill.title, skill.summary = topic.title, topic.summary
        register_extra(materials.topic_spec(topic))
        return len(materials.store_written(db, user.id, topic.id, plan.problems))
    want = max(NEW_TOPIC_PROBLEMS - len(rows), 0) if len(rows) < MIN_PROBLEMS else 0
    if not want:
        return 0
    return len(materials.add_variants(db, user.id, topic.id, want, rows, llm=llm, spread=True))


def _fail_part(db: Session, user_id: uuid.UUID, skill_id: str, part: str, message: str) -> None:
    db.rollback()
    holder = _holder(db, user_id, skill_id)
    if holder is not None:
        _mark(holder, part, "failed", message)
    db.commit()


def build_topic(skill_id: str, user_id: uuid.UUID, parts: tuple[str, ...] = ("problems", "lesson"), *,
                llm=None, force: bool = False) -> None:
    """Write a topic's problems and then its lesson (which teaches toward those problems)."""
    llm = llm if llm is not None else get_llm()
    with Session(get_engine()) as db:
        user = db.get(User, user_id)
        holder = _holder(db, user_id, skill_id)
        if user is None or holder is None:
            return
        if "problems" in parts and isinstance(holder, Topic):
            _mark(holder, "problems", "pending")
            db.commit()
            try:
                kept = _write_problems(db, user, holder, llm)
                _mark(holder, "problems", "done")
                db.commit()
                log.info("wrote %d checked problems for %s", kept, skill_id)
            except NotMath:
                _fail_part(db, user_id, skill_id, "problems",
                           "That doesn't look like a math topic Slate can teach. You can remove it.")
                if holder.origin == "added":
                    _fail_part(db, user_id, skill_id, "lesson", "There's no lesson for something that isn't math.")
                    return
            except (LLMUnavailable, LLMRefused) as exc:
                _fail_part(db, user_id, skill_id, "problems",
                           f"Claude couldn't write problems just now ({exc}). Try again in a minute.")
            except Exception:
                log.exception("writing problems for %s failed", skill_id)
                _fail_part(db, user_id, skill_id, "problems", "Something went wrong writing problems. Try again.")
        if "lesson" in parts:
            holder = _holder(db, user_id, skill_id)
            if holder is None:
                return
            if not force and has_lesson(db, user_id, skill_id):
                _mark(holder, "lesson", "done")
                db.commit()
                return
            _mark(holder, "lesson", "pending")
            db.commit()
            try:
                lesson_service.generate_for_topic(db, user, skill_id, llm=llm)
                _mark(_holder(db, user_id, skill_id), "lesson", "done")
                db.commit()
            except lesson_service.LessonError as exc:
                _fail_part(db, user_id, skill_id, "lesson", str(exc))
            except Exception:
                log.exception("writing a lesson for %s failed", skill_id)
                _fail_part(db, user_id, skill_id, "lesson", "Something went wrong writing the lesson. Try again.")


def build_lessons_for_source(source_id: uuid.UUID, *, llm=None) -> None:
    """After a source is read: problems where a topic has too few, and a lesson for each topic that has none."""
    llm = llm if llm is not None else get_llm()
    if not llm.available:
        return
    plan: list[tuple[str, tuple[str, ...]]] = []
    with Session(get_engine()) as db:
        source = db.get(Source, source_id)
        if source is None:
            return
        user_id = source.user_id
        covered: list[str] = []
        for chunk in source.chunks:
            for skill_id, score in sorted((chunk.skills or {}).items(), key=lambda kv: -float(kv[1])):
                if float(score) >= MIN_SOURCE_SCORE and skill_id not in covered:
                    covered.append(skill_id)
        for skill_id in covered:
            holder = _holder(db, user_id, skill_id)
            if holder is None:
                continue  # a built-in skill the reading didn't file problems under
            parts: list[str] = []
            if isinstance(holder, Topic):
                ready = db.scalar(select(func.count()).select_from(MaterialProblem).where(
                    MaterialProblem.user_id == user_id, MaterialProblem.skill_id == skill_id,
                    MaterialProblem.status == "ready"))
                if ready < MIN_PROBLEMS:
                    parts.append("problems")
            if not has_lesson(db, user_id, skill_id):
                parts.append("lesson")
            parts = [p for p in parts if _part(holder.build, p)[0] != "writing"]
            if parts:
                for part in parts:
                    _mark(holder, part, "queued")
                plan.append((skill_id, tuple(parts)))
        plan = plan[:MAX_LESSONS_PER_SOURCE]
        db.commit()
    for skill_id, parts in plan:
        build_topic(skill_id, user_id, parts, llm=llm)


# --- one topic's page -------------------------------------------------------------------------


def _results(db: Session, user_id: uuid.UUID, skill_id: str) -> dict[str, str]:
    """How the student did on each problem they tried, by signature: solved or missed."""
    out: dict[str, str] = {}
    rows = db.execute(select(Problem.signature, Attempt.status).join(Problem, Problem.id == Attempt.problem_id)
                      .where(Attempt.user_id == user_id, Attempt.skill_id == skill_id)).all()
    for signature, status in rows:
        if status == "correct":
            out[signature] = "solved"
        else:
            out.setdefault(signature, "missed")
    return out


def _problems(db: Session, user: User, skill_id: str) -> list[dict]:
    rows = list(db.scalars(select(MaterialProblem).where(
        MaterialProblem.user_id == user.id, MaterialProblem.skill_id == skill_id,
    ).order_by(MaterialProblem.origin, MaterialProblem.position)))
    titles = dict(db.execute(select(Source.id, Source.title).where(
        Source.id.in_({r.source_id for r in rows if r.source_id}))).all()) if rows else {}
    results = _results(db, user.id, skill_id)
    return [{
        "id": str(r.id),
        "label": r.label,
        "statement": r.statement or r.prompt,
        "kind": KIND_INFO[r.kind].title if r.kind in KIND_INFO else "Other",
        "difficulty": r.difficulty,
        "origin": r.origin,
        "source": {"id": str(r.source_id), "title": titles.get(r.source_id, "")} if r.source_id else None,
        "status": r.status,
        "reason": r.reason,
        "result": results.get(r.signature, "new"),
    } for r in rows]


def _mistakes(db: Session, user_id: uuid.UUID, skill_id: str) -> list[dict]:
    from slate_skills.core.mistakes import mistake_type

    counts = db.execute(select(MistakeTag.tag, func.count(), func.max(MistakeTag.where_to_look))
                        .where(MistakeTag.user_id == user_id, MistakeTag.skill_id == skill_id)
                        .group_by(MistakeTag.tag).order_by(func.count().desc()).limit(3)).all()
    return [{"tag": tag, "label": mistake_type(tag).label, "count": count, "example": example}
            for tag, count, example in counts]


def topic_view(db: Session, user: User, skill_id: str) -> dict:
    try:
        skill = get_skill(skill_id)
    except KeyError:
        raise TopicError("Topic not found.") from None
    if not is_builtin(skill_id) and not materials.owns_topic(db, user.id, skill_id):
        raise TopicError("Topic not found.")
    card = cards(db, user, [skill_id])[0]
    lessons = sorted(lesson_service.visible_lessons(db, user, [skill_id]),
                     key=lambda lesson: (lesson.user_id is None, -lesson.created_at.timestamp()))
    sheets = [w for w in db.scalars(select(Worksheet).where(Worksheet.user_id == user.id, Worksheet.mode == "practice")
                                    .order_by(Worksheet.updated_at.desc()))
              if w.skill_ids == [skill_id]][:MAX_TOPIC_WORKSHEETS]
    return {
        **card,
        "formula": {"title": skill.formula.title, "latex": skill.formula.latex, "note": skill.formula.note}
        if skill.formula.latex else None,
        "lessons": [lesson_service.lesson_summary(db, user, lesson) for lesson in lessons],
        "problem_list": _problems(db, user, skill_id),
        "worksheets": [worksheet_summary(w) for w in sheets],
        "mistakes": _mistakes(db, user.id, skill_id),
    }
