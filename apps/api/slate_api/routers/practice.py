from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import AnswerIn, HintIn, WorksheetIn
from ..services import practice
from ..services.grading import Grade

router = APIRouter(prefix="/practice", tags=["practice"])


def _fail(exc: practice.PracticeError) -> HTTPException:
    return HTTPException(exc.code, str(exc))


def _grade_view(grade: Grade) -> dict:
    mistake = grade.mistake
    return {
        "status": grade.status,
        "latex": grade.latex,
        "message": grade.message,
        "mistake": None if mistake is None else {
            "tag": mistake.tag,
            "label": mistake.label,
            "category": mistake.category,
            "step_id": mistake.step_id,
            "step_title": mistake.step_title,
            "where_to_look": mistake.where_to_look,
        },
    }


@router.get("/worksheets")
def list_worksheets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"worksheets": [practice.worksheet_summary(w) for w in practice.recent_worksheets(db, user)]}


@router.post("/worksheets", status_code=201)
def create_worksheet(body: WorksheetIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        sheet = practice.create_worksheet(db, user, body.skill_ids, body.count or get_settings().worksheet_size,
                                          body.seed)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()
    return practice.worksheet_view(db, sheet)


@router.get("/worksheets/{worksheet_id}")
def get_worksheet(worksheet_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        sheet = practice.get_worksheet(db, user, worksheet_id)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    return practice.worksheet_view(db, sheet)


@router.post("/items/{item_id}/answer")
def answer(item_id: uuid.UUID, body: AnswerIn, user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict:
    try:
        result = practice.submit_answer(db, user, item_id, body.answer, body.duration_ms)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()
    return {
        "grade": _grade_view(result.grade),
        "item": practice.item_view(db, result.item),
        "stats": practice.stats(result.item.worksheet),
    }


@router.post("/items/{item_id}/hint")
def hint(item_id: uuid.UUID, body: HintIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        item = practice.reveal_hint(db, user, item_id, body.level)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()
    return {"item": practice.item_view(db, item)}


@router.post("/items/{item_id}/similar")
def similar(item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        item = practice.serve_similar(db, user, item_id)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()
    return {"item": practice.item_view(db, item), "stats": practice.stats(item.worksheet)}
