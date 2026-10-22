"""What Claude returns for a lesson, and how it becomes a player script.

Language models count word positions badly, so board actions anchor to a
phrase from the narration ("x cubed") instead of a word index. ``to_script``
finds each phrase in the step's spoken words and converts it; a phrase that
isn't there is reported as a problem and sent back to Claude.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from ..materials.read import Kind
from ..tts import spoken_words
from . import ChunkRef


class Segment(BaseModel):
    """Either prose (``text``) or math (``math`` as LaTeX with ``say`` in words)."""

    text: str
    math: str
    say: str


class Action(BaseModel):
    type: Literal["write", "highlight", "box", "fade", "label"]
    at_phrase: str
    id: str
    latex: str
    row: int
    col: int
    size: Literal["md", "lg"]
    target: str
    part: str
    color: Literal["chalk", "yellow", "mint"]
    text: str
    side: Literal["above", "below", "right"]


class Claim(BaseModel):
    kind: Literal["derivative", "equal", "limit", "integral"]
    of: str
    var: str
    equals: str
    left: str
    right: str
    vars: list[str]
    to: str
    side: str
    lower: str
    upper: str


class Option(BaseModel):
    latex: str
    value: str
    say: str
    correct: bool
    why: str


class Checkpoint(BaseModel):
    prompt: str
    expect: Claim
    options: list[Option]


class Step(BaseModel):
    id: str
    title: str
    narration: list[Segment]
    actions: list[Action]
    has_checkpoint: bool
    checkpoint: Checkpoint
    claims: list[Claim]
    sources: list[str]


class Example(BaseModel):
    """The lesson's worked example, in the structured form of a problem read from a sheet,
    so SymPy can compute its answer and check the one the lesson arrives at."""

    kind: Kind
    statement: str
    word: bool
    expr: str
    var: str
    name: str
    at: str
    equation: str
    dependent: str
    to: str
    side: str
    lower: str
    upper: str
    interval: str
    goal: str
    report: str
    estimate: str
    relation: str
    variables: str
    values: str
    rates: str
    find: str
    answer: str


class Lesson(BaseModel):
    title: str
    summary: str
    example: Example
    steps: list[Step]


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def find_phrase(words: list[str], phrase: str) -> int | None:
    """Index of the first spoken word where ``phrase`` starts."""
    target = [_norm(w) for w in phrase.split() if _norm(w)]
    if not target:
        return None
    norm = [_norm(w) for w in words]
    for i in range(len(norm) - len(target) + 1):
        if norm[i:i + len(target)] == target:
            return i
    return None


def _claim(c: Claim) -> dict:
    if c.kind == "derivative":
        return {"kind": "derivative", "of": c.of, "var": c.var or "x", "equals": c.equals,
                "vars": c.vars or [c.var or "x"]}
    if c.kind == "limit":
        return {"kind": "limit", "of": c.of, "var": c.var or "x", "to": c.to, "side": c.side or "both",
                "equals": c.equals}
    if c.kind == "integral":
        out = {"kind": "integral", "of": c.of, "var": c.var or "x", "equals": c.equals}
        if c.lower.strip() or c.upper.strip():
            out.update(lower=c.lower, upper=c.upper)
        return out
    return {"kind": "equal", "left": c.left, "right": c.right, "vars": c.vars}


def example_payload(example: Example) -> dict:
    """What ``materials.verify.check`` needs to compute the example's answer and compare."""
    from ..materials.read import spec_of

    return {"spec": spec_of(example), "answer": example.answer, "statement": example.statement,
            "word": example.word, "steps": [], "difficulty": 2}


def to_script(model: Lesson, chunks: list[ChunkRef], skill_id: str) -> tuple[dict, list[str]]:
    problems: list[str] = []
    by_id = {c.id: c for c in chunks}
    cited: list[str] = []
    steps = []
    for index, step in enumerate(model.steps):
        narration: list = []
        for seg in step.narration:
            if seg.math.strip():
                narration.append({"math": seg.math, "say": seg.say or seg.math})
            elif seg.text:
                narration.append(seg.text)
        words = spoken_words(narration)
        actions = []
        for action in step.actions:
            at = find_phrase(words, action.at_phrase)
            if at is None:
                problems.append(f"step {index + 1} ({step.id}): phrase {action.at_phrase!r} is not in the narration")
                at = 0
            out: dict = {"type": action.type, "at": {"word": at}}
            if action.type == "write":
                out.update(id=action.id, latex=action.latex, row=action.row, col=max(0, min(action.col, 11)),
                           size=action.size)
            elif action.type == "label":
                out.update(id=action.id, text=action.text, target=action.target, side=action.side,
                           color=action.color, **({"part": action.part} if action.part else {}))
            elif action.type == "fade":
                out.update(target=action.target)
            else:
                out.update(target=action.target, color=action.color, **({"part": action.part} if action.part else {}))
            actions.append(out)
        entry: dict = {"id": step.id, "title": step.title, "narration": narration, "actions": actions}
        if step.has_checkpoint:
            entry["checkpoint"] = {
                "prompt": step.checkpoint.prompt,
                "expect": _claim(step.checkpoint.expect),
                "options": [{"id": chr(97 + i), "latex": o.latex, "value": o.value, "say": o.say,
                             "correct": o.correct, "why": o.why} for i, o in enumerate(step.checkpoint.options)],
            }
        if step.claims:
            entry["claims"] = [_claim(c) for c in step.claims]
        refs = [s for s in step.sources if s in by_id]
        if refs:
            entry["sources"] = refs
            cited += [r for r in refs if r not in cited]
        steps.append(entry)
    sources = [{"id": c, "title": by_id[c].source_title, "kind": by_id[c].source_kind, "locator": by_id[c].locator,
                "excerpt": re.sub(r"\s+", " ", by_id[c].text)[:400]} for c in cited]
    script = {"id": "generated", "version": 1, "skillId": skill_id, "title": model.title, "summary": model.summary,
              "sources": sources, "steps": steps}
    return script, problems
