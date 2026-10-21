"""Decide whether two expressions are mathematically the same.

Order of work:

1. Identical after SymPy's automatic evaluation: equal.
2. Numeric screen at fixed sample points, evaluated to 30 digits. Answers are
   compared on the reference expression's real domain: the sample points where
   ``b`` (the key) is real and finite. There ``a`` must be real and equal too.
   A point where they clearly differ proves the expressions are *not*
   equivalent, so most wrong answers stop here without any simplification.
   Comparing on the real domain matters for roots and logs: ``cbrt(x^2)`` and
   ``x^(2/3)`` are the same real function, but SymPy's principal branch makes
   ``x^(2/3)`` complex for negative ``x``.
3. Symbolic proof: ``simplify(a - b) == 0`` first, then a short chain of other
   rewrites for identities ``simplify`` misses (``sec^2 u = tan^2 u + 1`` is the
   usual one), then ``Expr.equals``. If the real domain lies in ``x > 0`` (every
   usable sample point is positive), the chain is retried with positive
   symbols, which is what proves ``cbrt(x^2) = x^(2/3)`` or
   ``ln(x^2) = 2 ln x`` there.
4. With a ``constraint`` (implicit differentiation, where answers only need to
   agree on the curve ``F(x, y) = 0``), the numerator of ``a - b`` is reduced
   modulo ``F``; a zero remainder is a proof.

When numbers agree everywhere but no rewrite proves it, the result is
``equal=None`` (undecided). Callers choose: key verification treats undecided as
a failure, grading treats it as correct and records the method for audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterable, Sequence

import mpmath
import sympy as sp
from sympy.functions.elementary.trigonometric import TrigonometricFunction

# Awkward values so that special angles and integer roots don't produce false agreement.
_SAMPLE_VALUES: tuple[str, ...] = (
    "0.3711", "1.2397", "-0.8513", "2.1731", "-1.6029", "0.6177", "2.9113", "-2.3349", "0.0917", "1.7803",
    "3.6271", "-3.1873", "4.4417", "-0.2659",
)
_DIGITS = 30
_REL_TOL = mpmath.mpf("1e-12")
_MAX_MAGNITUDE = mpmath.mpf("1e12")
MIN_NUMERIC_POINTS = 4


@dataclass(frozen=True)
class Equivalence:
    equal: bool | None
    method: str
    numeric_points: int = 0

    @property
    def proven(self) -> bool:
        return self.equal is True


def _to_mpc(value: sp.Basic) -> mpmath.mpc | None:
    if not value.is_number or value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        return None
    try:
        re_, im_ = value.as_real_imag()
        out = mpmath.mpc(mpmath.mpf(sp.Float(re_, _DIGITS)._mpf_), mpmath.mpf(sp.Float(im_, _DIGITS)._mpf_))
    except (TypeError, ValueError, AttributeError, ZeroDivisionError, OverflowError):
        return None
    if not (mpmath.isfinite(out.real) and mpmath.isfinite(out.imag)) or abs(out) > _MAX_MAGNITUDE:
        return None
    return out


def _evaluate(expr: sp.Expr, point: dict[sp.Symbol, sp.Expr]) -> mpmath.mpc | None:
    try:
        value = expr.evalf(_DIGITS, subs=point)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return None
    return _to_mpc(value)


@lru_cache(maxsize=256)
def _curve_points(constraint: sp.Expr, xs: sp.Symbol, ys: sp.Symbol) -> tuple[tuple[sp.Float, sp.Float], ...]:
    """Real points on ``constraint = 0`` found by solving for ``ys`` at sample ``xs``."""
    points: list[tuple[sp.Float, sp.Float]] = []
    for raw in _SAMPLE_VALUES:
        x0 = sp.Float(raw, _DIGITS)
        f = sp.expand(constraint.subs(xs, x0))
        roots: Iterable[sp.Expr] = ()
        try:
            if f.is_polynomial(ys):
                poly = sp.Poly(f, ys)
                if poly.degree() >= 1:
                    roots = poly.nroots(n=_DIGITS, maxsteps=200)
            else:
                guesses = (sp.Float("0.5"), sp.Float("-1.5"), sp.Float("2.5"))
                found = []
                for g in guesses:
                    try:
                        found.append(sp.nsolve(f, ys, g, prec=_DIGITS))
                    except (ValueError, ZeroDivisionError, TypeError):
                        continue
                roots = found
        except (sp.PolynomialError, ValueError, mpmath.libmp.libhyper.NoConvergence):
            roots = ()
        for r in roots:
            r = sp.N(r, _DIGITS)
            if abs(sp.im(r)) < 1e-20:
                y0 = sp.re(r)
                if all(abs(y0 - p[1]) > 1e-12 or abs(x0 - p[0]) > 1e-12 for p in points):
                    points.append((x0, y0))
    return tuple(points)


def curve_points(constraint: sp.Expr, xs: sp.Symbol, ys: sp.Symbol) -> tuple[tuple[sp.Float, sp.Float], ...]:
    """Real sample points on the curve ``constraint = 0``."""
    return _curve_points(constraint, xs, ys)


def real_sample_values(expr: sp.Expr, var: sp.Symbol) -> int:
    """How many sample points give a finite real value of ``expr``."""
    count = 0
    with mpmath.workdps(_DIGITS):
        for raw in _SAMPLE_VALUES:
            value = _evaluate(expr, {var: sp.Float(raw, _DIGITS)})
            if value is not None and abs(value.imag) <= _REL_TOL * max(mpmath.mpf(1), abs(value)):
                count += 1
    return count


def _sample_points(symbols: Sequence[sp.Symbol], constraint: sp.Expr | None) -> list[dict[sp.Symbol, sp.Expr]]:
    if constraint is not None and len(symbols) == 2:
        xs, ys = symbols
        return [{xs: px, ys: py} for px, py in _curve_points(constraint, xs, ys)]
    if not symbols:
        return [{}]
    n = len(_SAMPLE_VALUES)
    points = []
    for i in range(n):
        # Stagger values per symbol so two-variable points don't sit on y = x.
        points.append({s: sp.Float(_SAMPLE_VALUES[(i + 3 * k) % n], _DIGITS) for k, s in enumerate(symbols)})
    return points


@dataclass(frozen=True)
class Screen:
    """Outcome of the numeric screen.

    ``verdict`` is False on a counterexample, True when every usable point
    agrees, and None when too few points could be evaluated. ``positive`` says
    every usable point had all symbols positive.
    """

    verdict: bool | None
    points: int
    positive: bool


def _is_real(value: mpmath.mpc) -> bool:
    return abs(value.imag) <= _REL_TOL * max(mpmath.mpf(1), abs(value))


def screen(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol], constraint: sp.Expr | None = None) -> Screen:
    """Compare ``a`` with the reference ``b`` at sample points (see module docs)."""
    with mpmath.workdps(_DIGITS):
        evaluated = []
        for point in _sample_points(symbols, constraint):
            vb = _evaluate(b, point)
            if vb is not None:
                evaluated.append((point, vb))
        domain = [(p, vb) for p, vb in evaluated if _is_real(vb)]
        real_domain = len(domain) >= MIN_NUMERIC_POINTS
        if not real_domain:
            domain = evaluated

        agree = 0
        for point, vb in domain:
            va = _evaluate(a, point)
            if va is None:
                continue
            if real_domain and not _is_real(va):
                return Screen(False, agree, False)
            scale = max(mpmath.mpf(1), abs(va), abs(vb))
            if abs(va - vb) > _REL_TOL * scale:
                return Screen(False, agree, False)
            agree += 1
    positive = bool(symbols) and real_domain and all(
        all(point[s] > 0 for s in symbols) for point, _ in domain
    )
    if agree < MIN_NUMERIC_POINTS:
        return Screen(None, agree, positive)
    return Screen(True, agree, positive)


def numeric_screen(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol],
                   constraint: sp.Expr | None = None) -> tuple[bool | None, int]:
    """``(False, n)`` on a counterexample, ``(True, n)`` if all ``n`` usable points agree,
    ``(None, n)`` if fewer than :data:`MIN_NUMERIC_POINTS` points could be evaluated."""
    result = screen(a, b, symbols, constraint)
    return result.verdict, result.points


def _is_zero(expr: sp.Expr) -> bool:
    return expr == 0 or (expr.is_number and expr.is_zero is True)


def _rewrite_cos(d: sp.Expr) -> sp.Expr:
    return sp.simplify(d.rewrite(sp.cos))


def _rewrite_exp(d: sp.Expr) -> sp.Expr:
    return sp.simplify(d.rewrite(sp.exp))


def _cancel(d: sp.Expr) -> sp.Expr:
    return sp.cancel(sp.together(d))


def _expand_log_simplify(d: sp.Expr) -> sp.Expr:
    return sp.simplify(sp.expand_log(d))


_SYMBOLIC_CHAIN: tuple[tuple[str, Callable[[sp.Expr], sp.Expr]], ...] = (
    ("cancel", _cancel),
    ("simplify", sp.simplify),
    ("fu", sp.fu),
    ("rewrite_cos", _rewrite_cos),
    ("rewrite_exp", _rewrite_exp),
    ("expand_log", _expand_log_simplify),
)


def _chain_for(d: sp.Expr) -> tuple[tuple[str, Callable[[sp.Expr], sp.Expr]], ...]:
    # fu is cheap and proves the Pythagorean identities that simplify can spend
    # most of a second failing on, so try it first when trig is involved.
    if d.has(TrigonometricFunction):
        first = [step for step in _SYMBOLIC_CHAIN if step[0] in ("cancel", "fu")]
        return (*first, *(step for step in _SYMBOLIC_CHAIN if step not in first))
    return _SYMBOLIC_CHAIN


def symbolic_zero(d: sp.Expr) -> str | None:
    """Name of the first rewrite that reduces ``d`` to zero, or ``None``."""
    if _is_zero(d):
        return "identical"
    for name, rewrite in _chain_for(d):
        try:
            if _is_zero(rewrite(d)):
                return name
        except (TypeError, ValueError, ZeroDivisionError, RecursionError, NotImplementedError,
                sp.PolynomialError, AttributeError):
            continue
    try:
        if d.equals(0) is True:
            return "equals"
    except (TypeError, ValueError, ZeroDivisionError, RecursionError, NotImplementedError, AttributeError):
        pass
    return None


def _reduces_on_curve(d: sp.Expr, constraint: sp.Expr, symbols: Sequence[sp.Symbol]) -> bool:
    num, _ = sp.fraction(sp.together(d))
    num = sp.expand(num)
    poly_constraint = sp.expand(constraint)
    if not (num.is_polynomial(*symbols) and poly_constraint.is_polynomial(*symbols)):
        return False
    try:
        _, remainder = sp.reduced(num, [poly_constraint], *symbols)
    except (sp.PolynomialError, sp.polys.polyerrors.ComputationFailed):
        return False
    return _is_zero(sp.expand(remainder))


def _positive_version(d: sp.Expr, symbols: Sequence[sp.Symbol]) -> sp.Expr:
    return d.subs({s: sp.Symbol(s.name, positive=True) for s in symbols})


def equivalent(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol], *,
               constraint: sp.Expr | None = None) -> Equivalence:
    """Compare ``a`` with the reference ``b`` as functions of ``symbols``.

    ``b`` defines the domain: pass the key (or the oracle's answer) second.
    With a ``constraint`` the comparison is on the curve ``constraint = 0``.
    """
    a, b = sp.sympify(a), sp.sympify(b)
    d = a - b
    if _is_zero(d):
        return Equivalence(True, "identical")

    numeric = screen(a, b, symbols, constraint)
    if numeric.verdict is False:
        return Equivalence(False, "numeric_counterexample", numeric.points)

    method = symbolic_zero(d)
    if method is not None:
        return Equivalence(True, method, numeric.points)

    if constraint is not None and _reduces_on_curve(d, constraint, symbols):
        return Equivalence(True, "constraint_reduction", numeric.points)

    if numeric.verdict is True and numeric.positive and constraint is None:
        method = symbolic_zero(_positive_version(d, symbols))
        if method is not None:
            return Equivalence(True, f"positive_domain:{method}", numeric.points)

    if numeric.verdict is True:
        return Equivalence(None, "undecided", numeric.points)
    # Too few evaluable points and no proof: treat as different.
    return Equivalence(False, "unproven", numeric.points)


def constant_ratio(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol],
                   constraint: sp.Expr | None = None) -> sp.Rational | None:
    """If ``a / b`` is the same rational number at every sample point, return it.

    Found numerically (``simplify(a / b)`` misses ratios like
    ``(tan^2 u + 1) / sec^2 u``), then confirmed: ``a - c b`` must not be
    separable from zero by the numeric screen. Good enough for tagging, which
    needs a likely explanation rather than a proof.
    """
    ratios: list[mpmath.mpc] = []
    with mpmath.workdps(_DIGITS):
        for point in _sample_points(symbols, constraint):
            va, vb = _evaluate(a, point), _evaluate(b, point)
            if va is None or vb is None or abs(vb) < mpmath.mpf("1e-20"):
                continue
            ratios.append(va / vb)
        if len(ratios) < MIN_NUMERIC_POINTS:
            return None
        first = ratios[0]
        if abs(first.imag) > _REL_TOL or any(abs(r - first) > _REL_TOL * max(1, abs(first)) for r in ratios):
            return None
        c = sp.nsimplify(sp.Float(str(first.real), 25), rational=True, tolerance=1e-15)
    if not c.is_Rational or c == 0 or abs(c.q) > 1000:
        return None
    verdict, _ = numeric_screen(a, c * b, symbols, constraint)
    return c if verdict is not False else None
