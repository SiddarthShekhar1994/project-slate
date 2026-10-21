"""Data passed between the ingestion steps.

    bytes --extract--> [Page] --ocr (pages that need it)--> [Page] --chunk--> [Chunk]
          --match--> skill scores per chunk --notation--> styles per chunk

Every step is a pure function of its input except OCR, which may call the
Claude API (or Tesseract), so each one is testable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Page:
    """One page of a PDF, one slide, one section of a document, or one image.

    ``label`` is how a citation names it ("p. 3", "slide 7", "section 2").
    ``needs_ocr`` marks pages whose text layer is missing or too thin to trust
    (scanned pages, photos of handwriting, slides that are one big picture);
    ``image`` then holds a PNG rendering for OCR.
    """

    number: int
    label: str
    heading: str = ""
    text: str = ""
    needs_ocr: bool = False
    image: bytes | None = None
    ocr_method: str | None = None


@dataclass
class Extracted:
    pages: list[Page]
    title: str = ""
    page_count: int = 0


@dataclass
class OcrResult:
    """Text read from an image. Math is written as ``$...$`` LaTeX when the reader can."""

    text: str
    method: str  # "claude" | "tesseract" | "none"
    confidence: float = 0.0


@dataclass
class Chunk:
    """A topic-sized run of pages: what a citation points at.

    ``locator`` is human readable ("slides 12-14", "pp. 41-42").
    """

    ordinal: int
    heading: str
    locator: str
    text: str
    pages: list[int] = field(default_factory=list)


SourceKind = str  # "slides" | "textbook" | "syllabus" | "exam" | "notes" | "other"

PROFESSOR_KINDS = ("slides", "notes", "exam", "syllabus")
"""Sources written by the course staff. Their notation wins over a textbook's."""
