"""Data types every skill file is written against.

A skill file declares *what* to generate (families of parameterised problems),
*how* a correct solution unfolds (steps), and *how students usually go wrong*
(mistake patterns). It never decides whether a problem is fit to show: that is
the verifier's job in ``apps/api``, which recomputes every answer key with an
independent SymPy oracle before a problem can be served.

Text fields that end up in the UI (step titles, notes, hints) use inline
``$...$`` for math. Inside a template, ``[[name]]`` is replaced with the LaTeX of
``Built.parts[name]`` and ``[[name:yellow]]`` / ``[[name:mint]]`` wraps it in the
board highlight colour. See :func:`slate_skills.core.text.render`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any, Callable, Literal, Mapping

import sympy as sp

TaskKind = Literal[
    "differentiate", "implicit_differentiate",
    "tangent_line", "linear_approx", "limit", "antiderivative", "definite_integral", "solve", "critical_points",
    "extremum", "related_rates",
]
"""What the student is asked to produce. The verifier owns one oracle per kind.

Skill templates use the first two. The rest are problems read from a
student's own course materials (``slate_api.services.materials``), whose
answer keys SymPy computes from a structured statement of the problem."""

Difficulty = int
"""1 = easy, 2 = medium, 3 = hard, 4 = challenge."""

DIFFICULTY_LABELS: dict[int, str] = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Challenge"}

Params = dict[str, Any]
"""JSON-serialisable sampled parameters. Stored with the problem so it can be rebuilt."""


@dataclass(frozen=True)
class Step:
    """One expected intermediate step of the worked solution.

    ``expr`` is the step's checkable value (an expression a student might hand
    in if they stopped here). ``partial_tag`` names the mistake to record when a
    student's *final* answer equals this step's value but not the key, e.g. a
    chain-rule answer that stops at the outer derivative.
    """

    id: str
    title: str
    latex: str
    expr: sp.Expr | None = None
    partial_tag: str | None = None


@dataclass(frozen=True)
class WordContext:
    """Story wrapper for a word problem. ``text`` holds inline ``$...$`` math."""

    text: str
    question: str
    unit: str = ""


@dataclass(frozen=True)
class Built:
    """A fully specified problem instance produced by a family's ``build``.

    ``key`` must come from walking the rule's steps (for example
    ``outer'(inner) * inner'``), never from ``sp.diff`` on ``expr``. The verifier
    compares it against its own oracle, so a template bug shows up as a failed
    verification instead of a wrong key in front of a student.

    For ``implicit_differentiate`` problems ``expr`` is ``F(x, y)`` where the
    curve is ``F(x, y) = 0``, ``equation`` is the equation as the student sees
    it, ``dependent`` is ``y``, and ``key`` is dy/dx in terms of ``x`` and ``y``.

    ``at`` asks for the derivative's value at a point (``{x: 2}``); the key is
    then a number and so is the expected answer.
    """

    family: str
    difficulty: Difficulty
    task: TaskKind
    var: sp.Symbol
    expr: sp.Expr
    key: sp.Expr
    steps: tuple[Step, ...]
    parts: Mapping[str, sp.Expr]
    params: Params
    prompt: str
    equation: sp.Equality | None = None
    dependent: sp.Symbol | None = None
    at: Mapping[sp.Symbol, sp.Expr] | None = None
    word: WordContext | None = None
    snippets: Mapping[str, str] = field(default_factory=dict)
    """Pre-rendered LaTeX for ``[[name]]`` placeholders that plain ``parts``
    cannot express, such as the outer function with its inner part coloured."""

    @property
    def symbols(self) -> tuple[sp.Symbol, ...]:
        """Symbols a student answer may use."""
        if self.dependent is not None:
            return (self.var, self.dependent)
        return (self.var,)


@dataclass(frozen=True)
class Family:
    """A parameterised problem template within one difficulty band.

    ``sample`` draws parameters from ``rng`` only (no global randomness) so a
    seed reproduces the same problem. ``build`` must be a pure function of the
    params.
    """

    id: str
    difficulty: Difficulty
    description: str
    sample: Callable[[Random], Params]
    build: Callable[[Params], Built]
    word: bool = False


@dataclass(frozen=True)
class MistakePattern:
    """A common wrong turn and the answer it leads to.

    ``buggy`` returns the answer a student making this mistake would hand in,
    or ``None`` when the mistake cannot happen on this problem. ``note`` is the
    "where to look" text shown after a wrong answer; it points at ``step``.

    ``signature`` marks the mistake the skill exists to catch (dropping the
    inner derivative for the chain rule). The verifier rejects a problem whose
    signature mistakes give the same answer as the key, because such a problem
    cannot tell a student who knows the rule from one who does not.
    """

    tag: str
    step: str
    buggy: Callable[[Built], sp.Expr | None]
    note: str
    signature: bool = False


@dataclass(frozen=True)
class FormulaEntry:
    """One formula-sheet line for the skill."""

    title: str
    latex: str
    note: str = ""


@dataclass(frozen=True)
class HintLadder:
    """Three hint levels as text templates (inline ``$...$`` and ``[[part]]``)."""

    nudge: str
    bigger: str
    full_step: str


@dataclass(frozen=True)
class SkillSpec:
    """Everything Slate knows about one skill.

    ``hints`` either is a fixed :class:`HintLadder` or computes one from the
    built problem when the wording depends on the family.
    ``keywords`` let ingestion map source chunks to this skill.
    """

    id: str
    slug: str
    title: str
    summary: str
    task: TaskKind
    families: tuple[Family, ...]
    mistakes: tuple[MistakePattern, ...]
    hints: HintLadder | Callable[[Built], HintLadder]
    formula: FormulaEntry
    keywords: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()

    def family(self, family_id: str) -> Family:
        for fam in self.families:
            if fam.id == family_id:
                return fam
        raise KeyError(f"{self.id} has no family {family_id!r}")

    def families_at(self, difficulty: Difficulty, *, word: bool | None = None) -> tuple[Family, ...]:
        return tuple(
            f for f in self.families if f.difficulty == difficulty and (word is None or f.word == word)
        )

    @property
    def difficulties(self) -> tuple[Difficulty, ...]:
        return tuple(sorted({f.difficulty for f in self.families}))

    def hint_ladder(self, built: Built) -> HintLadder:
        return self.hints(built) if callable(self.hints) else self.hints


@dataclass(frozen=True)
class Unit:
    id: str
    title: str
    skills: tuple[SkillSpec, ...]


@dataclass(frozen=True)
class Course:
    id: str
    title: str
    units: tuple[Unit, ...]
    description: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def skills(self) -> tuple[SkillSpec, ...]:
        return tuple(s for u in self.units for s in u.skills)
