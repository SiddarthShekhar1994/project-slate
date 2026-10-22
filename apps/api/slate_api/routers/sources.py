from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..services import practice, sources
from ..services.llm import get_llm
from ..services.materials import service as materials

router = APIRouter(prefix="/sources", tags=["sources"])

READ_CHUNK = 1024 * 1024


def _fail(exc: sources.SourceError) -> HTTPException:
    return HTTPException(exc.code, str(exc))


async def _read_limited(upload: UploadFile) -> bytes:
    """Read the upload but stop as soon as it passes the size limit."""
    parts: list[bytes] = []
    total = 0
    while chunk := await upload.read(READ_CHUNK):
        total += len(chunk)
        if total > sources.MAX_UPLOAD_BYTES:
            raise HTTPException(413, "That file is larger than 50 MB. Try splitting it.")
        parts.append(chunk)
    return b"".join(parts)


@router.get("")
def list_sources(background: BackgroundTasks, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    # Sources uploaded before problems were read, or before a Claude key was set,
    # get read now, in the background.
    available = get_llm().available
    stale = [s for s in sources.user_sources(db, user) if materials.needs_reading(s, available)]
    for source in stale:
        materials.mark_pending(db, source)
    if stale:
        db.commit()
        for source in stale:
            background.add_task(materials.read_source, source.id)
    return {"sources": [sources.source_view(db, s) for s in sources.user_sources(db, user)],
            "kinds": sources.KIND_LABELS}


@router.post("", status_code=202)
async def upload(background: BackgroundTasks, file: UploadFile = File(...), kind: str | None = Form(None),
                 title: str | None = Form(None), user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    data = await _read_limited(file)
    try:
        source = sources.create_source(db, user, file.filename or "upload", data, kind or None, title or None)
    except sources.SourceError as exc:
        raise _fail(exc) from None
    db.commit()
    background.add_task(sources.process_source, source.id)
    return sources.source_view(db, source)


@router.get("/{source_id}")
def get_source(source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return sources.source_view(db, sources.get_source(db, user, source_id), with_chunks=True)
    except sources.SourceError as exc:
        raise _fail(exc) from None


@router.delete("/{source_id}", status_code=204)
def delete(source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    try:
        sources.delete_source(db, user, source_id)
    except sources.SourceError as exc:
        raise _fail(exc) from None
    db.commit()


@router.post("/{source_id}/reprocess", status_code=202)
def reprocess(source_id: uuid.UUID, background: BackgroundTasks, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict:
    try:
        source = sources.get_source(db, user, source_id)
    except sources.SourceError as exc:
        raise _fail(exc) from None
    source.status, source.error = "processing", None
    db.commit()
    background.add_task(sources.process_source, source.id)
    return sources.source_view(db, source)


@router.post("/{source_id}/read", status_code=202)
def read_again(source_id: uuid.UUID, background: BackgroundTasks, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:
    """Read the source's problems and topics again (after a failure, or with a key that is new)."""
    try:
        source = sources.get_source(db, user, source_id)
    except sources.SourceError as exc:
        raise _fail(exc) from None
    if source.status != "ready":
        raise HTTPException(409, "That source isn't ready yet.")
    if not get_llm().available:
        raise HTTPException(409, "Add a Claude API key on the Settings page so Slate can read the problems.")
    materials.mark_pending(db, source)
    db.commit()
    background.add_task(materials.read_source, source.id)
    return sources.source_view(db, source)


@router.post("/{source_id}/practice", status_code=201)
def practice_sheet(source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """A worksheet of the problems on this source that Slate could check."""
    try:
        sheet = practice.create_sheet_worksheet(db, user, source_id)
    except sources.SourceError as exc:
        raise _fail(exc) from None
    except practice.PracticeError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    db.commit()
    return practice.worksheet_view(db, sheet)
