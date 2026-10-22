from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..services.materials import service as materials

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/topics")
def topics(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Topics found in the student's materials that no built-in skill covers."""
    return {"topics": materials.topics_view(db, user)}
