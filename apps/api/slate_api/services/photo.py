"""Read a student's final answer from a photo of their work.

The photo only fills the answer box. Slate parses what was read with the same
parser that grades typed answers and shows the student how it reads it; they
correct it if needed and submit as usual, so grading stays symbolic and the
student stays in charge of what gets checked.

Claude vision reads handwriting and finds the final answer among the
working. It is told to copy the student's answer exactly, mistakes included,
and never to solve the problem. Without an API key Tesseract reads the last
line of text, which works for neat printed answers and little else.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass

import sympy as sp
from pydantic import BaseModel, Field

from .llm import LLMRefused, LLMUnavailable, get_llm
from .verify import ParseError, parse_answer

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_EDGE = 1568  # Claude downsizes beyond this anyway

SYSTEM = """You read a calculus student's final answer from a photo of their work.

Find the answer they ended on: the last line, or whatever they boxed, circled or underlined. Copy it exactly as
they wrote it, including any mistakes. Never solve the problem yourself and never correct their answer: if
their answer is wrong, it must stay wrong.

Write the answer in plain calculator syntax: ^ for powers, * where multiplication is ambiguous, sqrt(...) for
roots, sin(...), cos(...), tan(...), ln(...), e^(...), pi, and the problem's variables. Leave out any
"f'(x) =" or "dy/dx =" in front. If there is no answer you can read, set found to false.
Give a confidence from 0 to 1 that you read the answer correctly."""


class PhotoAnswer(BaseModel):
    found: bool
    answer: str = Field(max_length=300)
    confidence: float = Field(ge=0, le=1)


class PhotoError(RuntimeError):
    """A problem with the photo, with a message safe to show the student."""

    def __init__(self, message: str, code: int = 422):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PhotoReading:
    text: str
    latex: str | None
    error: str | None
    confidence: float
    method: str


def _normalise(image: bytes) -> bytes:
    """PNG no larger than Claude needs, upright, in RGB. Raises PhotoError if it isn't an image."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(image) > MAX_IMAGE_BYTES:
        raise PhotoError("That photo is too large. Try one under 15 MB.", 413)
    try:
        img = Image.open(io.BytesIO(image))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise PhotoError("That file isn't a photo Slate can open. Try a JPEG or PNG.") from None
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _with_claude(png: bytes, prompt: str, variables: list[str], llm) -> tuple[str, float] | None:
    if not llm.available:
        return None
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.standard_b64encode(png).decode()}},
        {"type": "text", "text": f"The problem: {prompt or 'not given'}\nVariables: {', '.join(variables)}\n"
                                 "What is the student's final answer?"},
    ]
    try:
        result = llm.structured(system=SYSTEM, content=content, schema=PhotoAnswer, effort="low", max_tokens=2000)
    except (LLMUnavailable, LLMRefused) as exc:
        log.info("Claude photo reading unavailable: %s", exc)
        return None
    if not result.found or not result.answer.strip():
        raise PhotoError("Couldn't find a final answer in that photo. Try a closer, brighter shot of the last line.")
    return result.answer.strip(), result.confidence


def _with_tesseract(png: bytes) -> tuple[str, float] | None:
    from .ingest.ocr import _with_tesseract as ocr

    result = ocr(png)
    if result is None:
        return None
    lines = [line.strip() for line in result.text.splitlines() if line.strip()]
    if not lines:
        raise PhotoError("Couldn't read any writing in that photo.")
    last = lines[-1]
    # "y' = 3x^2" -> "3x^2"; the parser handles "f'(x) =" itself but not every prefix.
    last = re.sub(r"^.*=\s*", "", last) or last
    return last, result.confidence


def read_answer(image: bytes, *, prompt: str = "", variables: list[str], llm=None) -> PhotoReading:
    png = _normalise(image)
    llm = llm if llm is not None else get_llm()
    method = "claude"
    found = _with_claude(png, prompt, variables, llm)
    if found is None:
        method = "tesseract"
        found = _with_tesseract(png)
    if found is None:
        raise PhotoError("Reading photos needs Claude (ANTHROPIC_API_KEY) or Tesseract. Type your answer instead.",
                         503)
    text, confidence = found
    try:
        parsed = parse_answer(text, [sp.Symbol(v) for v in variables])
        latex, error = parsed.latex, None
    except ParseError as exc:
        latex, error = None, str(exc)
    return PhotoReading(text=text[:300], latex=latex, error=error, confidence=round(confidence, 2), method=method)
