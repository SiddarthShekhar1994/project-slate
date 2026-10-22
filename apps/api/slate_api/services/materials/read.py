"""Read the problems and topics in a piece of course material with Claude.

Claude sees the material's text, chunk by chunk, and for short PDFs and
photos the pages themselves, since a review sheet's math layout (exponents,
fractions, roots) survives in the image better than in the text layer. It
returns structured data: the topics, and for every problem its kind, the
mathematics in Slate's answer syntax, its own worked answer, hints and steps.
Nothing it returns is trusted yet: ``verify.py`` checks each problem.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from slate_skills import all_skills

from .kinds import KINDS

log = logging.getLogger(__name__)

MAX_BATCH_CHARS = 9000
# About twenty pages: a review sheet or past exam fits; a long textbook chapter is read from the start.
MAX_TOTAL_CHARS = 60_000
SPEC_FIELDS = ("expr", "var", "name", "at", "equation", "dependent", "to", "side", "lower", "upper", "interval",
               "goal", "report", "estimate", "relation", "variables", "values", "rates", "find")

Kind = Literal[
    "derivative", "implicit_derivative", "tangent_line", "linear_approx", "limit", "antiderivative",
    "definite_integral", "solve", "critical_points", "extremum", "related_rates", "other",
]
assert set(Kind.__args__) == {*KINDS, "other"}  # type: ignore[attr-defined]


class StepOut(BaseModel):
    title: str = Field(description="A few words, math in $...$")
    latex: str = Field(description="One line of LaTeX, no dollar signs")


class TopicOut(BaseModel):
    name: str = Field(description="The topic as a calculus course names it, e.g. Related rates")
    summary: str = Field(description="One sentence on what it covers")
    builtin: str = Field(description="The id of the built-in skill this topic is exactly, or none")


class ProblemOut(BaseModel):
    label: str = Field(description="Its number as printed, like 4 or 2b; empty if none")
    chunk: int = Field(description="N of the [chunk N] block it appears in")
    topic: str = Field(description="The name of one of the topics")
    kind: Kind
    word: bool = Field(description="True for a word problem told as a story")
    statement: str = Field(description="The problem, self-contained, math in $...$")
    difficulty: int = Field(description="1 easy, 2 medium, 3 hard, 4 challenge")
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
    answer: str = Field(description="Your final answer in Slate syntax")
    hints: list[str] = Field(description="Exactly three hints, math in $...$")
    steps: list[StepOut]
    reason: str = Field(description="For kind other: why a computer can't check it; otherwise empty")


class SheetReading(BaseModel):
    topics: list[TopicOut]
    problems: list[ProblemOut]


SYNTAX = """# Slate syntax, for every math field and answer
Plain math as a student would type it: x^2, 3x, sqrt(x), cbrt(x), e^(2x), ln(x), sin(x)^2, arctan(x), abs(x), pi, 1/2. ln is the natural log; write a base-10 log as ln(x)/ln(10). Only numbers as constants: a problem with letters like a, k or C standing for unknown constants is kind "other". Use only these variable letters: x t y r s u v w z h. Rename any other variable (θ becomes t) and use the new letter in the statement too."""

KINDS_GUIDE = """# Kinds and their fields
derivative: f'(x), dy/dx, or the derivative's value at a point. expr is the function, var its variable, name the letter the problem uses (f, g or y), at the point (like 2) when it asks for the value there. answer: the derivative, or the number when at is given.
implicit_derivative: dy/dx on a curve given by an equation. equation like x^2 + xy + y^2 = 7, var x, dependent y, at like "x=1, y=2" when the value at a point is asked. answer: dy/dx in x and y, or the number.
tangent_line: the tangent line at a point. For y = f(x): expr, var and at (the x-value). For a curve: equation, var, dependent and at like "x=1, y=2". answer: y = mx + b.
linear_approx: the linearization at a. expr, var, at. With estimate (the x to estimate at, like 4.1) the answer is the estimated number; without it the answer is L(x) = ....
limit: expr, var, to (a number, oo or -oo) and side (both, left or right). answer: a number, oo, -oo or DNE.
antiderivative: an indefinite integral. expr, var. answer: an antiderivative + C.
definite_integral: expr, var, lower, upper. answer: a number.
solve: the real solutions of an equation. Use it also for "find every c that satisfies the Mean Value Theorem" or "where is the tangent horizontal": write the equation to solve. equation, var, interval (like [0, 2pi] when the problem restricts it, else ""). answer: the solutions separated by commas, or none.
critical_points: expr, var, interval ("" for the whole domain). answer: the x-values separated by commas, or none.
extremum: an absolute maximum or minimum on an interval, including an optimization word problem once you have set it up as one function of one variable. expr, var, interval (like [0, 4], or (0, oo) when open), goal (max or min), report (value for the extreme value itself, location for where it happens). answer: a number, or the x-values separated by commas.
related_rates: relation is one equation linking the changing quantities (substitute any that stay fixed), variables lists them (like "x, y"), values gives every variable's value at that instant (like "x=3, y=4", working out any the problem doesn't state), rates gives every known rate d/dt (like "x=2", negative when decreasing), find is the variable whose rate is asked. answer: that rate as a number.
other: anything else, such as proofs, explanations, sketches, intervals of increase or concavity, reading a graph or table. Fill statement, hints, steps, answer (in words if needed) and reason, and leave the math fields empty."""


def _builtin_list() -> str:
    return "\n".join(f"- {s.id}: {s.title}. {s.summary}" for s in all_skills())


SYSTEM = f"""You read a student's calculus course material (a review sheet, a past exam, homework, slides or notes) and turn every problem in it into structured data that a computer algebra system can check. A program parses each math field you write, computes the answer itself with SymPy, and uses a problem only if your answer agrees with its own. Accuracy matters more than coverage: if you aren't sure what a problem says, make it kind "other" and say why.

# Topics
List the topics the material practices, each once, in the order they first appear. Name them as a calculus course would: "Related rates", "Limits at infinity", "Chain rule". Judge a problem's topic by the mathematics it needs, not by its wording: "Find dy/dx if y = sin(x^3)" is the chain rule even though it never says so. A syllabus or an outline has topics and no problems.

These skills are built in. When a topic is exactly one of them, put its id in builtin; otherwise put none:
{_builtin_list()}

# Problems
One entry per thing the student is asked to do. Split a problem with parts (a), (b), (c) into entries labeled 3a, 3b, 3c, and make each statement self-contained by repeating the function or setup it relies on. In slides or notes, include the exercises and the examples a student could try on their own.

For each problem:
- label: its number as printed ("4", "2b"), or "" if it has none.
- chunk: the N of the [chunk N] block it is in.
- topic: the name of one of your topics.
- kind: one of the kinds below, or "other" when none fits exactly.
- word: true for a word problem told as a story (rates, optimization, motion).
- statement: what the student should see, self-contained, with every piece of math in LaTeX between single dollar signs, like: Find $\\frac{{dy}}{{dx}}$ if $x^2 + xy = 7$.
- difficulty: 1 easy, 2 medium, 3 hard, 4 challenge.
- the math fields its kind uses (below). Every field its kind doesn't use is "".
- answer: your own final answer, worked out carefully, in Slate syntax for its kind.
- hints: exactly three hints that lead toward the answer without giving it away: a nudge, a bigger hint, then nearly all of the first step. Math in $...$.
- steps: the worked solution in 2 to 6 steps, each a short title (words, math in $...$) and one line of LaTeX with no dollar signs.
- reason: for kind "other", one sentence for the student on why a computer can't check it (it asks for a proof, a sketch, an explanation, intervals). Otherwise "".

{SYNTAX}

{KINDS_GUIDE}"""


@dataclass(frozen=True)
class Block:
    """A chunk of the material as Claude sees it."""

    number: int
    locator: str
    text: str


def batches(blocks: list[Block], max_chars: int = MAX_BATCH_CHARS) -> list[list[Block]]:
    """Group consecutive chunks so each request reads a few pages at most."""
    out: list[list[Block]] = []
    size = 0
    for block in blocks:
        if out and size + len(block.text) <= max_chars:
            out[-1].append(block)
            size += len(block.text)
        else:
            out.append([block])
            size = len(block.text)
    return out


def content(title: str, kind_label: str, blocks: list[Block], images: list[tuple[str, bytes]],
            topics: list[str], known: list[str] | None = None) -> list[dict]:
    parts: list[dict] = []
    for label, png in images:
        parts.append({"type": "text", "text": f"Page image ({label}):"})
        parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                  "data": base64.standard_b64encode(png).decode()}})
    text = [f'Material: "{title}" ({kind_label}).']
    if known:
        text.append("The student already has these topics from other material; when a topic here is one of them, "
                    "use exactly the same name: " + "; ".join(known) + ".")
    if topics:
        text.append("Topics already found in earlier parts of this material (reuse these names when they fit): "
                    + "; ".join(topics) + ".")
    if images:
        text.append("The page images show the same material as the text below; trust the images for the math.")
    for block in blocks:
        text.append(f"\n[chunk {block.number}] {block.locator}\n{block.text}")
    parts.append({"type": "text", "text": "\n".join(text)})
    return parts


def spec_of(problem: BaseModel) -> dict:
    """The spec ``kinds.py`` reads: the kind and the math fields that are filled in.

    ``problem`` is a :class:`ProblemOut` or anything with the same math fields
    (a lesson's worked example)."""
    spec: dict = {"kind": problem.kind}
    for name in SPEC_FIELDS:
        value = str(getattr(problem, name) or "").strip()
        if value:
            spec[name] = value
    return spec


def read_material(llm, *, title: str, kind_label: str, blocks: list[Block],
                  images: list[tuple[str, bytes]], known: list[str] | None = None) -> SheetReading:
    """Read every chunk, a few pages per request. Images go with the first request only."""
    total = 0
    kept: list[Block] = []
    for block in blocks:
        if total + len(block.text) > MAX_TOTAL_CHARS:
            log.info("reading stopped after %d characters of %r", total, title)
            break
        kept.append(block)
        total += len(block.text)
    groups = batches(kept) or [[]]
    topics: list = []
    problems: list = []
    for index, group in enumerate(groups):
        reading = llm.structured(
            system=SYSTEM,
            content=content(title, kind_label, group, images if index == 0 and len(groups) == 1 else [],
                            [t.name for t in topics], known),
            schema=SheetReading, effort="medium", max_tokens=20000,
        )
        known = {t.name.strip().lower() for t in topics}
        topics += [t for t in reading.topics if t.name.strip().lower() not in known]
        problems += reading.problems
    return SheetReading(topics=topics, problems=problems)
