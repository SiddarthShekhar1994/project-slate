from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..deps import current_user
from ..models import User
from ..services import stt

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("")
def status(user: User = Depends(current_user)) -> dict:
    """Whether spoken questions work here, so the ask panel can offer the microphone."""
    transcriber = stt.get_transcriber()
    return {"available": transcriber is not None, "provider": transcriber.name if transcriber else None}


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), user: User = Depends(current_user)) -> dict:
    data = await audio.read(stt.MAX_AUDIO_BYTES + 1)
    try:
        text = await run_in_threadpool(stt.transcribe, data, audio.content_type or "")
    except stt.STTError as exc:
        code = 503 if stt.get_transcriber() is None else 422
        raise HTTPException(code, str(exc)) from None
    return {"text": text}
