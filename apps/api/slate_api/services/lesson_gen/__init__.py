"""Lesson generation from the student's sources, verified before it is stored.

``generate_lesson_script`` asks Claude for a narrated board lesson on any
topic that follows the student's own materials and their professor's
notation, then checks it structurally (``validate.py``) and mathematically
(``verify.claims``, plus SymPy's own answer to the lesson's worked example).
Failures go back to Claude with the exact problems for up to three attempts.
For a built-in skill, without an API key or if no attempt checks out, the
deterministic composer builds a sound lesson from a verified template problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChunkRef:
    """A source excerpt the lesson may cite. ``id`` is the chunk id."""

    id: str
    source_title: str
    source_kind: str
    locator: str
    heading: str
    text: str


@dataclass
class GenerationResult:
    script: dict
    method: str  # "claude" | "composer"
    attempts: int = 0
    problems: list[str] = field(default_factory=list)
    record: dict = field(default_factory=dict)  # the verification record to store with the lesson


def generate_lesson_script(skill_id, chunks, notation, *, llm=None, seed: int = 0,
                           examples: list[dict] | None = None) -> GenerationResult:
    from .generate import generate

    return generate(skill_id, chunks, notation, llm=llm, seed=seed, examples=examples)


__all__ = ["ChunkRef", "GenerationResult", "generate_lesson_script"]
