from __future__ import annotations

import sympy as sp
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..deps import current_user
from ..models import User
from ..schemas import PreviewIn
from ..services import photo
from ..services.materials import answers
from ..services.materials.kinds import VARIABLES
from ..services.verify import ParseError, parse_answer

router = APIRouter(prefix="/math", tags=["math"])

ALLOWED_VARIABLES = set(VARIABLES)


@router.post("/preview")
def preview(body: PreviewIn) -> dict:
    """Parse typed input and return the LaTeX to preview. Never evaluates or simplifies."""
    names = list(dict.fromkeys(n for n in body.variables if n))
    if not set(names) <= ALLOWED_VARIABLES:
        raise HTTPException(422, "Unsupported variable.")
    symbols = tuple(sp.Symbol(n) for n in names)
    try:
        if body.answer_kind == "expression":
            latex = parse_answer(body.text, symbols).latex
        else:
            latex = answers.preview(body.answer_kind, body.text, symbols, units=body.units)
    except ParseError as exc:
        return {"ok": False, "latex": None, "error": str(exc)}
    except (ValueError, TypeError, NotImplementedError):
        return {"ok": False, "latex": None, "error": "I couldn't read that. Check it for typos."}
    return {"ok": True, "latex": latex, "error": None}


@router.post("/photo")
async def read_photo(image: UploadFile = File(...), variables: str = Form("x", max_length=20),
                     prompt: str = Form("", max_length=1000), user: User = Depends(current_user)) -> dict:
    """Read the final answer from a photo of the student's work. It fills the answer box; it never grades."""
    names = list(dict.fromkeys(v for v in variables.split(",") if v))
    if not set(names) <= ALLOWED_VARIABLES:
        raise HTTPException(422, "Unsupported variable.")
    data = await image.read(photo.MAX_IMAGE_BYTES + 1)
    try:
        reading = await run_in_threadpool(photo.read_answer, data, prompt=prompt, variables=names)
    except photo.PhotoError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    return {"text": reading.text, "latex": reading.latex, "error": reading.error,
            "confidence": reading.confidence, "method": reading.method}
