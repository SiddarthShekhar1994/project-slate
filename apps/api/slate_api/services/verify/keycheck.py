"""Verify a built problem before it can be shown to anyone.

``verify_built`` recomputes the answer with an oracle that does not share code
with the skill template, and runs the structural checks below. A problem is
servable only if every check passes; :mod:`slate_api.services.problem_gen`
enforces that by construction.

Checks:

``oracle``          template key equals the oracle's answer (proven, not just numerically)
``finite``          key and expression contain no infinities or NaN; point answers are numbers
``well_formed``     only the allowed symbols appear and the function really depends on its variable
``steps``           the last checkable step equals the key, and every step value is finite
``signature``       each signature mistake gives an answer different from the key
``mistakes``        every mistake pattern runs without error on this problem
``text``            hints, notes and the prompt render without missing placeholders
``size``            key and expression are small enough to read and type
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sympy as sp
from slate_skills.core.text import render
from slate_skills.core.types import Built, SkillSpec

from .equivalence import Equivalence, equivalent, numeric_screen

MAX_KEY_OPS = 70
MAX_EXPR_OPS = 45
MAX_PROMPT_CHARS = 600
MAX_COEFFICIENT = 10**5


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    oracle: str
    method: str
    checks: tuple[Check, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "oracle": self.oracle,
            "method": self.method,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks],
        }


def constraint_of(built: Built) -> sp.Expr | None:
    """The curve ``F(x, y) = 0`` that implicit answers only need to agree on."""
    return built.expr if built.task == "implicit_differentiate" else None


def oracle_answer(built: Built) -> tuple[str, sp.Expr]:
    """Recompute the answer directly from the problem statement."""
    if built.task == "differentiate":
        answer = sp.diff(built.expr, built.var)
        name = "sympy.diff"
    elif built.task == "implicit_differentiate":
        if built.dependent is None:
            raise ValueError("implicit problem without a dependent variable")
        # Implicit function theorem: dy/dx = -F_x / F_y.
        fx = sp.diff(built.expr, built.var)
        fy = sp.diff(built.expr, built.dependent)
        answer = -fx / fy
        name = "implicit_function_theorem"
    else:
        raise ValueError(f"no oracle for task {built.task!r}")
    if built.at:
        answer = sp.simplify(answer.subs(built.at))
    return name, answer


def _finite(expr: sp.Expr) -> bool:
    return not expr.has(sp.zoo, sp.nan, sp.oo, -sp.oo)


def _max_coefficient(expr: sp.Expr) -> int:
    nums = [abs(n) for n in expr.atoms(sp.Rational)]
    biggest = 0
    for n in nums:
        biggest = max(biggest, int(abs(n.p)), int(abs(n.q)))
    return biggest


def _check_oracle(built: Built) -> tuple[Check, str, str]:
    try:
        oracle_name, answer = oracle_answer(built)
    except Exception as exc:  # the oracle itself failing is a verification failure
        return Check("oracle", False, f"oracle raised {type(exc).__name__}: {exc}"), "error", "none"
    symbols = () if built.at else built.symbols
    constraint = None if built.at else constraint_of(built)
    eq: Equivalence = equivalent(built.key, answer, symbols, constraint=constraint)
    if eq.proven:
        return Check("oracle", True, f"key equals {oracle_name} result ({eq.method})"), oracle_name, eq.method
    return (
        Check("oracle", False, f"key {built.key} does not match {oracle_name} result {answer} ({eq.method})"),
        oracle_name,
        eq.method,
    )


def _check_finite(built: Built) -> Check:
    if not _finite(built.key) or not _finite(built.expr):
        return Check("finite", False, "key or expression is infinite or undefined")
    if built.at:
        if built.key.free_symbols:
            return Check("finite", False, f"point answer still has symbols: {built.key}")
        value = sp.N(built.key, 20)
        if not value.is_finite or abs(sp.im(value)) > 1e-12:
            return Check("finite", False, f"point answer is not a finite real number: {value}")
    return Check("finite", True)


def _check_well_formed(built: Built) -> Check:
    allowed = set(built.symbols)
    extra = (built.expr.free_symbols | built.key.free_symbols) - allowed
    if extra:
        return Check("well_formed", False, f"unexpected symbols {sorted(map(str, extra))}")
    if built.var not in built.expr.free_symbols:
        return Check("well_formed", False, f"expression does not depend on {built.var}")
    if built.task == "implicit_differentiate" and built.dependent not in built.expr.free_symbols:
        return Check("well_formed", False, "implicit curve does not involve the dependent variable")
    return Check("well_formed", True)


def _check_steps(built: Built) -> Check:
    if not built.steps:
        return Check("steps", False, "no steps")
    ids = [s.id for s in built.steps]
    if len(ids) != len(set(ids)):
        return Check("steps", False, "duplicate step ids")
    for step in built.steps:
        if step.expr is not None and not _finite(step.expr):
            return Check("steps", False, f"step {step.id} is undefined")
    checkable = [s for s in built.steps if s.expr is not None]
    if not checkable:
        return Check("steps", False, "no checkable step")
    last = checkable[-1].expr
    symbols = () if built.at and not last.free_symbols else built.symbols
    eq = equivalent(last, built.key, symbols, constraint=None if built.at else constraint_of(built))
    if not eq.proven:
        return Check("steps", False, f"last step {checkable[-1].id} does not equal the key ({eq.method})")
    return Check("steps", True)


def _check_mistakes(skill: SkillSpec, built: Built) -> tuple[Check, Check]:
    constraint = None if built.at else constraint_of(built)
    symbols = built.symbols if not built.at else ()
    failures: list[str] = []
    collisions: list[str] = []
    for pattern in skill.mistakes:
        try:
            wrong = pattern.buggy(built)
        except Exception as exc:
            failures.append(f"{pattern.tag}@{pattern.step}: {type(exc).__name__}: {exc}")
            continue
        if wrong is None:
            continue
        if not isinstance(wrong, sp.Basic):
            failures.append(f"{pattern.tag}@{pattern.step}: returned {type(wrong).__name__}")
            continue
        if not pattern.signature:
            continue
        verdict, _ = numeric_screen(wrong, built.key, symbols, constraint)
        if verdict is not False:
            # Not separable by numbers; fall back to a symbolic check before rejecting.
            if equivalent(wrong, built.key, symbols, constraint=constraint).equal is not False:
                collisions.append(pattern.tag)
    mistakes = Check("mistakes", not failures, "; ".join(failures))
    signature = Check(
        "signature",
        not collisions,
        f"signature mistakes give the right answer: {', '.join(collisions)}" if collisions else "",
    )
    return mistakes, signature


def _check_text(skill: SkillSpec, built: Built) -> Check:
    try:
        ladder = skill.hint_ladder(built)
        for template in (ladder.nudge, ladder.bigger, ladder.full_step):
            render(template, built)
        for pattern in skill.mistakes:
            render(pattern.note, built)
        for step in built.steps:
            render(step.title, built)
    except (KeyError, ValueError) as exc:
        return Check("text", False, f"template error: {exc}")
    if len(built.prompt) > MAX_PROMPT_CHARS:
        return Check("text", False, "prompt too long")
    if built.prompt.count("$") % 2:
        return Check("text", False, "prompt has an unbalanced $")
    return Check("text", True)


def _check_size(built: Built) -> Check:
    key_ops = sp.count_ops(built.key)
    expr_ops = sp.count_ops(built.expr)
    if key_ops > MAX_KEY_OPS:
        return Check("size", False, f"key too long ({key_ops} ops)")
    if expr_ops > MAX_EXPR_OPS:
        return Check("size", False, f"expression too long ({expr_ops} ops)")
    biggest = max(_max_coefficient(built.key), _max_coefficient(built.expr))
    if biggest > MAX_COEFFICIENT:
        return Check("size", False, f"coefficient {biggest} is too large")
    return Check("size", True)


def verify_built(skill: SkillSpec, built: Built) -> VerificationReport:
    """Run every check. ``ok`` is true only if all of them pass."""
    if built.task != skill.task:
        check = Check("task", False, f"skill task {skill.task} but problem task {built.task}")
        return VerificationReport(False, "none", "none", (check,))

    oracle_check, oracle_name, method = _check_oracle(built)
    checks = [oracle_check, _check_finite(built), _check_well_formed(built)]
    # Later checks assume a sound key; skip them if the oracle already failed.
    if oracle_check.passed:
        mistakes, signature = _check_mistakes(skill, built)
        checks += [_check_steps(built), mistakes, signature, _check_text(skill, built), _check_size(built)]
    ok = all(c.passed for c in checks)
    return VerificationReport(ok=ok, oracle=oracle_name, method=method, checks=tuple(checks))
