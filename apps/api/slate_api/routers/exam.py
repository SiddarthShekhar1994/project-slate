from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from slate_skills import all_skills
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import ExamAnswerIn, ExamIn
from ..services import exam, practice, topics

router = APIRouter(prefix="/exam", tags=["exam"])


def _fail(exc: practice.PracticeError) -> HTTPException:
    return HTTPException(exc.code, str(exc))


@router.get("/weights")
def weights(skills: str = Query(default="", max_length=2000), user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> dict:
    """Suggested weights for the chosen topics, from the syllabus when there is one."""
    mine = topics.topic_ids(db, user.id)
    known = set(mine) | {s.id for s in all_skills()}
    chosen = [s for s in skills.split(",") if s in known] if skills else mine
    return {"weights": exam.default_weights(db, user.id, chosen), "minutes": exam.MINUTES,
            "study_factor": exam.STUDY_FACTOR}


@router.post("", status_code=201)
def create(body: ExamIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        sheet = exam.create_exam(db, user, body.weights, body.count, body.pace, body.seed)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()
    if body.pace == "study":
        return {"id": str(sheet.id), "pace": "study", "worksheet": practice.worksheet_view(db, sheet)}
    return {"id": str(sheet.id), "pace": "exam", "exam": exam.exam_view(db, sheet)}


@router.get("/{worksheet_id}")
def get(worksheet_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        sheet = exam.get_exam(db, user, worksheet_id)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    db.commit()  # a set whose time ran out is handed in on read
    return exam.exam_view(db, sheet)


@router.put("/items/{item_id}/answer")
def save_answer(item_id: uuid.UUID, body: ExamAnswerIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    try:
        item = exam.save_answer(db, user, item_id, body.answer)
    except practice.PracticeError as exc:
        db.commit()  # keep the hand-in if time had run out
        raise _fail(exc) from None
    db.commit()
    return {"id": str(item.id), "answer": item.exam_answer}


@router.post("/{worksheet_id}/finish")
def finish(worksheet_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        sheet = exam.get_exam(db, user, worksheet_id)
    except practice.PracticeError as exc:
        raise _fail(exc) from None
    exam.finish_exam(db, sheet)
    db.commit()
    return exam.exam_view(db, sheet)
