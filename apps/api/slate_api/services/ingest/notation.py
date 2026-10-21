"""Which notation a course uses, so lessons can match the professor.

Interface:

``detect_notation(text) -> dict[str, dict[str, int]]``
    Count the notation styles that appear in a chunk of text, per feature.
    Features and styles:

    ``derivative``  ``prime`` (f'(x), y'), ``leibniz`` (dy/dx, d/dx, \\frac{dy}{dx}),
                    ``operator`` (D_x f, Df, D_x y)
    ``log``         ``ln`` (ln x) or ``log`` (log x meaning the natural log)
    ``inner``       the letter used for the inside of a composition when the
                    text names it: ``u``, ``g`` (g(x)), ``w``, ...

``notation_profile(observations) -> NotationProfile``
    Combine per-chunk counts into one profile. ``observations`` is a list of
    ``(source_kind, chunk_id, counts)``. Professor-written sources (slides,
    notes, exams, syllabus) outrank a textbook: if the professor uses a style
    at all, it wins, even when the textbook uses another one more often.

``apply_notation(latex, profile) -> str``
    Rewrite LaTeX written in Slate's default notation into the profile's
    notation: derivative style, natural log symbol, inner-function letter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_STYLES = {"derivative": "prime", "log": "ln", "inner": "u"}


@dataclass(frozen=True)
class NotationProfile:
    derivative: str = "prime"
    log: str = "ln"
    inner: str = "u"
    # feature -> chunk ids whose text showed the chosen style
    evidence: dict[str, list[str]] = field(default_factory=dict)
    # feature -> True when the professor's choice differs from the textbook's
    differs_from_textbook: dict[str, bool] = field(default_factory=dict)

    def describe(self) -> str:
        """One line for prompts and the UI, e.g. "Leibniz notation (dy/dx), ln for the natural log"."""
        names = {"prime": "prime notation (f'(x))", "leibniz": "Leibniz notation (dy/dx)",
                 "operator": "operator notation (D_x f)"}
        return f"{names.get(self.derivative, self.derivative)}, {self.log} for the natural log, " \
               f"{self.inner} for the inside of a composition"


_DERIVATIVE = {
    # f'(x), y', g''(t); not apostrophes in words like "don't" (a letter follows).
    "prime": re.compile(r"(?<![A-Za-z])[a-zA-Z]'+(?:\s*\(|(?![a-zA-Z]))"),
    # dy/dx, d/dx, \frac{dy}{dx}, \frac{d}{dx}
    "leibniz": re.compile(r"\bd[a-z]?\s*/\s*d[a-z]\b|\\d?frac\{d[a-z]?\}\{d[a-z]\}"),
    # D_x f, D_x(y), Dx f, Df(x)
    "operator": re.compile(r"\bD_\{?[a-z]\}?|\bD[xt]\s*[\[(a-z]|\bDf\b"),
}
_LOG = {
    "ln": re.compile(r"\\?\bln\b"),
    "log": re.compile(r"\\?\blog\b(?!_)"),
}
_INNER = re.compile(r"\b(?:let|set|put|write|call)\s+(?:the\s+inner(?:\s+function)?\s+)?([a-z])\s*(?:\(x\))?\s*=",
                    re.IGNORECASE)


def detect_notation(text: str) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for style, pattern in _DERIVATIVE.items():
        n = len(pattern.findall(text))
        if n:
            counts.setdefault("derivative", {})[style] = n
    for style, pattern in _LOG.items():
        n = len(pattern.findall(text))
        if n:
            counts.setdefault("log", {})[style] = n
    for letter in _INNER.findall(text):
        letter = letter.lower()
        if letter not in ("x", "y", "f"):
            inner = counts.setdefault("inner", {})
            inner[letter] = inner.get(letter, 0) + 1
    return counts


def notation_profile(observations: list[tuple[str, str, dict[str, dict[str, int]]]]) -> NotationProfile:
    from .types import PROFESSOR_KINDS

    chosen: dict[str, str] = {}
    evidence: dict[str, list[str]] = {}
    differs: dict[str, bool] = {}
    for feature, default in DEFAULT_STYLES.items():
        prof: dict[str, int] = {}
        book: dict[str, int] = {}
        for kind, _, counts in observations:
            target = prof if kind in PROFESSOR_KINDS else book
            for style, n in counts.get(feature, {}).items():
                target[style] = target.get(style, 0) + n
        best_prof = max(prof, key=lambda k: prof[k]) if prof else None
        best_book = max(book, key=lambda k: book[k]) if book else None
        style = best_prof or best_book or default
        chosen[feature] = style
        differs[feature] = bool(best_prof and best_book and best_prof != best_book)
        evidence[feature] = [chunk for kind, chunk, counts in observations
                             if style in counts.get(feature, {}) and (best_prof is None or kind in PROFESSOR_KINDS)]
    return NotationProfile(derivative=chosen["derivative"], log=chosen["log"], inner=chosen["inner"],
                           evidence=evidence, differs_from_textbook=differs)


def _leibniz(var: str, fn: str | None) -> str:
    return rf"\frac{{d{fn}}}{{d{var}}}" if fn else rf"\frac{{d}}{{d{var}}}"


def _operator(var: str, fn: str | None) -> str:
    return rf"D_{{{var}}}{fn}" if fn else rf"D_{{{var}}}"


def apply_notation(latex: str, profile: NotationProfile | None) -> str:
    """Rewrite Slate's default notation (prime, \\ln, u) into the profile's."""
    if profile is None:
        return latex
    out = latex
    if profile.derivative != "prime":
        conv = _leibniz if profile.derivative == "leibniz" else _operator

        # f'(x) -> \frac{df}{dx} or D_x f(x), only for single-letter function names.
        def prime_call(m: re.Match[str]) -> str:
            fn, var = m.group(1), m.group(2)
            return conv(var, fn) if profile.derivative == "leibniz" else f"{conv(var, None)} {fn}({var})"

        out = re.sub(r"(?<![\\A-Za-z])([a-zA-Z])'\(([a-z])\)", prime_call, out)
        if profile.derivative == "operator":
            out = re.sub(r"\\frac\{d([a-z]?)\}\{d([a-z])\}", lambda m: _operator(m.group(2), m.group(1) or None), out)
    if profile.log == "log":
        out = re.sub(r"\\ln(?![a-zA-Z])", r"\\log", out)
    if profile.inner != "u" and len(profile.inner) == 1:
        # The letter u as a standalone variable: not inside commands (\cup, \mu), not in words.
        out = re.sub(r"(?<![\\A-Za-z])u(?![A-Za-z])", profile.inner, out)
        out = re.sub(r"\{du\}", "{d" + profile.inner + "}", out)
    return out
