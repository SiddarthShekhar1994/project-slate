"""Store what was read from a source, and serve its problems to practice.

    ready source -> Claude reads topics and problems -> each problem checked
    (SymPy's key must agree with Claude's answer) -> stored, topics resolved
    -> similar problems written for the topics Slate has no templates for

Topics that match a built-in skill use it. Every other topic becomes the
student's own skill: a row in ``skills`` (so attempts, mistakes and review
cards can point at it) plus a ``topics`` row, registered with the skills
package so the rest of Slate finds it by id.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

from slate_skills import get_skill, is_builtin, register_extra, set_extra_resolver
from slate_skills.core.types import FormulaEntry, HintLadder, SkillSpec
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...db import get_engine
from ...models import MaterialProblem, Problem, Skill, Source, SourceChunk, Topic, TopicPin, User
from .. import sandbox
from ..llm import LLMRefused, LLMUnavailable, get_llm
from ..problem_gen import VerifiedProblem
from ..storage import get_storage
from .kinds import KIND_INFO
from .problems import verified
from .read import Block, ProblemOut, TopicOut, read_material, spec_of
from .variants import write_variants
from .verify import check, usable_hints

log = logging.getLogger(__name__)

CHECK_TIMEOUT = 30.0
MAX_SHEET = 30
MAX_VARIANT_GROUPS = 8
STALE_READING = timedelta(minutes=15)
TOPIC_PREFIX = "mine"
# Kinds that exercise the derivative rules, so they may count toward a built-in derivative skill.
DERIVATIVE_KINDS = ("derivative", "implicit_derivative", "tangent_line", "linear_approx")
KIND_TOPICS = {
    "derivative": "Derivatives", "implicit_derivative": "Implicit differentiation", "tangent_line": "Tangent lines",
    "linear_approx": "Linear approximation", "limit": "Limits", "antiderivative": "Antiderivatives",
    "definite_integral": "Definite integrals", "solve": "Solving equations", "critical_points": "Critical points",
    "extremum": "Absolute extrema and optimization", "related_rates": "Related rates", "other": "Other problems",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- topics as skills ------------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "topic"


def topic_spec(topic: Topic) -> SkillSpec:
    """How the rest of Slate sees a topic: a skill with no templates (problems come from materials)."""
    return SkillSpec(
        id=topic.id, slug=topic.id.rsplit(".", 1)[-1], title=topic.title, summary=topic.summary,
        task="differentiate", families=(), mistakes=(), hints=HintLadder("", "", ""),
        formula=FormulaEntry(title=topic.title, latex=""),
    )


def is_topic(skill_id: str) -> bool:
    return skill_id.startswith(f"{TOPIC_PREFIX}.")


def owns_topic(db: Session, user_id: uuid.UUID, skill_id: str) -> bool:
    topic = db.get(Topic, skill_id) if is_topic(skill_id) else None
    return topic is not None and topic.user_id == user_id


def register_all(db: Session) -> int:
    """Register every stored topic with the skills package (at startup)."""
    topics = list(db.scalars(select(Topic)))
    for topic in topics:
        register_extra(topic_spec(topic))
    return len(topics)


def resolve_topic(skill_id: str) -> SkillSpec | None:
    """A topic another process created since this one started."""
    if not is_topic(skill_id):
        return None
    with Session(get_engine()) as db:
        topic = db.get(Topic, skill_id)
        return topic_spec(topic) if topic is not None else None


# Any process that uses topics (the server, its background jobs, a script) finds
# ones created elsewhere on first use.
set_extra_resolver(resolve_topic)


def normalize_title(text: str) -> str:
    """For telling whether two names mean the same topic: "L'Hôpital's Rule" and "lhopitals rule" do."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"['’`]", "", plain)
    plain = re.sub(r"[^a-z0-9]+", " ", plain).strip()
    return re.sub(r"^the ", "", plain)


def find_topic(db: Session, user_id: uuid.UUID, name: str) -> Topic | None:
    """The student's topic with this name, hidden or not."""
    wanted = normalize_title(name)
    for topic in db.scalars(select(Topic).where(Topic.user_id == user_id)):
        if normalize_title(topic.title) == wanted:
            return topic
    return None


def ensure_topic(db: Session, user_id: uuid.UUID, name: str, summary: str = "", *, origin: str = "upload") -> str:
    """The id of the student's topic called ``name``, creating it if needed."""
    title = re.sub(r"\s+", " ", name).strip()[:120] or "Other problems"
    topic = find_topic(db, user_id, title)
    if topic is None:
        topic_id = f"{TOPIC_PREFIX}.{user_id.hex[:12]}.{_slug(title)}"
        topic = db.get(Topic, topic_id)
    if topic is None:
        db.add(Skill(id=topic_id, course_id="materials", unit_id="materials", slug=_slug(title)[:60], title=title,
                     summary=summary.strip(), position=10_000))
        db.flush()
        topic = Topic(id=topic_id, user_id=user_id, title=title, summary=summary.strip(), origin=origin)
        db.add(topic)
        db.flush()
    elif topic.hidden:
        # Removed from the dashboard earlier, and now it's back in an upload or asked for again.
        topic.hidden = False
    if summary.strip() and not topic.summary:
        topic.summary = summary.strip()
    register_extra(topic_spec(topic))
    return topic.id


def pin_skill(db: Session, user_id: uuid.UUID, skill_id: str) -> None:
    """Put a built-in skill on the student's dashboard."""
    if db.get(TopicPin, (user_id, skill_id)) is None:
        db.add(TopicPin(user_id=user_id, skill_id=skill_id))
        db.flush()


def note_topic(db: Session, user_id: uuid.UUID, skill_id: str) -> None:
    """A source covers this topic: a built-in skill goes on the student's dashboard.

    (The student's own topics are on it already; which sources cover a topic
    is read from the chunks the reading scored for it.)"""
    if is_builtin(skill_id):
        pin_skill(db, user_id, skill_id)


def _resolve(db: Session, user_id: uuid.UUID, topic: TopicOut) -> str:
    builtin = topic.builtin.strip()
    if builtin and builtin != "none" and is_builtin(builtin):
        return builtin
    return ensure_topic(db, user_id, topic.name, topic.summary)


def _skill_for(db: Session, user_id: uuid.UUID, problem: ProblemOut, topics: dict[str, str]) -> str:
    skill_id = topics.get(problem.topic.strip().lower())
    if skill_id is None:
        return ensure_topic(db, user_id, KIND_TOPICS[problem.kind])
    if is_builtin(skill_id) and problem.kind not in DERIVATIVE_KINDS:
        # The built-in skills are derivative rules; a limit filed under one gets its own topic.
        return ensure_topic(db, user_id, KIND_TOPICS[problem.kind])
    return skill_id


# --- checking and storing problems ----------------------------------------------------------


def _payload(problem: ProblemOut) -> dict:
    return {
        "spec": spec_of(problem),
        "answer": problem.answer,
        "statement": problem.statement,
        "word": problem.word,
        "steps": [s.model_dump() for s in problem.steps],
        "difficulty": problem.difficulty,
    }


def _checked_row(problem: ProblemOut, *, user_id: uuid.UUID, skill_id: str, origin: str, position: int,
                 source_id: uuid.UUID | None = None, chunk_id: uuid.UUID | None = None,
                 parent_id: uuid.UUID | None = None) -> MaterialProblem:
    """Check one problem in the sandbox and make its row, whatever the outcome."""
    payload = _payload(problem)
    base = {"user_id": user_id, "source_id": source_id, "chunk_id": chunk_id, "parent_id": parent_id,
            "skill_id": skill_id, "origin": origin, "label": (problem.label or "").strip()[:40] or None,
            "position": position, "kind": problem.kind, "statement": problem.statement.strip(),
            "claimed": problem.answer.strip(), "difficulty": min(4, max(1, int(problem.difficulty or 2)))}
    if problem.kind == "other":
        reason = problem.reason.strip() or "A computer can't check this kind of problem."
        return MaterialProblem(**base, status="unsupported", reason=reason, prompt=problem.statement.strip(),
                               params={"spec": {"kind": "other"}, "steps": payload["steps"]}, hints=[],
                               verification={"ok": False, "oracle": "none", "method": "none", "checks": []},
                               signature=_signature_text(problem.statement))
    try:
        result = sandbox.run(check, payload, timeout=CHECK_TIMEOUT)
    except sandbox.SandboxTimeout:
        result = {"ok": False, "params": None, "reason": "SymPy took too long to work this one out.",
                  "report": {"ok": False, "oracle": "none", "method": "none",
                             "checks": [{"name": "oracle", "passed": False, "detail": "timeout"}]}}
    except sandbox.SandboxError as exc:
        result = {"ok": False, "params": None, "reason": "Slate couldn't check this one.",
                  "report": {"ok": False, "oracle": "none", "method": "none",
                             "checks": [{"name": "oracle", "passed": False, "detail": str(exc)[:300]}]}}
    params = result.get("params") or {"spec": payload["spec"], "steps": payload["steps"]}
    return MaterialProblem(
        **base,
        status="ready" if result["ok"] else "unchecked",
        reason=result.get("reason", ""),
        prompt=result.get("prompt") or problem.statement.strip(),
        params=params,
        key_latex=result.get("key_latex"),
        answer_kind=result.get("answer"),
        hints=usable_hints(problem.kind, problem.hints),
        verification=result["report"],
        signature=result.get("signature") or _signature_text(problem.statement),
    )


def _signature_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(f"text|{text.strip()}".encode()).hexdigest()[:24]


def store_reading(db: Session, source: Source, chunks: list[SourceChunk], topics: list[TopicOut],
                  problems: list[ProblemOut]) -> list[MaterialProblem]:
    """Replace the source's sheet problems with these, and point its chunks at the topics found."""
    user_id = source.user_id
    db.execute(delete(MaterialProblem).where(MaterialProblem.source_id == source.id,
                                             MaterialProblem.origin == "sheet"))
    by_name = {t.name.strip().lower(): _resolve(db, user_id, t) for t in topics}
    for skill_id in by_name.values():
        note_topic(db, user_id, skill_id)
    rows = []
    for position, problem in enumerate(problems):
        skill_id = _skill_for(db, user_id, problem, by_name)
        note_topic(db, user_id, skill_id)
        chunk = chunks[problem.chunk - 1] if 1 <= problem.chunk <= len(chunks) else None
        row = _checked_row(problem, user_id=user_id, skill_id=skill_id, origin="sheet", position=position,
                           source_id=source.id, chunk_id=chunk.id if chunk else None)
        db.add(row)
        rows.append(row)
        if chunk is not None:
            # The material shows this topic: lessons and practice can now cite this chunk for it.
            scores = dict(chunk.skills or {})
            scores[skill_id] = max(float(scores.get(skill_id, 0.0)), 0.9)
            chunk.skills = scores
            chunk.top_score = max(scores.values())
    # Topics a syllabus names, with no problems, still count as covered.
    if chunks:
        for skill_id in by_name.values():
            first = chunks[0]
            if not any(r.skill_id == skill_id for r in rows):
                scores = dict(first.skills or {})
                scores[skill_id] = max(float(scores.get(skill_id, 0.0)), 0.6)
                first.skills = scores
                first.top_score = max(scores.values())
    db.flush()
    return rows


def read_source(source_id: uuid.UUID, *, llm=None, variants: bool = True) -> None:
    """Read a ready source's topics and problems. Runs in the background after processing."""
    from ..ingest.extract import page_images
    from ..sources import KIND_LABELS

    llm = llm if llm is not None else get_llm()
    with Session(get_engine()) as db:
        source = db.get(Source, source_id)
        if source is None or source.status != "ready":
            return
        if not llm.available:
            source.reading = {"status": "no_key", "at": _now().isoformat()}
            db.commit()
            return
        source.reading = {"status": "pending", "at": _now().isoformat()}
        db.commit()
        try:
            chunks = list(source.chunks)
            blocks = [Block(i + 1, c.locator, c.text) for i, c in enumerate(chunks)]
            images = page_images(get_storage().get(source.storage_key), source.mime)
            known = [t.title for t in db.scalars(select(Topic).where(Topic.user_id == source.user_id))]
            reading = read_material(llm, title=source.title, kind_label=KIND_LABELS[source.kind], blocks=blocks,
                                    images=images, known=known)
            rows = store_reading(db, source, chunks, reading.topics, reading.problems)
            source.reading = {"status": "done", "at": _now().isoformat(), "model": llm.model}
            db.commit()
            log.info("read %d problems (%d checked) from source %s", len(rows),
                     sum(r.status == "ready" for r in rows), source_id)
        except (LLMUnavailable, LLMRefused) as exc:
            db.rollback()
            source = db.get(Source, source_id)
            source.reading = {"status": "failed", "at": _now().isoformat(),
                              "error": f"Claude couldn't read it ({exc}). Try again in a minute."}
            db.commit()
            return
        except Exception:
            log.exception("reading source %s failed", source_id)
            db.rollback()
            source = db.get(Source, source_id)
            source.reading = {"status": "failed", "at": _now().isoformat(),
                              "error": "Something went wrong reading the problems. Try again."}
            db.commit()
            return
    if variants:
        fill_variants(source_id, llm=llm)
    from ..topics import build_lessons_for_source

    build_lessons_for_source(source_id, llm=llm)


def needs_reading(source: Source, llm_available: bool) -> bool:
    """A ready source that was never read, waited for a key that is now set, or stalled."""
    if source.status != "ready" or not llm_available:
        return False
    reading = source.reading or {}
    status = reading.get("status")
    if status in (None, "no_key"):
        return True
    if status == "pending":
        try:
            started = datetime.fromisoformat(reading["at"])
        except (KeyError, ValueError):
            return True
        return _now() - started > STALE_READING
    return False


def mark_pending(db: Session, source: Source) -> None:
    source.reading = {"status": "pending", "at": _now().isoformat()}


# --- similar problems --------------------------------------------------------------------------


def _example(row: MaterialProblem) -> dict:
    return {"kind": row.kind, "statement": row.statement or row.prompt, "answer": row.claimed}


def add_variants(db: Session, user_id: uuid.UUID, skill_id: str, count: int, examples: list[MaterialProblem],
                 *, llm=None, spread: bool = False) -> list[MaterialProblem]:
    """Have Claude write ``count`` problems for ``skill_id`` like ``examples``; keep the ones that check out."""
    llm = llm if llm is not None else get_llm()
    if not llm.available:
        return []
    skill = get_skill(skill_id)
    try:
        written = write_variants(llm, topic=skill.title, summary=skill.summary,
                                 examples=[_example(r) for r in examples[:4]], count=count, spread=spread)
    except (LLMUnavailable, LLMRefused) as exc:
        log.info("couldn't write variants for %s: %s", skill_id, exc)
        return []
    return store_written(db, user_id, skill_id, written, parent=examples[0].id if examples else None)


def store_written(db: Session, user_id: uuid.UUID, skill_id: str, written: list[ProblemOut], *,
                  parent: uuid.UUID | None = None) -> list[MaterialProblem]:
    """Check problems Claude wrote for a topic and keep the new ones that check out."""
    start = (db.scalar(select(MaterialProblem.position).where(MaterialProblem.user_id == user_id)
                       .order_by(MaterialProblem.position.desc()).limit(1)) or 0) + 1
    known = set(db.scalars(select(MaterialProblem.signature).where(MaterialProblem.user_id == user_id,
                                                                    MaterialProblem.skill_id == skill_id)))
    kept = []
    for offset, problem in enumerate(written):
        row = _checked_row(problem, user_id=user_id, skill_id=skill_id, origin="variant", position=start + offset,
                           parent_id=parent)
        if row.status != "ready" or row.signature in known:
            continue
        known.add(row.signature)
        db.add(row)
        kept.append(row)
    db.flush()
    return kept


def fill_variants(source_id: uuid.UUID, *, llm=None) -> None:
    """Write similar problems for the source's topics that have no templates, ahead of practice."""
    llm = llm if llm is not None else get_llm()
    if not llm.available:
        return
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(MaterialProblem).where(MaterialProblem.source_id == source_id,
                                                             MaterialProblem.status == "ready")))
        groups: dict[tuple[str, str], list[MaterialProblem]] = {}
        for row in rows:
            if row.skill_id and not (is_builtin(row.skill_id) and row.kind in ("derivative", "implicit_derivative")):
                groups.setdefault((row.skill_id, row.kind), []).append(row)
        for (skill_id, kind), examples in list(groups.items())[:MAX_VARIANT_GROUPS]:
            have = len(list(db.scalars(select(MaterialProblem.id).where(
                MaterialProblem.user_id == examples[0].user_id, MaterialProblem.skill_id == skill_id,
                MaterialProblem.kind == kind, MaterialProblem.origin == "variant",
                MaterialProblem.status == "ready"))))
            want = min(6, 2 * len(examples)) - have
            if want > 0:
                add_variants(db, examples[0].user_id, skill_id, want, examples, llm=llm)
                db.commit()


# --- serving problems ------------------------------------------------------------------------


def problem_from_row(row: MaterialProblem) -> VerifiedProblem:
    params = {**row.params, "material_id": str(row.id), "label": row.label or "",
              "chunk_id": str(row.chunk_id) if row.chunk_id else None,
              "source_id": str(row.source_id) if row.source_id else None}
    return verified(params, row.verification, row.hints, row.signature, skill_id=row.skill_id or "",
                    origin=row.origin)


def load(row: Problem) -> VerifiedProblem:
    """A stored practice problem that came from course materials."""
    return verified(dict(row.params), row.verification, row.hints, row.signature, skill_id=row.skill_id,
                    origin=row.origin)


def is_material(row: Problem) -> bool:
    return row.family.startswith("material:")


def _ready(db: Session, user_id: uuid.UUID, *conditions) -> list[MaterialProblem]:
    return list(db.scalars(select(MaterialProblem).where(MaterialProblem.user_id == user_id,
                                                         MaterialProblem.status == "ready", *conditions)
                           .order_by(MaterialProblem.origin, MaterialProblem.position)))


def seen_signatures(db: Session, user_id: uuid.UUID, skill_id: str) -> set[str]:
    return set(db.scalars(select(Problem.signature).where(Problem.user_id == user_id, Problem.skill_id == skill_id)))


def topic_problems(db: Session, user: User, skill_id: str, count: int, exclude: Iterable[str] = (),
                   *, llm=None) -> list[VerifiedProblem]:
    """``count`` problems for one of the student's topics, unseen ones first, easy to hard."""
    seen = set(exclude) | seen_signatures(db, user.id, skill_id)
    rows = _ready(db, user.id, MaterialProblem.skill_id == skill_id)
    fresh = [r for r in rows if r.signature not in seen]
    if len(fresh) < count:
        fresh += add_variants(db, user.id, skill_id, count - len(fresh), rows, llm=llm)
    if len(fresh) < count:
        # Better a problem seen before than a short worksheet.
        fresh += [r for r in rows if r not in fresh][: count - len(fresh)]
    picked = sorted(fresh[:count], key=lambda r: r.difficulty)
    return [problem_from_row(r) for r in picked]


def similar_problem(db: Session, user: User, skill_id: str, current: VerifiedProblem, *, attempt: int,
                    llm=None) -> VerifiedProblem | None:
    """A new problem like ``current`` (a material problem) for the retry loop, or ``None``."""
    from ..problem_gen import GenerationError, derive_seed, generate

    kind = current.built.params["spec"]["kind"]
    seen = seen_signatures(db, user.id, skill_id) | {current.signature}
    if is_builtin(skill_id):
        skill = get_skill(skill_id)
        task = {"derivative": "differentiate", "implicit_derivative": "implicit_differentiate"}.get(kind)
        if task == skill.task:
            levels = skill.difficulties
            level = min(levels, key=lambda d: abs(d - current.difficulty))
            try:
                return generate(skill_id, level, derive_seed(int(current.signature[:8], 16), f"material:{attempt}"),
                                exclude=seen)
            except GenerationError:
                pass
    rows = _ready(db, user.id, MaterialProblem.skill_id == skill_id)
    same_kind = [r for r in rows if r.kind == kind and r.signature not in seen]
    other_kind = [r for r in rows if r.kind != kind and r.signature not in seen]
    pool = same_kind or other_kind
    if not pool:
        examples = [r for r in rows if r.kind == kind] or rows
        pool = add_variants(db, user.id, skill_id, 3, examples, llm=llm)
    if not pool:
        return None
    best = min(pool, key=lambda r: abs(r.difficulty - current.difficulty))
    return problem_from_row(best)


def sheet_rows(db: Session, source: Source) -> list[MaterialProblem]:
    return list(db.scalars(select(MaterialProblem).where(MaterialProblem.source_id == source.id,
                                                         MaterialProblem.origin == "sheet")
                           .order_by(MaterialProblem.position)))


# --- views -----------------------------------------------------------------------------------------


def _skill_title(skill_id: str | None) -> str:
    if not skill_id:
        return "Other problems"
    try:
        return get_skill(skill_id).title
    except KeyError:
        return skill_id


def reading_view(db: Session, source: Source) -> dict:
    """What the source card shows about the problems read from it."""
    reading = source.reading or {}
    rows = sheet_rows(db, source)
    topics: dict[str, dict] = {}
    for row in rows:
        key = row.skill_id or ""
        entry = topics.setdefault(key, {"id": key or None, "title": _skill_title(row.skill_id),
                                        "builtin": bool(key) and is_builtin(key), "problems": 0, "ready": 0})
        entry["problems"] += 1
        entry["ready"] += row.status == "ready"
    return {
        "status": reading.get("status") or "none",
        "error": reading.get("error"),
        "problems": len(rows),
        "ready": sum(r.status == "ready" for r in rows),
        "topics": list(topics.values()),
        "not_checked": [
            {"label": r.label, "kind": KIND_INFO[r.kind].title if r.kind in KIND_INFO else "Other",
             "reason": r.reason, "statement": r.statement}
            for r in rows if r.status != "ready"
        ],
    }


def topics_view(db: Session, user: User) -> list[dict]:
    """The student's own topics with how many checked problems each has."""
    topics = list(db.scalars(select(Topic).where(Topic.user_id == user.id).order_by(Topic.created_at)))
    out = []
    for topic in topics:
        rows = _ready(db, user.id, MaterialProblem.skill_id == topic.id)
        sources = sorted({r.source_id for r in rows if r.source_id}, key=str)
        out.append({
            "id": topic.id, "title": topic.title, "summary": topic.summary,
            "problems": len(rows), "from_sheets": sum(r.origin == "sheet" for r in rows),
            "sources": [s.title for s in db.scalars(select(Source).where(Source.id.in_(sources)))] if sources else [],
        })
    return out
