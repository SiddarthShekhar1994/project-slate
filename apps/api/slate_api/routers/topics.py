"""The student's topics: the dashboard, adding a topic by name, and each topic's page."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import MaterialProblem, User
from ..schemas import TopicIn, TopicPracticeIn
from ..services import practice, topics

router = APIRouter(prefix="/topics", tags=["topics"])


def _fail(exc: topics.TopicError | practice.PracticeError) -> HTTPException:
    return HTTPException(exc.code, str(exc))


@router.get("")
def dashboard(background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    # Lessons and problems Slate was writing when the app last closed, or never wrote, get written now.
    work = topics.pending_work(db, user)
    if work:
        db.commit()
        background.add_task(topics.build_all, user.id, work)
    return topics.dashboard(db, user)


@router.post("", status_code=201)
def add(body: TopicIn, background: BackgroundTasks, user: User = Depends(current_user),
        db: Session = Depends(get_db)) -> dict:
    """Add a topic by name. Slate writes its problems and lesson in the background."""
    try:
        skill_id, parts = topics.add_topic(db, user, body.name)
    except topics.TopicError as exc:
        raise _fail(exc) from None
    db.commit()
    if parts:
        background.add_task(topics.build_topic, skill_id, user.id, parts)
    return topics.cards(db, user, [skill_id])[0]


@router.get("/{topic_id}")
def get_topic(topic_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return topics.topic_view(db, user, topic_id)
    except topics.TopicError as exc:
        raise _fail(exc) from None


@router.delete("/{topic_id}", status_code=204)
def remove(topic_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    try:
        topics.remove_topic(db, user, topic_id)
    except topics.TopicError as exc:
        raise _fail(exc) from None
    db.commit()


@router.post("/{topic_id}/lesson", status_code=202)
def write_lesson(topic_id: str, background: BackgroundTasks, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    """Write a (new) lesson for the topic, in the background."""
    try:
        parts = topics.request_build(db, user, topic_id, "lesson")
    except topics.TopicError as exc:
        raise _fail(exc) from None
    db.commit()
    background.add_task(topics.build_topic, topic_id, user.id, parts, force=True)
    return topics.cards(db, user, [topic_id])[0]


@router.post("/{topic_id}/problems", status_code=202)
def write_problems(topic_id: str, background: BackgroundTasks, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> dict:
    try:
        parts = topics.request_build(db, user, topic_id, "problems")
    except topics.TopicError as exc:
        raise _fail(exc) from None
    db.commit()
    background.add_task(topics.build_topic, topic_id, user.id, parts)
    return topics.cards(db, user, [topic_id])[0]


@router.post("/{topic_id}/practice", status_code=201)
def start_practice(topic_id: str, body: TopicPracticeIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> dict:
    """A worksheet on this topic: chosen problems from the student's materials, or a fresh set easy to hard."""
    try:
        view = topics.topic_view(db, user, topic_id)
        if body.problem_ids:
            wanted = [str(i) for i in body.problem_ids]
            rows = {str(r.id): r for r in db.scalars(select(MaterialProblem).where(
                MaterialProblem.user_id == user.id, MaterialProblem.skill_id == topic_id,
                MaterialProblem.status == "ready", MaterialProblem.id.in_(body.problem_ids)))}
            chosen = [rows[i] for i in wanted if i in rows]
            title = view["title"] if len(chosen) != 1 else f"{view['title']}: one problem"
            sheet = practice.create_problem_worksheet(db, user, chosen, title)
        else:
            sheet = practice.create_worksheet(db, user, [topic_id], body.count or 8, title=f"{view['title']} practice")
    except (topics.TopicError, practice.PracticeError) as exc:
        raise _fail(exc) from None
    db.commit()
    return practice.worksheet_summary(sheet)
