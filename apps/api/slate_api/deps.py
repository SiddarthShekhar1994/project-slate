"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User
from .services.auth import local_user, user_for_token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    if settings.desktop:
        return local_user(db)
    user = user_for_token(db, request.cookies.get(settings.session_cookie))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return user
