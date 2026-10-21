"""Parameter sampling helpers. All take an explicit ``Random`` so seeds reproduce."""

from __future__ import annotations

from random import Random
from typing import Sequence, TypeVar

import sympy as sp

T = TypeVar("T")


def nonzero_int(rng: Random, lo: int, hi: int, *, exclude: Sequence[int] = ()) -> int:
    """Uniform integer in ``[lo, hi]`` other than 0 and anything in ``exclude``."""
    choices = [n for n in range(lo, hi + 1) if n != 0 and n not in exclude]
    if not choices:
        raise ValueError(f"no integers left in [{lo}, {hi}] after exclusions")
    return rng.choice(choices)


def pick(rng: Random, options: Sequence[T]) -> T:
    return options[rng.randrange(len(options))]


def poly_coeffs(rng: Random, degree: int, *, lo: int = -6, hi: int = 6, monic: bool = False,
                min_terms: int = 2) -> list[int]:
    """Integer coefficients ``[a_degree, ..., a_0]`` for a polynomial of exactly ``degree``.

    The leading coefficient is nonzero (and 1 if ``monic``); at least
    ``min_terms`` coefficients are nonzero so the polynomial is not a bare
    monomial unless asked for.
    """
    while True:
        lead = 1 if monic else nonzero_int(rng, lo, hi)
        rest = [rng.randint(lo, hi) for _ in range(degree)]
        coeffs = [lead, *rest]
        if sum(1 for c in coeffs if c != 0) >= min(min_terms, degree + 1):
            return coeffs


def poly_from(coeffs: Sequence[int], var: sp.Symbol) -> sp.Expr:
    degree = len(coeffs) - 1
    return sp.Add(*[sp.Integer(c) * var ** (degree - i) for i, c in enumerate(coeffs)])


def rational(p: int, q: int = 1) -> sp.Rational:
    return sp.Rational(p, q)
