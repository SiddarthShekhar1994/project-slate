from __future__ import annotations

import sympy as sp
from fastapi import APIRouter, HTTPException

from ..schemas import PreviewIn
from ..services.verify import ParseError, parse_answer

router = APIRouter(prefix="/math", tags=["math"])

ALLOWED_VARIABLES = {"x", "y", "t", "r"}


@router.post("/preview")
def preview(body: PreviewIn) -> dict:
    """Parse typed input and return the LaTeX to preview. Never evaluates or simplifies."""
    names = list(dict.fromkeys(body.variables))
    if not set(names) <= ALLOWED_VARIABLES:
        raise HTTPException(422, "Unsupported variable.")
    try:
        parsed = parse_answer(body.text, [sp.Symbol(n) for n in names])
    except ParseError as exc:
        return {"ok": False, "latex": None, "error": str(exc)}
    return {"ok": True, "latex": parsed.latex, "error": None}
