"""Decide whether two expressions are mathematically the same.

Order of work:

1. Identical after SymPy's automatic evaluation: equal.
2. Numeric screen at fixed sample points, evaluated to 30 digits. A point where
   both sides are finite and clearly differ proves the expressions are *not*
   equivalent, so most wrong answers stop here without any simplification.
3. Symbolic proof: ``simplify(a - b) == 0`` first, then a short chain of other
   rewrites for identities ``simplify`` misses (``sec^2 u = tan^2 u + 1`` is the
   usual one), then ``Expr.equals``.
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


def numeric_screen(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol],
                   constraint: sp.Expr | None = None) -> tuple[bool | None, int]:
    """``(False, n)`` on a counterexample, ``(True, n)`` if all ``n`` usable points agree,
    ``(None, n)`` if fewer than :data:`MIN_NUMERIC_POINTS` points could be evaluated."""
    agree = 0
    with mpmath.workdps(_DIGITS):
        for point in _sample_points(symbols, constraint):
            va, vb = _evaluate(a, point), _evaluate(b, point)
            if va is None or vb is None:
                continue
            scale = max(mpmath.mpf(1), abs(va), abs(vb))
            if abs(va - vb) > _REL_TOL * scale:
                return False, agree
            agree += 1
    if agree < MIN_NUMERIC_POINTS:
        return None, agree
    return True, agree


def _is_zero(expr: sp.Expr) -> bool:
    return expr == 0 or (expr.is_number and expr.is_zero is True)


def _rewrite_cos(d: sp.Expr) -> sp.Expr:
    return sp.simplify(d.rewrite(sp.cos))


def _rewrite_exp(d: sp.Expr) -> sp.Expr:
    return sp.simplify(d.rewrite(sp.exp))


def _cancel(d: sp.Expr) -> sp.Expr:
    return sp.cancel(sp.together(d))


_SYMBOLIC_CHAIN: tuple[tuple[str, Callable[[sp.Expr], sp.Expr]], ...] = (
    ("cancel", _cancel),
    ("simplify", sp.simplify),
    ("fu", sp.fu),
    ("rewrite_cos", _rewrite_cos),
    ("rewrite_exp", _rewrite_exp),
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


def equivalent(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol], *,
               constraint: sp.Expr | None = None) -> Equivalence:
    """Compare ``a`` and ``b`` as functions of ``symbols`` (optionally on a curve)."""
    a, b = sp.sympify(a), sp.sympify(b)
    d = a - b
    if _is_zero(d):
        return Equivalence(True, "identical")

    numeric, points = numeric_screen(a, b, symbols, constraint)
    if numeric is False:
        return Equivalence(False, "numeric_counterexample", points)

    method = symbolic_zero(d)
    if method is not None:
        return Equivalence(True, method, points)

    if constraint is not None and _reduces_on_curve(d, constraint, symbols):
        return Equivalence(True, "constraint_reduction", points)

    if numeric is True:
        return Equivalence(None, "undecided", points)
    # Too few evaluable points and no proof: treat as different.
    return Equivalence(False, "unproven", points)


def constant_ratio(a: sp.Expr, b: sp.Expr, symbols: Sequence[sp.Symbol]) -> sp.Expr | None:
    """If ``a / b`` is a nonzero constant, return it; otherwise ``None``."""
    if _is_zero(b):
        return None
    ratio = sp.simplify(a / b)
    if ratio.free_symbols & set(symbols) or not ratio.is_number or _is_zero(ratio):
        return None
    return ratio
