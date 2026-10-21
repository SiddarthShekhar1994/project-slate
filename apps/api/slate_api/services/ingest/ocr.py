"""Read text from images: photos of handwritten notes, scanned pages, picture-only slides.

Claude vision goes first because it reads handwriting and math far better
than classic OCR, and it can write math as LaTeX. Tesseract is the fallback
when no API key is configured or the request is declined; it reads printed
text reasonably and handwriting poorly. If neither is available the page is
left empty and the method is recorded as "none", so the library can say why.
"""

from __future__ import annotations

import base64
import io
import logging

from pydantic import BaseModel, Field

from ..llm import LLMRefused, LLMUnavailable, get_llm
from .types import OcrResult, Page

log = logging.getLogger(__name__)

SYSTEM = """You transcribe a student's course material from an image: handwritten notes, a scanned page, or a slide.

Write down everything that is there, in reading order, faithfully. Do not solve, correct or add anything.
Write every piece of mathematics as LaTeX between single dollar signs, for example $\\frac{dy}{dx} = 3x^2\\cos(x^3+1)$.
Keep headings on their own lines. Mark anything you cannot read as [unclear].
Give a confidence from 0 to 1 for how sure you are of the transcription as a whole."""


class Transcription(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)


def _with_claude(image: bytes, hint: str, llm) -> OcrResult | None:
    if not llm.available:
        return None
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.standard_b64encode(image).decode()}},
        {"type": "text", "text": f"Transcribe this image.{' Context: ' + hint if hint else ''}"},
    ]
    try:
        result = llm.structured(system=SYSTEM, content=content, schema=Transcription, effort="medium", max_tokens=8000)
    except (LLMUnavailable, LLMRefused) as exc:
        log.info("Claude OCR unavailable, falling back: %s", exc)
        return None
    return OcrResult(text=result.text.strip(), method="claude", confidence=result.confidence)


def _with_tesseract(image: bytes) -> OcrResult | None:
    try:
        import pytesseract
        from PIL import Image, ImageOps

        img = ImageOps.grayscale(Image.open(io.BytesIO(image)))
        # A light threshold helps with phone photos of paper.
        img = img.point(lambda v: 255 if v > 160 else 0)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception as exc:  # binary missing, unreadable image, ...
        log.info("Tesseract unavailable: %s", exc)
        return None
    words = [(w, float(c)) for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
    if not words:
        return OcrResult(text="", method="tesseract", confidence=0.0)
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(word)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    confidence = sum(c for _, c in words) / len(words) / 100
    return OcrResult(text=text, method="tesseract", confidence=round(confidence, 2))


def ocr_image(image: bytes, *, hint: str = "", llm=None) -> OcrResult:
    llm = llm if llm is not None else get_llm()
    return _with_claude(image, hint, llm) or _with_tesseract(image) or OcrResult("", "none", 0.0)


def ocr_pages(pages: list[Page], *, llm=None) -> list[Page]:
    """Fill in text for pages marked ``needs_ocr``; other pages pass through."""
    for page in pages:
        if not page.needs_ocr or not page.image:
            continue
        result = ocr_image(page.image, hint=page.heading, llm=llm)
        if result.text:
            page.text = f"{page.text}\n{result.text}".strip() if page.text else result.text
        page.ocr_method = result.method
        page.image = None
    return pages
