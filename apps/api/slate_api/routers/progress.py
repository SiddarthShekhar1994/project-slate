from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from slate_skills import all_skills
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import ReviewIn
from ..services import practice, progress, review

router = APIRouter(prefix="/progress", tags=["progress"])

PER_SKILL = 2


@router.get("")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return progress.progress_view(db, user.id)


@router.get("/review")
def review_queue(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return review.queue_view(db, user.id)


@router.post("/review", status_code=201)
def start_review(body: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """A short worksheet over the skills that are due, two problems each."""
    skill_ids = body.skill_ids if body.skill_ids else review.due_skill_ids(db, user.id)[:6]
    if not skill_ids:
        raise HTTPException(409, "Nothing is due for review yet.")
    try:
        sheet = practice.create_worksheet(db, user, skill_ids, PER_SKILL * len(skill_ids), mode="review",
                                          title="Review: " + ", ".join(_titles(skill_ids)))
    except practice.PracticeError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    db.commit()
    return practice.worksheet_view(db, sheet)


def _titles(skill_ids: list[str]) -> list[str]:
    from slate_skills import get_skill

    titles = [get_skill(s).title for s in skill_ids]
    return [t if i == 0 else t.lower() for i, t in enumerate(titles)]


@router.get("/formula-sheet")
def formula_sheet(skills: str = Query(default="", max_length=2000), user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> dict:
    known = {s.id for s in all_skills()}
    chosen = [s for s in skills.split(",") if s in known] if skills else sorted(known)
    return progress.formula_sheet(db, user.id, chosen)
