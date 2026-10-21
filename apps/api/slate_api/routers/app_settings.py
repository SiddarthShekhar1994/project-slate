from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..deps import current_user
from ..models import User
from ..schemas import SettingsIn
from ..services import app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _desktop_only() -> None:
    # On the website keys belong to the server's environment, not to a page.
    if not get_settings().desktop:
        raise HTTPException(404, "Not found.")


@router.get("", dependencies=[Depends(_desktop_only)])
def read(user: User = Depends(current_user)) -> dict:
    return app_settings.view()


@router.put("", dependencies=[Depends(_desktop_only)])
def update(body: SettingsIn, user: User = Depends(current_user)) -> dict:
    try:
        app_settings.save(body.model_dump(exclude_unset=True))
    except app_settings.SettingsError as exc:
        raise HTTPException(422, str(exc)) from None
    return app_settings.view()
