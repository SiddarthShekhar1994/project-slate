"""Group extracted pages into topic-sized chunks that a citation can point at.

A lesson cites "slides 12-14" or "pp. 41-42", so a chunk should cover one
topic: long enough to stand on its own, short enough that the citation sends
the student to the right place. Where a topic starts depends on the layout:

- Slides: a topic runs while the titles continue it ("Chain rule",
  "Chain rule (cont.)", "Chain rule, examples", "Example"). A slide without a
  title belongs to the topic before it.
- PDF pages: a page with a new heading starts a topic. Otherwise pages are
  grouped a few at a time, because a page break says nothing about the topic.
- Documents: each section is a chunk.

Afterwards, chunks too short to be useful on their own (a title slide, a
divider) are merged into a neighbour, and chunks too long to cite precisely are
split at paragraph boundaries. Pages with no text at all are skipped and never
named in a locator.

The layout comes from the page labels the extractor wrote ("slide 4", "p. 3",
"section 2", "image"), except that a slide deck exported to PDF (``kind`` is
"slides" but the labels are pages) is still grouped by its slide titles.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .types import Chunk, Page

MIN_CHARS = 150
MAX_CHARS = 4000
PAGES_PER_CHUNK = 3
MAX_HEADING_CHARS = 300  # SourceChunk.heading column
MAX_LOCATOR_CHARS = 120  # SourceChunk.locator column

SLIDES, PAGES, SECTIONS, IMAGE = "slides", "pages", "sections", "image"

_SLIDE_KINDS = {"slides", "slide", "pptx", "ppt", "deck"}
_DOCUMENT_KINDS = {"docx", "doc", "document"}
_IMAGE_KINDS = {"image", "png", "jpg", "jpeg", "photo"}

_PLURALS = {"p.": "pp.", "p": "pp.", "pg.": "pp.", "page": "pages", "slide": "slides", "section": "sections"}

_LABEL = re.compile(r"^(?P<unit>.*?)\s*(?P<num>\d+)$")

# Trailing marks that say "same topic as before": "(cont.)", "continued",
# "cont'd", "(2/3)", "part 2", "II". They must follow a space or punctuation so
# a title like "Derivative of e^x" keeps its "x".
_CONTINUATION_MARK = re.compile(
    r"(?:\s+|\s*[,:;\-–—]\s*|\s*[(\[]\s*)"
    r"(?:cont(?:inued|'d|d)?\.?|ctd\.?|part\s+(?:\d+|[ivx]+|one|two|three|four)|\d+\s*(?:/|of)\s*\d+|\d+|(?-i:[IVX]{1,4}))"
    r"\s*[)\]]?\s*$",
    re.IGNORECASE,
)
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+")
# Titles that never start a topic of their own.
_GENERIC_TITLE = re.compile(
    r"^(?:(?:more|worked|another|some)\s+)?(?:examples?|practice(?:\s+problems?)?|exercises?|solutions?|"
    r"your\s+turn|try\s+(?:it|this)|check\s+your\s+understanding|quick\s+check|continued|cont|"
    r"questions?|problems?)(?:\s+\d+)?$"
)
# Words that, around a repeated title, still describe the same topic
# ("more chain rule examples", "examples of the chain rule").
_FILLER_WORDS = {
    "example", "examples", "more", "another", "worked", "practice", "problem", "problems", "exercise", "exercises",
    "solution", "solutions", "continued", "cont", "again", "revisited", "review", "proof", "using", "of", "the", "a",
    "an", "for", "on", "applying", "applications", "application", "part", "one", "two", "three",
}
# A chunk whose text is little more than its heading (a divider slide) introduces what follows it.
# A one-line formula slide is not a divider: it has a few words besides the title.
_DIVIDER_WORDS = 5


@dataclass
class _Group:
    """Pages on their way to becoming a chunk, kept as paragraphs so a split
    piece still knows which pages it came from."""

    heading: str
    paras: list[tuple[Page, str]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(len(p) for _, p in self.paras) + 2 * max(len(self.paras) - 1, 0)

    @property
    def text(self) -> str:
        return "\n\n".join(p for _, p in self.paras)

    @property
    def pages(self) -> list[Page]:
        seen: dict[int, Page] = {}
        for page, _ in self.paras:
            seen.setdefault(page.number, page)
        return list(seen.values())


def chunk_pages(pages: list[Page], kind: str) -> list[Chunk]:
    """Group ``pages`` into chunks, in reading order, with ordinals from 0.

    ``kind`` is the source kind or file type ("slides", "textbook", "pdf",
    "docx", ...); the page labels decide the layout when they are clear.
    """
    pages = [p for p in pages if p.heading.strip() or p.text.strip()]
    if not pages:
        return []
    layout = _layout(pages, kind)
    if layout == SLIDES:
        groups = _group_slides(pages)
    elif layout == PAGES:
        groups = _group_pdf_pages(pages)
    elif layout == SECTIONS:
        groups = [_Group(_clean(p.heading), _paragraphs(p)) for p in pages]
    else:
        groups = [_Group(_clean(pages[0].heading), [para for p in pages for para in _paragraphs(p)])]

    groups = [piece for g in groups for piece in _split(g)]
    groups = _merge_short(groups)
    return [
        Chunk(
            ordinal=i,
            heading=g.heading[:MAX_HEADING_CHARS],
            locator=locator([p for p in g.pages], layout),
            text=g.text,
            pages=[p.number for p in g.pages],
        )
        for i, g in enumerate(groups)
    ]


def locator(pages: list[Page], layout: str = PAGES) -> str:
    """How a citation names these pages: "slide 4", "slides 12-14", "pp. 41-42", "section 2", "image".

    Pages that are not consecutive are listed as ranges ("slides 3-5, 8").
    """
    if not pages:
        return ""
    pages = sorted({p.number: p for p in pages}.values(), key=lambda p: p.number)
    labels = [_label(p, layout) for p in pages]
    if len(pages) == 1:
        return labels[0][:MAX_LOCATOR_CHARS]
    parsed = [_LABEL.match(label) for label in labels]
    units = {m.group("unit").lower() for m in parsed if m}
    if all(parsed) and len(units) == 1:
        unit = parsed[0].group("unit")
        numbers = sorted({int(m.group("num")) for m in parsed})
        text = f"{_PLURALS.get(unit.lower(), unit + 's')} {', '.join(_ranges(numbers))}"
    else:
        text = ", ".join(dict.fromkeys(labels))
    if len(text) > MAX_LOCATOR_CHARS:
        text = f"{labels[0]} to {labels[-1]}"
    return text[:MAX_LOCATOR_CHARS]


# --- layout -------------------------------------------------------------------


def _layout(pages: list[Page], kind: str) -> str:
    kind = (kind or "").strip().lower()
    units = {_label_layout(p.label) for p in pages} - {None}
    if units == {SECTIONS}:
        return SECTIONS
    if units == {IMAGE}:
        return IMAGE
    if units == {SLIDES} or (kind in _SLIDE_KINDS and units <= {PAGES}):
        return SLIDES
    if units == {PAGES}:
        return PAGES
    if kind in _DOCUMENT_KINDS:
        return SECTIONS
    if kind in _IMAGE_KINDS:
        return IMAGE
    return PAGES


def _label_layout(label: str) -> str | None:
    label = label.strip().lower()
    if label.startswith("slide"):
        return SLIDES
    if label.startswith("section") or label.startswith("sec."):
        return SECTIONS
    if label.startswith("image") or label.startswith("photo"):
        return IMAGE
    if re.match(r"^(?:p\.?|pp\.|pg\.|page)\s*\d", label):
        return PAGES
    return None


def _label(page: Page, layout: str) -> str:
    if page.label.strip():
        return page.label.strip()
    return {SLIDES: f"slide {page.number}", SECTIONS: f"section {page.number}", IMAGE: "image"}.get(
        layout, f"p. {page.number}")


def _ranges(numbers: list[int]) -> list[str]:
    out: list[str] = []
    start = prev = numbers[0]
    for n in numbers[1:] + [None]:  # type: ignore[list-item]
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if n is not None:
            start = prev = n
    return out


# --- grouping -------------------------------------------------------------------


def _group_slides(pages: list[Page]) -> list[_Group]:
    groups: list[_Group] = []
    prev_title = ""
    for page in pages:
        title = _clean(page.heading)
        current = groups[-1] if groups else None
        if current is not None and (not title or _continues(current.heading, title) or _continues(prev_title, title)):
            current.paras.extend(_paragraphs(page))
            if not current.heading and title:
                current.heading = _strip_continuation(title)
        else:
            groups.append(_Group(_strip_continuation(title), _paragraphs(page)))
        if title:
            prev_title = title
    return groups


def _group_pdf_pages(pages: list[Page]) -> list[_Group]:
    groups: list[_Group] = []
    count = 0
    for page in pages:
        heading = _clean(page.heading)
        current = groups[-1] if groups else None
        # Running headers repeat the same heading on every page, so only a heading
        # that does not continue the current one starts a new topic.
        new_topic = bool(heading) and (current is None or not _continues(current.heading, heading))
        if current is None or new_topic or count >= PAGES_PER_CHUNK:
            carried = current.heading if current is not None else ""
            groups.append(_Group(_strip_continuation(heading) if new_topic else carried or heading))
            count = 0
        groups[-1].paras.extend(_paragraphs(page))
        count += 1
    return groups


def _paragraphs(page: Page) -> list[tuple[Page, str]]:
    """The page's text as paragraphs, with its heading on top when the text does not already start with it."""
    text = _tidy(page.text)
    heading = _clean(page.heading)
    if heading and not _squash(text).startswith(_squash(heading)):
        text = f"{heading}\n\n{text}" if text else heading
    return [(page, p) for p in re.split(r"\n\s*\n", text) if p.strip()]


# --- titles ---------------------------------------------------------------------


def _clean(title: str) -> str:
    return re.sub(r"\s+", " ", _quotes(title)).strip()


def _quotes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").replace(" ", " ")


def _squash(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def _strip_continuation(title: str) -> str:
    while True:
        stripped = _CONTINUATION_MARK.sub("", title).rstrip(" ,:;-–—")
        if stripped == title or not stripped:
            return title
        title = stripped


def _topic(title: str) -> str:
    topic = _strip_continuation(_clean(title)).lower()
    topic = _LEADING_ARTICLE.sub("", topic)
    return topic.strip(" .,:;-–—")


def _continues(base: str, title: str) -> bool:
    """Whether a slide titled ``title`` carries on the topic titled ``base``."""
    b = _topic(title)
    if not b or _GENERIC_TITLE.match(b):
        return True
    a = _topic(base)
    if not a:
        return False
    if a == b:
        return True
    # "Chain rule: proof", "Chain rule, examples", "Chain rule (two layers)"
    for short, long in ((a, b), (b, a)):
        if long.startswith(short) and re.match(r"\s*[,:;(\[\-–—]", long[len(short):]):
            return True
    # "More chain rule examples", "Examples of the chain rule"
    found = re.search(rf"(?<!\w){re.escape(a)}(?!\w)", b)
    if found:
        rest = b[:found.start()] + " " + b[found.end():]
        return all(w in _FILLER_WORDS for w in re.findall(r"[a-z]+", rest))
    return False


# --- sizing ---------------------------------------------------------------------


def _tidy(text: str) -> str:
    text = _quotes(text).replace("\r\n", "\n").replace("\r", "\n").replace("­", "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split(group: _Group) -> list[_Group]:
    """Cut a long group at paragraph boundaries into pieces of similar size."""
    if group.size <= MAX_CHARS:
        return [group]
    paras = [(page, piece) for page, para in group.paras for piece in _cut(para, MAX_CHARS)]
    target = group.size / math.ceil(group.size / MAX_CHARS)
    pieces: list[_Group] = []
    current = _Group(group.heading)
    for page, para in paras:
        if current.paras and current.size + 2 + len(para) > MAX_CHARS:
            pieces.append(current)
            current = _Group(group.heading)
        current.paras.append((page, para))
        if current.size >= target:
            pieces.append(current)
            current = _Group(group.heading)
    if current.paras:
        pieces.append(current)
    return pieces


def _cut(text: str, limit: int) -> list[str]:
    """Split one paragraph that is too long: at line breaks, then sentences, then spaces."""
    if len(text) <= limit:
        return [text]
    for pattern, joiner in ((r"\n", "\n"), (r"(?<=[.!?])\s+", " "), (r"\s+", " ")):
        units = [u for u in re.split(pattern, text) if u]
        if len(units) > 1:
            return [piece for packed in _pack(units, joiner, limit) for piece in _cut(packed, limit)]
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _pack(units: list[str], joiner: str, limit: int) -> list[str]:
    out: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(joiner) + len(unit) > limit:
            out.append(current)
            current = unit
        else:
            current = f"{current}{joiner}{unit}" if current else unit
    if current:
        out.append(current)
    return out


def _merge_short(groups: list[_Group]) -> list[_Group]:
    groups = list(groups)
    while len(groups) > 1:
        # A short group with its own topic heading stays separate: folding a brief
        # "Product rule" slide into the chain rule chunk would mis-cite it. Only
        # headless fragments and bare section dividers are merged.
        i = next((i for i, g in enumerate(groups)
                  if g.size < MIN_CHARS and (not g.heading or _is_divider(g))), None)
        if i is None:
            break
        if i == 0:
            j = 1
        elif i == len(groups) - 1:
            j = i - 1
        else:
            j = i + 1 if _is_divider(groups[i]) else i - 1
        first, second = sorted((i, j))
        a, b = groups[first], groups[second]
        bigger, smaller = (a, b) if a.size >= b.size else (b, a)
        merged = _Group(bigger.heading or smaller.heading, a.paras + b.paras)
        groups[first:second + 1] = [merged]
    return groups


def _is_divider(group: _Group) -> bool:
    if not group.heading:
        return False
    body = [p for _, p in group.paras if _squash(p) != _squash(group.heading)]
    return sum(len(p.split()) for p in body) < _DIVIDER_WORDS
