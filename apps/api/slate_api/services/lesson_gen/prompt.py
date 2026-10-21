"""The instructions Claude gets for writing a lesson."""

from __future__ import annotations

from slate_skills import get_skill
from slate_skills.core.mistakes import mistake_type

from ..ingest.notation import NotationProfile
from . import ChunkRef

SYSTEM = r"""You write short narrated chalkboard lessons for Slate, a calculus study app. A voice reads the narration
while the math writes itself onto a dark green board step by step.

Teach the given skill the way the student's own course materials do. When a source has a worked example, use that
example (or one like it) rather than inventing a new style, and cite the source ids you drew on in each step's sources.

The lesson:
- 6 to 10 steps. Each step has a short title, narration of one to three sentences, and board actions.
- Narration is a list of segments. Prose goes in text. Every piece of math goes in a math segment: math is LaTeX for
  the board and captions, and say is the same math in plain spoken words ("x cubed plus one"). Never put math in a
  text segment. For a segment you don't use, leave its fields empty.
- Actions: write puts a line of LaTeX on the board (give it an id, a row from 0 down, col 0 to 11 to indent, size
  md or lg); highlight colours a written line or a named part of it; box draws around a line or part; fade dims a line
  or label; label writes a short handwritten note (text) next to a line or part. Every action has at_phrase: a short
  phrase copied exactly from that step's spoken narration, at which the action happens.
- Colour code: wrap the inner or first piece in \htmlClass{slate-yellow}{...} and the outer or second piece in
  \htmlClass{slate-mint}{...}. Wrap any part you will highlight or box in \htmlClass{slate-part-NAME}{...} and refer to
  it with part NAME.
- One or two pause-and-predict checkpoints (has_checkpoint true) placed just before the step that reveals the result.
  Options: one correct answer and two or three distractors taken from the skill's real mistakes listed below. value is
  each option in Slate's answer syntax (^ for powers, * or juxtaposition for products, sqrt(), sin(), cos(), tan(),
  sec(), exp(), ln(), e, pi), say is how it is read aloud, why explains it in one sentence with $...$ math.
  expect states the answer as a claim. For steps without a checkpoint set has_checkpoint false and leave the
  checkpoint fields empty.
- claims: every checkable fact the step states, in answer syntax: kind "derivative" with of, var, equals; or kind
  "equal" with left, right and vars. Every claim must be true. They are checked by a computer algebra system and the
  lesson is rejected if any fails.
- Write in plain, warm, direct sentences for a first-year student. No em dashes."""


def build_request(skill_id: str, chunks: list[ChunkRef], notation: NotationProfile | None,
                  feedback: list[str] | None = None) -> str:
    skill = get_skill(skill_id)
    lines = [
        f"Skill: {skill.title}. {skill.summary}",
        f"Formula: ${skill.formula.latex}$. {skill.formula.note}",
        "Common mistakes (use these for checkpoint distractors):",
    ]
    seen = set()
    for pattern in skill.mistakes:
        if pattern.tag in seen:
            continue
        seen.add(pattern.tag)
        kind = mistake_type(pattern.tag)
        lines.append(f"- {kind.label}: {kind.description}")
    if notation is not None:
        lines.append(f"Use the professor's notation: {notation.describe()}.")
        changed = [f for f, d in notation.differs_from_textbook.items() if d]
        if changed:
            lines.append("This differs from the textbook for: " + ", ".join(changed) + ". Follow the professor.")
    lines.append("The student's sources (cite these ids):")
    for chunk in chunks:
        lines.append(f"[{chunk.id}] {chunk.source_title}, {chunk.locator}"
                     f"{' (' + chunk.heading + ')' if chunk.heading else ''}:\n{chunk.text[:2500]}")
    if feedback:
        lines.append("Your previous lesson was rejected for these reasons. Fix every one:")
        lines += [f"- {problem}" for problem in feedback[:30]]
    return "\n\n".join(lines)
