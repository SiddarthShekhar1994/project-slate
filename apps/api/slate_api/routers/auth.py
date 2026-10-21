from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import LoginIn, SignupIn
from ..services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_view(user: User) -> dict:
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie, token, max_age=settings.session_days * 86400, httponly=True,
        secure=settings.cookie_secure, samesite="lax", path="/",
    )


@router.post("/signup", status_code=201)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)) -> dict:
    try:
        user = auth.create_user(db, body.email, body.password, body.display_name)
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from None
    token = auth.start_session(db, user, get_settings().session_days)
    db.commit()
    _set_cookie(response, token)
    return _user_view(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict:
    try:
        user = auth.authenticate(db, body.email, body.password)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from None
    token = auth.start_session(db, user, get_settings().session_days)
    db.commit()
    _set_cookie(response, token)
    return _user_view(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    settings = get_settings()
    auth.end_session(db, request.cookies.get(settings.session_cookie))
    db.commit()
    response.delete_cookie(settings.session_cookie, path="/")


@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)) -> dict:
    """The signed-in user, or null. Never 401, so a signed-out page load is quiet.

    ``desktop`` tells the web app it is running inside the Windows app: no
    sign-in screens, a Settings page for API keys.
    """
    settings = get_settings()
    if settings.desktop:
        return {"user": _user_view(auth.local_user(db)), "desktop": True}
    user = auth.user_for_token(db, request.cookies.get(settings.session_cookie))
    return {"user": _user_view(user) if user else None, "desktop": False}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_view(user)
