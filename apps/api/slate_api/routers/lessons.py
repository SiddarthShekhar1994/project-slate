from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import LessonQuestion, User
from ..schemas import AskIn, CheckpointIn, StepIn
from ..services import lessons
from ..services.ask import answer_question

router = APIRouter(prefix="/lessons", tags=["lessons"])


def _lesson(db: Session, user: User, lesson_id: uuid.UUID):
    try:
        return lessons.get_lesson(db, user, lesson_id)
    except lessons.LessonError as exc:
        raise HTTPException(exc.code, str(exc)) from None


@router.get("")
def list_lessons(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"lessons": [lessons.lesson_summary(db, user, l) for l in lessons.visible_lessons(db, user)]}


@router.get("/{lesson_id}")
def get_lesson(lesson_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return lessons.lesson_view(db, user, _lesson(db, user, lesson_id))


@router.get("/{lesson_id}/steps/{step}/audio")
async def step_audio(lesson_id: uuid.UUID, step: int, voice: str = Query(max_length=80),
                     user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    lesson = _lesson(db, user, lesson_id)
    try:
        # Synthesis is a slow network call on a cache miss; keep it off the event loop.
        return await run_in_threadpool(lessons.step_audio, lesson, step, voice)
    except lessons.LessonError as exc:
        raise HTTPException(exc.code, str(exc)) from None


@router.post("/{lesson_id}/progress", status_code=204)
def save_progress(lesson_id: uuid.UUID, body: StepIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> None:
    lesson = _lesson(db, user, lesson_id)
    try:
        lessons.save_progress(db, user, lesson, body.step)
    except lessons.LessonError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    db.commit()


@router.post("/{lesson_id}/checkpoint")
def checkpoint(lesson_id: uuid.UUID, body: CheckpointIn, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:
    lesson = _lesson(db, user, lesson_id)
    try:
        correct = lessons.answer_checkpoint(db, user, lesson, body.step, body.option)
    except lessons.LessonError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    db.commit()
    return {"correct": correct}


@router.post("/{lesson_id}/ask")
async def ask(lesson_id: uuid.UUID, body: AskIn, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict:
    lesson = _lesson(db, user, lesson_id)
    if body.step >= len(lesson.script["steps"]):
        raise HTTPException(422, "No such step.")
    result = await run_in_threadpool(answer_question, lesson.script, body.step, body.question)
    db.add(LessonQuestion(user_id=user.id, lesson_id=lesson.id, step=body.step, question=body.question,
                          answer=result["answer"], source=result["source"], verified=result["verified"]))
    db.commit()
    return {"answer": result["answer"], "verified": result["verified"], "notes": result["notes"]}
