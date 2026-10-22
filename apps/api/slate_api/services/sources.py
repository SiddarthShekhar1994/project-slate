"""Uploaded sources: storing them, processing them, and what they were used for.

Processing runs after the upload request returns:

    stored file -> extract -> OCR the pages that need it -> chunk by topic
    -> score each chunk against every skill -> note the notation it uses
    -> (with a Claude key) read the problems and topics, see ``materials``

A failure marks the source ``failed`` with a message the student can act on;
it never leaves a half-written set of chunks behind.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePath

from slate_skills import get_skill
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_engine
from ..models import Citation, Lesson, Source, SourceChunk, User
from .ingest.types import PROFESSOR_KINDS
from .storage import get_storage

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
KIND_LABELS = {
    "slides": "Lecture slides",
    "textbook": "Textbook",
    "syllabus": "Syllabus",
    "exam": "Past exam",
    "notes": "Notes",
    "other": "Other",
}
EXTENSIONS = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MIN_SKILL_SCORE = 0.3


class SourceError(ValueError):
    def __init__(self, message: str, code: int = 422):
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def guess_kind(filename: str, mime: str) -> str:
    """A sensible default for the source kind; the student can always override it."""
    name = filename.lower()

    def has(*words: str) -> bool:
        # Whole words only, so "example" is not an exam and "latest" is not a test.
        return any(re.search(rf"(?<![a-z]){w}(?![a-z])", name) for w in words)

    if has("syllabus", "outline"):
        return "syllabus"
    if has("exam", "exams", "midterm", "midterms", "final", "finals", "quiz", "quizzes", "test", "tests"):
        return "exam"
    if has("chapter", "textbook", "ch", "section", "sec"):
        return "textbook"
    if mime.startswith("image/") or has("notes", "handwritten"):
        return "notes"
    if mime.endswith("presentation") or has("lecture", "lec", "slides", "week"):
        return "slides"
    return "other"


def create_source(db: Session, user: User, filename: str, data: bytes, kind: str | None, title: str | None) -> Source:
    from .ingest.extract import detect_mime

    if not data:
        raise SourceError("That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise SourceError("That file is larger than 50 MB. Try splitting it.", 413)
    mime = detect_mime(data, filename)
    if mime is None:
        raise SourceError("Slate reads PDF, PowerPoint (.pptx), Word (.docx) and photos (PNG, JPEG, WEBP).", 415)
    if kind is not None and kind not in KIND_LABELS:
        raise SourceError("Unknown source type.")
    clean_name = PurePath(filename).name[:300] or f"upload.{EXTENSIONS[mime]}"
    source = Source(
        user_id=user.id,
        title=(title or PurePath(clean_name).stem.replace("_", " ").strip())[:300] or "Untitled",
        filename=clean_name,
        kind=kind or guess_kind(clean_name, mime),
        mime=mime,
        size_bytes=len(data),
        storage_key="pending",
        status="processing",
    )
    db.add(source)
    db.flush()
    source.storage_key = f"uploads/{user.id}/{source.id}.{EXTENSIONS[mime]}"
    get_storage().put(source.storage_key, data, mime)
    db.flush()
    return source


def process_source(source_id: uuid.UUID, *, llm=None, read: bool = True) -> None:
    """Extract, OCR, chunk, match and store, then read its problems. Runs in the background after upload."""
    from .ingest.chunk import chunk_pages
    from .ingest.extract import ExtractionError, extract
    from .ingest.match import match_skills
    from .ingest.notation import detect_notation
    from .ingest.ocr import ocr_pages

    with Session(get_engine()) as db:
        source = db.get(Source, source_id)
        if source is None:
            return
        try:
            data = get_storage().get(source.storage_key)
            extracted = extract(data, source.mime, source.filename)
            pages = ocr_pages(extracted.pages, llm=llm)
            chunks = chunk_pages(pages, source.kind)
            if not any(c.text.strip() for c in chunks):
                raise ExtractionError("Slate couldn't find any text in that file.")
            db.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
            for chunk in chunks:
                scores = match_skills(chunk.text, chunk.heading)
                db.add(SourceChunk(
                    source_id=source.id, ordinal=chunk.ordinal, heading=chunk.heading[:300],
                    locator=chunk.locator[:120], text=chunk.text, skills=scores,
                    notation=detect_notation(chunk.text), top_score=max(scores.values(), default=0.0),
                ))
            methods = sorted({p.ocr_method for p in pages if p.ocr_method})
            source.pages = extracted.page_count or len(extracted.pages)
            source.ocr_method = ", ".join(methods) or None
            if extracted.title and source.title == PurePath(source.filename).stem.replace("_", " ").strip():
                source.title = extracted.title[:300]
            source.status = "ready"
            source.error = None
        except ExtractionError as exc:
            db.rollback()
            source = db.get(Source, source_id)
            source.status, source.error = "failed", str(exc)
        except Exception:
            log.exception("processing source %s failed", source_id)
            db.rollback()
            source = db.get(Source, source_id)
            source.status, source.error = "failed", "Something went wrong reading that file. Try uploading it again."
        source.processed_at = _now()
        db.commit()
        ready = source.status == "ready"
    if ready and read:
        from .materials.service import read_source

        read_source(source_id, llm=llm)


def user_sources(db: Session, user: User) -> list[Source]:
    return list(db.scalars(select(Source).where(Source.user_id == user.id).order_by(Source.created_at.desc())))


def get_source(db: Session, user: User, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None or source.user_id != user.id:
        raise SourceError("Source not found.", 404)
    return source


def delete_source(db: Session, user: User, source_id: uuid.UUID) -> None:
    source = get_source(db, user, source_id)
    key = source.storage_key
    db.delete(source)
    db.flush()
    get_storage().delete(key)


def _skill_summary(chunks: list[SourceChunk]) -> list[dict]:
    best: dict[str, float] = {}
    for chunk in chunks:
        for skill_id, score in chunk.skills.items():
            best[skill_id] = max(best.get(skill_id, 0.0), score)
    out = []
    for skill_id, score in sorted(best.items(), key=lambda kv: -kv[1]):
        if score < MIN_SKILL_SCORE:
            continue
        try:
            out.append({"id": skill_id, "title": get_skill(skill_id).title, "score": round(score, 2)})
        except KeyError:
            continue
    return out


def used_for(db: Session, source: Source) -> dict:
    chunk_ids = select(SourceChunk.id).where(SourceChunk.source_id == source.id)
    lessons = db.execute(
        select(Lesson.id, Lesson.title).join(Citation, Citation.lesson_id == Lesson.id)
        .where(Citation.chunk_id.in_(chunk_ids)).distinct()
    ).all()
    problems = db.scalar(
        select(func.count(func.distinct(Citation.problem_id))).where(Citation.chunk_id.in_(chunk_ids),
                                                                     Citation.problem_id.is_not(None))
    ) or 0
    return {"lessons": [{"id": str(i), "title": t} for i, t in lessons], "problems": problems}


def reading_view(db: Session, source: Source) -> dict:
    from .materials.service import reading_view as view

    return view(db, source)


def source_view(db: Session, source: Source, *, with_chunks: bool = False) -> dict:
    view = {
        "id": str(source.id),
        "title": source.title,
        "filename": source.filename,
        "kind": source.kind,
        "kind_label": KIND_LABELS[source.kind],
        "status": source.status,
        "error": source.error,
        "pages": source.pages,
        "ocr": source.ocr_method,
        "size_bytes": source.size_bytes,
        "created_at": source.created_at.isoformat(),
        "file_url": f"/api/media/{source.storage_key}",
        "chunks": len(source.chunks),
        "skills": _skill_summary(source.chunks),
        "used_for": used_for(db, source),
        "reading": reading_view(db, source) if source.status == "ready" else None,
    }
    if with_chunks:
        view["chunk_list"] = [
            {"id": str(c.id), "heading": c.heading, "locator": c.locator, "excerpt": c.text[:280],
             "skills": [s for s in _skill_summary([c])]}
            for c in source.chunks
        ]
    return view


# --- using sources --------------------------------------------------------------------


def chunks_for_skill(db: Session, user_id: uuid.UUID, skill_id: str, limit: int = 6) -> list[tuple[SourceChunk, Source]]:
    """The user's best chunks for a skill, professor-written sources first at equal strength."""
    rows = db.execute(
        select(SourceChunk, Source).join(Source, Source.id == SourceChunk.source_id)
        .where(Source.user_id == user_id, Source.status == "ready")
    ).all()
    scored = []
    for chunk, source in rows:
        score = float(chunk.skills.get(skill_id, 0.0))
        if score >= MIN_SKILL_SCORE:
            bonus = 0.05 if source.kind in PROFESSOR_KINDS else 0.0
            scored.append((score + bonus, chunk, source))
    scored.sort(key=lambda s: -s[0])
    return [(c, s) for _, c, s in scored[:limit]]


def best_chunk_for_skill(db: Session, user_id: uuid.UUID, skill_id: str) -> SourceChunk | None:
    found = chunks_for_skill(db, user_id, skill_id, limit=1)
    return found[0][0] if found else None


def notation_for_user(db: Session, user_id: uuid.UUID):
    from .ingest.notation import notation_profile

    rows = db.execute(
        select(SourceChunk.id, SourceChunk.notation, Source.kind).join(Source, Source.id == SourceChunk.source_id)
        .where(Source.user_id == user_id, Source.status == "ready")
    ).all()
    observations = [(kind, str(chunk_id), notation or {}) for chunk_id, notation, kind in rows]
    return notation_profile(observations) if observations else None


def citation_view(chunk: SourceChunk | None) -> dict | None:
    if chunk is None:
        return None
    source = chunk.source
    return {"source_id": str(source.id), "title": source.title, "kind": KIND_LABELS[source.kind],
            "locator": chunk.locator}
