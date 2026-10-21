"""Check a student's answer and, when it is wrong, say which mistake it was.

Correctness is decided symbolically against the verified key (see
:mod:`slate_api.services.verify.equivalence`), never by comparing strings.

A wrong answer gets exactly one mistake tag, chosen in this order:

1. The skill's own mistake patterns. Each pattern computes the answer a
   specific error would produce on this problem; a match is the strongest
   evidence there is.
2. The expected intermediate steps. An answer equal to a step's value (for
   example the outer derivative without the inner factor) means the student
   stopped there; the step's ``partial_tag`` names the mistake.
3. Generic comparisons with the key: a flipped sign, a constant factor off,
   one term missing, or the right building blocks combined wrongly while
   simplifying.
4. ``unclassified``.

The tag is stored with the attempt; the Progress page ranks tags by count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import sympy as sp
from slate_skills.core.mistakes import mistake_type
from slate_skills.core.text import render, tex
from slate_skills.core.types import Built, SkillSpec, Step

from ..problem_gen import VerifiedProblem
from ..verify import ParseError, constant_ratio, constraint_of, equivalent, numeric_screen, parse_answer

GradeStatus = Literal["correct", "incorrect", "invalid"]


@dataclass(frozen=True)
class MistakeResult:
    tag: str
    label: str
    category: str
    step_id: str | None
    step_title: str | None
    where_to_look: str
    evidence: str


@dataclass(frozen=True)
class Grade:
    status: GradeStatus
    latex: str | None = None
    message: str | None = None
    method: str | None = None
    mistake: MistakeResult | None = None
    normalized: str | None = None

    @property
    def correct(self) -> bool:
        return self.status == "correct"


# --- context ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    built: Built
    symbols: tuple[sp.Symbol, ...]
    constraint: sp.Expr | None

    def at_point(self, expr: sp.Expr) -> sp.Expr:
        return expr.subs(self.built.at) if self.built.at else expr

    def same(self, a: sp.Expr, b: sp.Expr) -> bool:
        """Equal for tagging purposes: proven, or undecided with numbers agreeing."""
        verdict, _ = numeric_screen(a, b, self.symbols, self.constraint)
        if verdict is False:
            return False
        return equivalent(a, b, self.symbols, constraint=self.constraint).equal is not False


def _context(built: Built) -> _Context:
    if built.at:
        return _Context(built, (), None)
    return _Context(built, built.symbols, constraint_of(built))


def _step(built: Built, step_id: str | None) -> Step | None:
    for step in built.steps:
        if step.id == step_id:
            return step
    return None


def _last_checkable_step(built: Built) -> Step:
    steps = [s for s in built.steps if s.expr is not None and s.id != "evaluate"]
    return steps[-1] if steps else built.steps[-1]


def _result(tag: str, built: Built, step: Step | None, note: str, evidence: str) -> MistakeResult:
    kind = mistake_type(tag)
    return MistakeResult(
        tag=tag,
        label=kind.label,
        category=kind.category,
        step_id=step.id if step else None,
        step_title=step.title if step else None,
        where_to_look=note,
        evidence=evidence,
    )


# --- generic detectors --------------------------------------------------------------


def _additive_terms(key: sp.Expr) -> tuple[list[sp.Expr], sp.Expr] | None:
    """Split the key into terms that a student could flip or drop.

    Returns ``(terms, multiplier)`` with ``key == multiplier * Add(*terms)``.
    A plain sum gives its own terms; a product with one sum factor (a quotient
    rule numerator over g^2, or (6x + 6) e^u) gives that factor's terms.
    """
    if isinstance(key, sp.Add):
        return list(key.args), sp.Integer(1)
    if isinstance(key, sp.Mul):
        sums = [f for f in key.args if isinstance(f, sp.Add)]
        if len(sums) == 1:
            rest = sp.Mul(*[f for f in key.args if f is not sums[0]])
            return list(sums[0].args), rest
    return None


def _sign_error(ctx: _Context, student: sp.Expr, key: sp.Expr) -> bool:
    if ctx.same(student, -key):
        return True
    split = _additive_terms(key)
    if split is None:
        return False
    terms, mult = split
    if len(terms) < 2:
        return False
    for i in range(len(terms)):
        flipped = [(-t if j == i else t) for j, t in enumerate(terms)]
        if ctx.same(student, ctx.at_point(mult * sp.Add(*flipped))):
            return True
    return False


def _dropped_term(ctx: _Context, student: sp.Expr, key: sp.Expr) -> bool:
    split = _additive_terms(key)
    if split is None:
        return False
    terms, mult = split
    if len(terms) < 2:
        return False
    for i in range(len(terms)):
        kept = [t for j, t in enumerate(terms) if j != i]
        if ctx.same(student, ctx.at_point(mult * sp.Add(*kept))):
            return True
    return False


def _coefficient_ratio(ctx: _Context, student: sp.Expr, key: sp.Expr) -> sp.Expr | None:
    """``student / key`` when it is a constant other than 0, 1 and -1."""
    if ctx.built.at or key == 0:
        return None
    ratio = constant_ratio(student, key, ctx.symbols, ctx.constraint)
    if ratio is None or ratio in (1, -1):
        return None
    return ratio


def _building_blocks(expr: sp.Expr, symbols: Sequence[sp.Symbol]) -> set[sp.Basic]:
    """Function applications and non-integer powers that involve the variables."""
    blocks: set[sp.Basic] = set()
    for node in sp.preorder_traversal(expr):
        if isinstance(node, sp.Function) and node.free_symbols & set(symbols):
            blocks.add(node)
        elif isinstance(node, sp.Pow) and not node.exp.is_Integer and node.free_symbols & set(symbols):
            blocks.add(node.base)
    return blocks


def _algebra_slip(ctx: _Context, student: sp.Expr, key: sp.Expr) -> bool:
    """Same building blocks as the key, combined wrongly.

    Comparing the transcendental pieces (``cos(x^3+1)``, ``sqrt(x^2+2)``) tells
    apart a student who applied the rule and then fumbled the algebra from one
    who applied the wrong rule, without needing to know their working.
    """
    if ctx.built.at:
        return False
    key_blocks = _building_blocks(key, ctx.symbols)
    student_blocks = _building_blocks(student, ctx.symbols)
    if key_blocks:
        return key_blocks == student_blocks
    # Polynomial or rational keys: same variables and degree ballpark.
    try:
        kd = sp.Poly(sp.fraction(sp.together(key))[0], *ctx.symbols).total_degree()
        sd = sp.Poly(sp.fraction(sp.together(student))[0], *ctx.symbols).total_degree()
    except (sp.PolynomialError, sp.GeneratorsNeeded):
        return False
    return kd == sd and student.free_symbols == key.free_symbols


def _generic_note(tag: str, step: Step, ratio: sp.Expr | None = None) -> str:
    where = f'Look again at the step "{step.title}".'
    if tag == "sign_error":
        return f"Your answer has the right pieces but a sign is flipped. {where}"
    if tag == "coefficient_slip":
        return f"The structure is right but your answer is ${tex(ratio)}$ times the correct one. Recheck the constants. {where}"
    if tag == "dropped_term":
        return f"Your answer is missing one of the terms. {where}"
    if tag == "algebra_slip":
        return f"You used the right pieces, so the rule went fine. Something slipped while simplifying. {where}"
    return "This doesn't match a common mistake. Try the first hint, then compare each step with the worked solution."


# --- classification ------------------------------------------------------------------


def classify_mistake(skill: SkillSpec, built: Built, student: sp.Expr) -> MistakeResult:
    """Pick the single best mistake tag for a wrong ``student`` answer."""
    ctx = _context(built)

    for pattern in skill.mistakes:
        try:
            wrong = pattern.buggy(built)
        except Exception:  # a broken pattern must not block grading
            continue
        if wrong is None:
            continue
        if ctx.same(student, wrong):
            return _result(pattern.tag, built, _step(built, pattern.step), render(pattern.note, built),
                           f"pattern:{pattern.tag}@{pattern.step}")

    key = built.key
    for step in built.steps:
        if step.expr is None or step.partial_tag is None:
            continue
        value = ctx.at_point(step.expr)
        if ctx.same(value, key):
            continue
        if ctx.same(student, value):
            note = (f'Your answer matches the step "{step.title}" but stops there. '
                    "Keep going from that step to finish the derivative.")
            return _result(step.partial_tag, built, step, note, f"partial_step:{step.id}")

    last = _last_checkable_step(built)
    if _sign_error(ctx, student, key):
        return _result("sign_error", built, last, _generic_note("sign_error", last), "generic:sign")
    ratio = _coefficient_ratio(ctx, student, key)
    if ratio is not None:
        return _result("coefficient_slip", built, last, _generic_note("coefficient_slip", last, ratio),
                       "generic:ratio")
    if _dropped_term(ctx, student, key):
        return _result("dropped_term", built, last, _generic_note("dropped_term", last), "generic:dropped_term")
    if _algebra_slip(ctx, student, key):
        return _result("algebra_slip", built, last, _generic_note("algebra_slip", last), "generic:building_blocks")
    return _result("unclassified", built, None, _generic_note("unclassified", last), "none")


# --- grading -----------------------------------------------------------------------


def _rounded_match(student: sp.Expr, key: sp.Expr, places: int) -> bool:
    """A decimal answer that is the key correctly rounded to the places typed."""
    if places < 2 or student.free_symbols or key.free_symbols:
        return False
    tolerance = sp.Rational(1, 2) * sp.Rational(1, 10**places)
    try:
        return bool(abs(sp.N(student - key, 30)) <= tolerance)
    except TypeError:
        return False


def grade_answer(problem: VerifiedProblem, raw: str) -> Grade:
    """Grade ``raw`` against a verified problem."""
    built = problem.built
    try:
        parsed = parse_answer(raw, built.symbols)
    except ParseError as exc:
        return Grade(status="invalid", message=str(exc))

    student = parsed.expr
    if built.at and student.free_symbols:
        names = ", ".join(sorted(str(s) for s in student.free_symbols))
        point = ", ".join(f"{tex(k)} = {tex(v)}" for k, v in built.at.items())
        return Grade(status="invalid", latex=parsed.latex,
                     message=f"This asks for a number, but your answer still has {names} in it. "
                             f"Plug in ${point}$.")

    ctx = _context(built)
    eq = equivalent(student, built.key, ctx.symbols, constraint=ctx.constraint)
    normalized = sp.srepr(student)
    if eq.equal is True:
        return Grade(status="correct", latex=parsed.latex, method=eq.method, normalized=normalized)
    if eq.equal is None:
        # Numbers agree at every sample point but no rewrite proved it. Accept and
        # record the method so these cases can be audited.
        return Grade(status="correct", latex=parsed.latex, method="numeric_agreement", normalized=normalized)
    if parsed.has_decimal and _rounded_match(student, built.key, parsed.decimal_places):
        return Grade(status="correct", latex=parsed.latex, method="rounded_decimal", normalized=normalized)

    mistake = classify_mistake(problem.skill, built, student)
    return Grade(status="incorrect", latex=parsed.latex, method=eq.method, mistake=mistake, normalized=normalized)
