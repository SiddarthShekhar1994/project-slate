from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from ..deps import current_user
from ..models import User
from ..services.storage import get_storage

router = APIRouter(prefix="/media", tags=["media"])


def _allowed(user: User, key: str) -> bool:
    # Lesson audio is shared (keys are content hashes); uploads belong to their owner.
    if key.startswith("tts/"):
        return True
    return key.startswith(f"uploads/{user.id}/")


@router.get("/{key:path}")
def media(key: str, user: User = Depends(current_user)):
    if ".." in key.split("/") or not _allowed(user, key):
        raise HTTPException(404, "Not found.")
    storage = get_storage()
    try:
        path = storage.local_path(key)
    except ValueError:
        raise HTTPException(404, "Not found.") from None
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=31536000, immutable"} if key.startswith("tts/") else {}
    if path is not None:
        # FileResponse handles Range requests, which <audio> seeking relies on.
        return FileResponse(path, media_type=media_type, headers=headers)
    if not storage.exists(key):
        raise HTTPException(404, "Not found.")
    return Response(storage.get(key), media_type=media_type, headers=headers)
