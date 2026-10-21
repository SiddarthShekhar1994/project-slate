"""Implicit differentiation: find dy/dx on a curve F(x, y) = 0 without solving for y.

Every curve here is a polynomial equation in ``x`` and ``y``, so each side is a
sum of monomials ``c x^a y^b``. The key is derived the way a student works:

1. differentiate every term with respect to ``x``, treating ``y`` as a function
   of ``x``. A power of ``x`` uses the power rule, a power of ``y`` picks up a
   factor of dy/dx (chain rule), and a mixed term ``x^a y^b`` needs the product
   rule, which gives one term without dy/dx and one with it;
2. collect the dy/dx terms on the left and everything else on the right;
3. divide by the coefficient of dy/dx and cancel common factors.

Each monomial is differentiated with exponent arithmetic (see
:func:`_term_derivative`), never with ``sp.diff`` on the curve. The verifier
checks the key against ``-F_x / F_y`` independently and compares on the curve.

Point families (``at = {x: x0, y: y0}``) pick an integer point first and set the
constant so the point lies on the curve; the key is then the slope there.

Parts available to notes and hints:

``coef``      the coefficient of dy/dx after collecting
``other``     the right side after collecting, so dy/dx = other / coef
``formula``   dy/dx in terms of x and y, tidied (the key of a symbolic problem)
``y_term``    the first term with only y in it (``y^2`` when there is none)
``mixed``     the first product of powers of x and y (``x y`` when there is none)
``const``     the constant term of the equation (0 when there is none)

Snippets: ``y_term_prime`` and ``mixed_prime`` (those terms differentiated, with
dy/dx written out) and ``point`` (the point as ``(2, 4)``, or ``(x_0, y_0)``
for symbolic problems). The fallbacks exist so every note renders on every
problem; a note is only shown when its pattern applies.
"""

from __future__ import annotations

from collections.abc import Callable
from math import gcd
from random import Random

import sympy as sp

from ....core.sampling import nonzero_int, pick
from ....core.text import highlight, tex
from ....core.types import (
    Built,
    Family,
    FormulaEntry,
    HintLadder,
    MistakePattern,
    Params,
    SkillSpec,
    Step,
    WordContext,
)

x, y = sp.symbols("x y")

DYDX = r"\frac{dy}{dx}"

Mono = tuple[int, int, int]
"""``(c, a, b)`` for one term ``c * x**a * y**b``."""

Terms = list[list[int]]
"""JSON form of one side of an equation: ``[[c, a, b], ...]``."""


# --- the rule, one monomial at a time --------------------------------------------


def _term_derivative(c: int, a: int, b: int, bug: str | None = None) -> tuple[sp.Expr, sp.Expr]:
    """d/dx of ``c x^a y^b`` as ``(part without dy/dx, coefficient of dy/dx)``.

    ``bug`` replays one wrong turn so mistake patterns share this code:

    ``missing_dydx``            a power of y differentiated as n y^(n-1), no dy/dx
    ``y_constant``              a mixed term differentiated as if y were a constant
    ``x_constant``              a mixed term differentiated as if x were a constant
    ``product_of_derivatives``  a mixed term's two factor derivatives multiplied
    ``constant_kept``           a constant term left in place instead of becoming 0
    """
    dx = sp.Integer(c * a) * x ** (a - 1) * y**b if a else sp.Integer(0)  # power rule in x
    dy = sp.Integer(c * b) * x**a * y ** (b - 1) if b else sp.Integer(0)  # power rule in y, times dy/dx
    pure_y, mixed = a == 0 and b > 0, a > 0 and b > 0
    if bug == "missing_dydx" and pure_y:
        return dy, sp.Integer(0)
    if bug == "y_constant" and mixed:
        return dx, sp.Integer(0)
    if bug == "x_constant" and mixed:
        return sp.Integer(0), dy
    if bug == "product_of_derivatives" and mixed:
        return sp.Integer(0), sp.Integer(c * a * b) * x ** (a - 1) * y ** (b - 1)
    if bug == "constant_kept" and a == 0 and b == 0:
        return sp.Integer(c), sp.Integer(0)
    return dx, dy


def _monomials(side: sp.Expr) -> list[tuple[sp.Expr, Mono]]:
    """The terms of one side in the order SymPy prints them, with their ``(c, a, b)``."""
    out = []
    for term in side.as_ordered_terms():
        if term == 0:
            continue
        ((a, b), c), = sp.Poly(term, x, y).terms()
        out.append((term, (int(c), int(a), int(b))))
    return out


def _collect(left: list[tuple[sp.Expr, Mono]], right: list[tuple[sp.Expr, Mono]],
             bug: str | None = None) -> tuple[sp.Expr, sp.Expr]:
    """Differentiate both sides and move dy/dx terms left: ``(coef, other)`` with coef * dy/dx = other."""
    lx = ly = rx = ry = sp.Integer(0)
    for _, (c, a, b) in left:
        dx, dy = _term_derivative(c, a, b, bug)
        lx, ly = lx + dx, ly + dy
    for _, (c, a, b) in right:
        dx, dy = _term_derivative(c, a, b, bug)
        rx, ry = rx + dx, ry + dy
    return sp.expand(ly - ry), sp.expand(rx - lx)


def _leads_negative(expr: sp.Expr) -> bool:
    return expr.as_ordered_terms()[0].could_extract_minus_sign()


def _tidy(other: sp.Expr, coef: sp.Expr) -> tuple[sp.Expr, sp.Expr]:
    """Cancel common factors of ``other / coef`` and pick signs that read well.

    Prefers a denominator whose first printed term is positive, then the same
    for the numerator: (x^2 - 2y)/(2x - y^2) rather than (-x^2 + 2y)/(-2x + y^2).
    """
    g = sp.gcd(other, coef)
    if g not in (0, 1):
        other, coef = sp.cancel(other / g), sp.cancel(coef / g)

    def score(num: sp.Expr, den: sp.Expr) -> int:
        return 2 * _leads_negative(den) + _leads_negative(num)

    if score(-other, -coef) < score(other, coef):
        other, coef = sp.expand(-other), sp.expand(-coef)
    return other, coef


def _fraction(num: sp.Expr, den: sp.Expr) -> sp.Expr:
    """``num / den`` with an all-negative numerator shown as a leading minus."""
    if isinstance(num, sp.Add) and all(t.could_extract_minus_sign() for t in num.args):
        return sp.Mul(-1, -num, sp.Pow(den, -1))
    return num / den


def _buggy_formula(left, right, bug: str) -> sp.Expr | None:
    """dy/dx as a student making ``bug`` would get it, or None if the bug changes nothing."""
    good = _collect(left, right)
    coef, other = _collect(left, right, bug)
    if (coef, other) == good or coef == 0:
        return None
    return other / coef


# --- LaTeX helpers -------------------------------------------------------------------


def _dydx_tex(coef: sp.Expr) -> str:
    """LaTeX for ``coef * dy/dx`` with the coefficient written first."""
    if coef == 1:
        return DYDX
    if coef == -1:
        return f"-{DYDX}"
    if isinstance(coef, sp.Add):
        return rf"\left({tex(coef)}\right) {DYDX}"
    return f"{tex(coef)} {DYDX}"


Piece = tuple[bool, str, "str | None"]
"""``(negative, LaTeX without the sign, highlight colour)`` for one printed term."""


def _join(pieces: list[Piece]) -> str:
    if not pieces:
        return "0"
    out = []
    for i, (neg, body, color) in enumerate(pieces):
        body = highlight(body, color) if color else body
        if i == 0:
            out.append(f"- {body}" if neg else body)
        else:
            out.append(f" - {body}" if neg else f" + {body}")
    return "".join(out)


def _kind(mono: Mono) -> str:
    _, a, b = mono
    if b == 0:
        return "const" if a == 0 else "x"
    return "y" if a == 0 else "mixed"


COLOR = {"y": "yellow", "mixed": "mint"}


def _identify_pieces(side: list[tuple[sp.Expr, Mono]]) -> list[Piece]:
    return [(mono[0] < 0, tex(-term if mono[0] < 0 else term), COLOR.get(_kind(mono))) for term, mono in side]


def _derivative_pieces(side: list[tuple[sp.Expr, Mono]]) -> list[Piece]:
    """Each term differentiated, in print order. Constants differentiate to 0 and drop out."""
    pieces: list[Piece] = []
    for _, (c, a, b) in side:
        kind = _kind((c, a, b))
        if kind == "const":
            continue
        dx, dy = _term_derivative(abs(c), a, b)
        if kind == "x":
            body = tex(dx)
        elif kind == "y":
            body = _dydx_tex(dy)
        else:
            body = rf"\left({tex(dx)} + {_dydx_tex(dy)}\right)"
        pieces.append((c < 0, body, COLOR.get(kind)))
    return pieces


def _signed_derivative_tex(mono: Mono) -> str:
    """One term's derivative with its own sign, for notes and hints."""
    c, a, b = mono
    dx, dy = _term_derivative(c, a, b)
    if a == 0:
        return _dydx_tex(dy)
    if c > 0:
        return f"{tex(dx)} + {_dydx_tex(dy)}"
    return f"{tex(dx)} - {_dydx_tex(-dy)}"


def _point_tex(point: tuple[int, int]) -> str:
    return f"({point[0]}, {point[1]})"


# --- building a problem ---------------------------------------------------------------


def _side(terms: Terms) -> sp.Expr:
    return sp.Add(*[sp.Integer(c) * x**a * y**b for c, a, b in terms])


def _value(terms: Terms, point: tuple[int, int]) -> int:
    x0, y0 = point
    return sum(c * x0**a * y0**b for c, a, b in terms)


MAX_POINT_KEY = 30
"""Largest numerator or denominator allowed in a point answer."""


def build_curve(*, family: str, difficulty: int, lhs: Terms, rhs: Terms, params: Params,
                point: tuple[int, int] | None = None, word: WordContext | None = None) -> Built:
    """Build the problem ``lhs = rhs`` and walk implicit differentiation to the key.

    ``lhs`` and ``rhs`` list monomials as ``[c, a, b]``. With ``point`` the key
    is the slope there; the point must lie on the curve.
    """
    left_expr, right_expr = _side(lhs), _side(rhs)
    equation = sp.Eq(left_expr, right_expr)
    if equation in (sp.true, sp.false):
        raise ValueError("equation evaluated to a boolean; resample")
    expr = left_expr - right_expr
    left, right = _monomials(left_expr), _monomials(right_expr)
    monos = [m for _, m in left + right]
    if not any(_kind(m) in ("y", "mixed") for m in monos):
        raise ValueError("curve does not involve y")

    coef, other = _collect(left, right)
    if coef == 0 or other == 0:
        raise ValueError("dy/dx is undefined or identically zero; resample")
    num, den = _tidy(other, coef)
    formula = _fraction(num, den)

    first = {kind: next(((t, m) for t, m in left + right if _kind(m) == kind), None) for kind in ("y", "mixed")}
    y_term, y_mono = first["y"] or (y**2, (1, 0, 2))
    mixed, mixed_mono = first["mixed"] or (x * y, (1, 1, 1))
    const = next((t for t, m in left + right if _kind(m) == "const"), sp.Integer(0))

    parts = {
        "coef": coef,
        "other": other,
        "formula": formula,
        "y_term": y_term,
        "mixed": mixed,
        "const": const,
    }
    snippets = {
        "y_term_prime": _signed_derivative_tex(y_mono),
        "mixed_prime": _signed_derivative_tex(mixed_mono),
        "point": _point_tex(point) if point else "(x_0, y_0)",
    }
    coef_tex = tex(coef)
    if coef in (1, -1):
        collected = _dydx_tex(coef)
    else:
        grouped = rf"\left({coef_tex}\right)" if isinstance(coef, sp.Add) else coef_tex
        collected = f"{highlight(grouped, 'yellow')} {DYDX}"

    raw = rf"\frac{{{tex(other)}}}{{{coef_tex}}}" if coef != 1 else tex(other)
    shown = (rf"\frac{{{highlight(tex(other), 'mint')}}}{{{highlight(coef_tex, 'yellow')}}}"
             if coef != 1 else highlight(tex(other), "mint"))
    solve_latex = f"{DYDX} = {shown}"
    if raw != tex(formula):
        solve_latex += f" = {tex(formula)}"

    steps = [
        Step(
            id="identify",
            title="Spot the terms that contain $y$",
            latex=f"{_join(_identify_pieces(left))} = {_join(_identify_pieces(right))}",
        ),
        Step(
            id="differentiate",
            title="Differentiate both sides with respect to $x$",
            latex=f"{_join(_derivative_pieces(left))} = {_join(_derivative_pieces(right))}",
        ),
        Step(
            id="collect",
            title=f"Collect the ${DYDX}$ terms on one side",
            latex=f"{collected} = {highlight(tex(other), 'mint')}",
        ),
        Step(
            id="solve",
            title=f"Divide to isolate ${DYDX}$",
            latex=solve_latex,
            expr=formula,
        ),
    ]

    key = formula
    at = None
    if point is not None:
        at = {x: sp.Integer(point[0]), y: sp.Integer(point[1])}
        if expr.subs(at) != 0:
            raise ValueError("the point is not on the curve")
        num0, den0 = num.subs(at), den.subs(at)
        if den0 == 0:
            raise ValueError("vertical tangent at the point; resample")
        key = num0 / den0
        if max(abs(key.p), abs(key.q)) > MAX_POINT_KEY:
            raise ValueError("slope is an awkward fraction; resample")
        # A problem only tests the rule if forgetting dy/dx changes the answer.
        wrong = _buggy_formula(left, right, "missing_dydx")
        if wrong is not None and wrong.subs(at) == key:
            raise ValueError("signature mistake gives the right slope here; resample")
        # Show the substituted fraction only when it still needs reducing.
        substituted = rf"\frac{{{tex(num0)}}}{{{tex(den0)}}} = " if (num0, den0) != (key.p, key.q) else ""
        steps.append(Step(
            id="evaluate",
            title=f"Substitute the point ${snippets['point']}$",
            latex=rf"\left.{DYDX}\right|_{{{snippets['point']}}} = {substituted}{tex(key)}",
            expr=key,
        ))

    if word is not None:
        prompt = f"{word.text} {word.question}"
    elif point is not None:
        prompt = rf"Find ${DYDX}$ at the point ${snippets['point']}$ on the curve ${tex(equation)}$."
    else:
        prompt = rf"Find ${DYDX}$ if ${tex(equation)}$. Give your answer in terms of $x$ and $y$."

    return Built(
        family=family,
        difficulty=difficulty,
        task="implicit_differentiate",
        var=x,
        expr=expr,
        key=key,
        steps=tuple(steps),
        parts=parts,
        params=params,
        prompt=prompt,
        equation=equation,
        dependent=y,
        at=at,
        word=word,
        snippets=snippets,
    )


def _family(id: str, difficulty: int, description: str, sample, build, word: bool = False) -> Family:
    return Family(id=id, difficulty=difficulty, description=description, sample=sample, build=build, word=word)


def _first_that_builds(rng: Random, draw: Callable[[Random], Params], build: Callable[[Params], Built],
                       fallback: Params) -> Params:
    """Draw until ``build`` accepts the params, or give up and use ``fallback``.

    Point families need this: the point, the slope and the signature check all
    have to work out together, which is easier to test than to sample directly.
    """
    for _ in range(200):
        params = draw(rng)
        try:
            build(params)
        except ValueError:
            continue
        return params
    return fallback


def _coprime_pair(rng: Random, lo: int, hi: int, *, distinct: bool) -> tuple[int, int]:
    while True:
        a, b = rng.randint(lo, hi), rng.randint(lo, hi)
        if gcd(a, b) == 1 and (a != b or not distinct):
            return a, b


# d1 ------------------------------------------------------------------------------------


def _sample_circle(rng: Random) -> Params:
    # A centred circle, or one shifted along the x-axis by a linear term on either side.
    d = pick(rng, [0, 0, 0, -6, -4, -2, 2, 4, 6])
    r = rng.randint(2, 9) if d == 0 else rng.randint(4, 8)
    return {"r": r, "d": d, "side": pick(rng, ["lhs", "rhs"])}


def _build_circle(p: Params) -> Built:
    # (x + d/2)^2 + y^2 = r^2, multiplied out.
    r, d = p["r"], p["d"]
    c = r * r - (d // 2) ** 2
    if d and p["side"] == "rhs":
        lhs, rhs = [[1, 2, 0], [1, 0, 2]], [[-d, 1, 0], [c, 0, 0]]
    else:
        lhs, rhs = [[1, 2, 0], [d, 1, 0], [1, 0, 2]], [[c, 0, 0]]
    lhs = [t for t in lhs if t[0]]
    return build_curve(family="circle", difficulty=1, lhs=lhs, rhs=rhs, params=p)


def _sample_ellipse(rng: Random) -> Params:
    a, b = _coprime_pair(rng, 1, 9, distinct=True)
    return {"a": a, "b": b, "p": rng.randint(1, 3), "q": rng.randint(1, 3)}


def _build_ellipse(p: Params) -> Built:
    # The constant is a p^2 + b q^2, so (p, q) is on the ellipse and it is never tiny.
    a, b = p["a"], p["b"]
    c = a * p["p"] ** 2 + b * p["q"] ** 2
    return build_curve(family="ellipse", difficulty=1, lhs=[[a, 2, 0], [b, 0, 2]], rhs=[[c, 0, 0]], params=p)


def _sample_hyperbola(rng: Random) -> Params:
    a, b = _coprime_pair(rng, 1, 6, distinct=False)
    opens = pick(rng, ["x", "y"])
    # Opening along x, a x^2 - b y^2 = c has no points for |x| < sqrt(c/a); keep that gap narrow.
    c = rng.randint(1, 3 * a) if opens == "x" else rng.randint(1, 20)
    return {"a": a, "b": b, "c": c, "opens": opens}


def _build_hyperbola(p: Params) -> Built:
    a, b, c = p["a"], p["b"], p["c"]
    lhs = [[a, 2, 0], [-b, 0, 2]] if p["opens"] == "x" else [[b, 0, 2], [-a, 2, 0]]
    return build_curve(family="hyperbola", difficulty=1, lhs=lhs, rhs=[[c, 0, 0]], params=p)


def _sample_power_curve(rng: Random) -> Params:
    n = pick(rng, [2, 2, 3])
    if n == 2:
        # y^2 = x^3 + p x + q, an elliptic curve.
        poly = [[1, 3, 0], [rng.randint(-4, 4), 1, 0], [rng.randint(-6, 6), 0, 0]]
    else:
        # y^3 = a x^2 + p x + q.
        poly = [[rng.randint(1, 4), 2, 0], [rng.randint(-5, 5), 1, 0], [nonzero_int(rng, -8, 8), 0, 0]]
    return {"n": n, "poly": [t for t in poly if t[0]]}


def _build_power_curve(p: Params) -> Built:
    return build_curve(family="power_curve", difficulty=1, lhs=[[1, 0, p["n"]]], rhs=p["poly"], params=p)


# d2 ------------------------------------------------------------------------------------


def _quadratic_terms(a: int, b: int, d: int) -> Terms:
    return [[a, 2, 0], [b, 1, 1], [d, 0, 2]]


def _quadratic_ok(a: int, b: int, d: int) -> bool:
    # b^2 = 4ad makes the left side a perfect square: two parallel lines, not a curve.
    return b * b != 4 * a * d


def _sample_quadratic_mixed(rng: Random) -> Params:
    while True:
        a, d = rng.randint(1, 3), rng.randint(1, 3)
        b = nonzero_int(rng, -4, 4)
        px, py = rng.randint(-3, 3), rng.randint(-3, 3)
        c = _value(_quadratic_terms(a, b, d), (px, py))
        if _quadratic_ok(a, b, d) and 1 <= c <= 40:
            return {"a": a, "b": b, "d": d, "c": c}


def _build_quadratic_mixed(p: Params) -> Built:
    if not _quadratic_ok(p["a"], p["b"], p["d"]):
        raise ValueError("degenerate conic")
    return build_curve(family="quadratic_mixed", difficulty=2, lhs=_quadratic_terms(p["a"], p["b"], p["d"]),
                       rhs=[[p["c"], 0, 0]], params=p)


def _sample_product_term(rng: Random) -> Params:
    a, b = rng.randint(1, 3), rng.randint(1, 3)
    layout = pick(rng, ["same", "same", "split"])
    if layout == "same":
        # a xy + b y^2 + e x = c with b, c > 0: real for every x when e = 0, and away from a short
        # interval of x otherwise.
        return {"a": a, "b": b, "e": pick(rng, [0, 0, -3, -2, -1, 1, 2, 3]), "c": rng.randint(1, 12),
                "layout": layout}
    # a xy = b y^2 - c: y terms on both sides, real for every x since c > 0.
    return {"a": a, "b": b, "e": 0, "c": rng.randint(1, 12), "layout": layout}


def _build_product_term(p: Params) -> Built:
    a, b, c, e = p["a"], p["b"], p["c"], p["e"]
    if p["layout"] == "split":
        lhs, rhs = [[a, 1, 1]], [[b, 0, 2], [-c, 0, 0]]
    else:
        lhs, rhs = [t for t in ([a, 1, 1], [b, 0, 2], [e, 1, 0]) if t[0]], [[c, 0, 0]]
    return build_curve(family="product_term", difficulty=2, lhs=lhs, rhs=rhs, params=p)


# d3 ------------------------------------------------------------------------------------


def _sample_folium(rng: Random) -> Params:
    return {"k": rng.randint(2, 9), "c": pick(rng, [0, 0, 0, *range(-9, 10)])}


def _build_folium(p: Params) -> Built:
    # x^3 + y^3 = k x y (+ c): the folium of Descartes and its relatives.
    rhs = [[p["k"], 1, 1]] + ([[p["c"], 0, 0]] if p["c"] else [])
    return build_curve(family="folium", difficulty=3, lhs=[[1, 3, 0], [1, 0, 3]], rhs=rhs, params=p)


MIXED_CUBIC_SHAPES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "x2y_y3": ((2, 1), (0, 3)),  # a x^2 y + b y^3
    "xy2_y3": ((1, 2), (0, 3)),  # a x y^2 + b y^3
    "xy2_x3": ((1, 2), (3, 0)),  # a x y^2 + b x^3
    "x2y_y2": ((2, 1), (0, 2)),  # a x^2 y + b y^2
}


def _sample_mixed_cubic(rng: Random) -> Params:
    return {"shape": pick(rng, sorted(MIXED_CUBIC_SHAPES)), "a": rng.randint(1, 3),
            "b": nonzero_int(rng, -3, 3), "c": nonzero_int(rng, -12, 12)}


def _build_mixed_cubic(p: Params) -> Built:
    (ma, mb), (pa, pb) = MIXED_CUBIC_SHAPES[p["shape"]]
    lhs = [[p["a"], ma, mb], [p["b"], pa, pb]]
    return build_curve(family="mixed_cubic", difficulty=3, lhs=lhs, rhs=[[p["c"], 0, 0]], params=p)


# d4 ------------------------------------------------------------------------------------


def _sample_two_mixed(rng: Random) -> Params:
    # a x^2 y + b x y^2 (+ e y^k) = c: the product rule twice, plus a power of y.
    return {"a": rng.randint(1, 3), "b": nonzero_int(rng, -3, 3), "e": pick(rng, [0, -3, -2, -1, 1, 2, 3]),
            "k": pick(rng, [1, 2]), "c": nonzero_int(rng, -12, 12)}


def _build_two_mixed(p: Params) -> Built:
    lhs = [[p["a"], 2, 1], [p["b"], 1, 2]] + ([[p["e"], 0, p["k"]]] if p["e"] else [])
    return build_curve(family="two_mixed", difficulty=4, lhs=lhs, rhs=[[p["c"], 0, 0]], params=p)


HIGHER_MIXED_SHAPES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "x2y2_y3": ((2, 2), (0, 3)),  # a x^2 y^2 + b y^3
    "x3y_y2": ((3, 1), (0, 2)),   # a x^3 y + b y^2
    "xy3_x2": ((1, 3), (2, 0)),   # a x y^3 + b x^2
    "x2y2_y": ((2, 2), (0, 1)),   # a x^2 y^2 + b y
}


def _sample_higher_mixed(rng: Random) -> Params:
    shape = pick(rng, sorted(HIGHER_MIXED_SHAPES))
    if shape == "x2y2_y":
        # a x^2 y^2 + b y = c is quadratic in y with discriminant b^2 + 4 a c x^2: keep c > 0 so it is
        # real for every x.
        return {"shape": shape, "a": rng.randint(1, 2), "b": nonzero_int(rng, -3, 3), "c": rng.randint(1, 9),
                "e": 0}
    rhs = pick(rng, ["const", "const", "linear"])
    return {"shape": shape, "a": rng.randint(1, 2), "b": nonzero_int(rng, -3, 3), "c": nonzero_int(rng, -9, 9),
            "e": nonzero_int(rng, -4, 4) if rhs == "linear" else 0}


def _build_higher_mixed(p: Params) -> Built:
    (ma, mb), (pa, pb) = HIGHER_MIXED_SHAPES[p["shape"]]
    lhs = [[p["a"], ma, mb], [p["b"], pa, pb]]
    rhs = ([[p["e"], 1, 0]] if p["e"] else []) + [[p["c"], 0, 0]]
    return build_curve(family="higher_mixed", difficulty=4, lhs=lhs, rhs=rhs, params=p)


POINT_SHAPES: dict[str, tuple[tuple[int, int], ...]] = {
    "x2y_y3": ((2, 1), (0, 3)),
    "x2y_xy2": ((2, 1), (1, 2)),
    "xy2_x3": ((1, 2), (3, 0)),
    "x3_xy_y2": ((3, 0), (1, 1), (0, 2)),
    "x2_xy2_y3": ((2, 0), (1, 2), (0, 3)),
}


def _point_lhs(p: Params) -> Terms:
    return [[c, a, b] for c, (a, b) in zip(p["coeffs"], POINT_SHAPES[p["shape"]])]


def _draw_slope_at_point(rng: Random) -> Params:
    shape = pick(rng, sorted(POINT_SHAPES))
    coeffs = [1] + [nonzero_int(rng, -3, 3) for _ in POINT_SHAPES[shape][1:]]
    return {"shape": shape, "coeffs": coeffs, "point": [nonzero_int(rng, -3, 3), nonzero_int(rng, -3, 3)]}


def _build_slope_at_point(p: Params) -> Built:
    lhs = _point_lhs(p)
    point = (p["point"][0], p["point"][1])
    c = _value(lhs, point)
    # c = 0 often makes the curve split into simpler pieces (y (x^2 + y^2) = 0).
    if c == 0 or abs(c) > 60:
        raise ValueError("constant is zero or too large; resample")
    return build_curve(family="slope_at_point", difficulty=4, lhs=lhs, rhs=[[c, 0, 0]], params=p, point=point)


def _sample_slope_at_point(rng: Random) -> Params:
    return _first_that_builds(rng, _draw_slope_at_point, _build_slope_at_point,
                              {"shape": "x2y_y3", "coeffs": [1, 1], "point": [1, 2]})


# word problems ---------------------------------------------------------------------------

_MIRROR = (
    ("The rim of an oval mirror follows the ellipse ${eq}$, with $x$ and $y$ in decimeters "
     "measured from the center of the mirror."),
    "What is the slope of the rim at the point ${pt}$?",
)
_TRACK = (
    ("A cycling track is laid out along the curve ${eq}$, where $x$ and $y$ are in hundreds of meters. "
     "A cyclist passes the point ${pt}$."),
    "What is the slope of the track at that point?",
)
_ISOQUANT = (
    ("A workshop's weekly output is $Q = {q}$ units, where $x$ is the number of machines and $y$ the number "
     "of workers. To hold output at {q0} units, $x$ and $y$ must satisfy ${eq}$."),
    ("The workshop runs {x0} machines with {y0} workers. At what rate must the number of workers change per "
     "additional machine? Find $\\frac{{dy}}{{dx}}$ at ${pt}$."),
)
_PENDANT = (
    "A jeweller cuts a pendant whose outline follows the curve ${eq}$, with $x$ and $y$ in centimeters.",
    "What is the slope of the outline at the point ${pt}$?",
)


def _word(template: tuple[str, str], lhs: Terms, rhs: Terms, point: tuple[int, int], unit: str = "",
          **extra: object) -> WordContext:
    text, question = template
    fields = {"eq": tex(sp.Eq(_side(lhs), _side(rhs))), "pt": _point_tex(point), "x0": point[0], "y0": point[1],
              **extra}
    return WordContext(text=text.format(**fields), question=question.format(**fields), unit=unit)


def _draw_word_mirror(rng: Random) -> Params:
    a, b = _coprime_pair(rng, 1, 9, distinct=True)
    return {"a": a, "b": b, "point": [nonzero_int(rng, -3, 3), nonzero_int(rng, -3, 3)]}


def _build_word_mirror(p: Params) -> Built:
    point = (p["point"][0], p["point"][1])
    lhs = [[p["a"], 2, 0], [p["b"], 0, 2]]
    rhs = [[_value(lhs, point), 0, 0]]
    return build_curve(family="word_mirror", difficulty=1, lhs=lhs, rhs=rhs, params=p, point=point,
                       word=_word(_MIRROR, lhs, rhs, point))


def _sample_word_mirror(rng: Random) -> Params:
    return _first_that_builds(rng, _draw_word_mirror, _build_word_mirror, {"a": 4, "b": 9, "point": [3, 2]})


def _draw_word_track(rng: Random) -> Params:
    return {"a": rng.randint(1, 3), "b": nonzero_int(rng, -3, 3), "d": rng.randint(1, 3),
            "point": [nonzero_int(rng, -3, 3), nonzero_int(rng, -3, 3)]}


def _build_word_track(p: Params) -> Built:
    if not _quadratic_ok(p["a"], p["b"], p["d"]):
        raise ValueError("degenerate conic")
    point = (p["point"][0], p["point"][1])
    lhs = _quadratic_terms(p["a"], p["b"], p["d"])
    c = _value(lhs, point)
    if c <= 0:
        raise ValueError("track constant should be positive; resample")
    rhs = [[c, 0, 0]]
    return build_curve(family="word_track", difficulty=2, lhs=lhs, rhs=rhs, params=p, point=point,
                       word=_word(_TRACK, lhs, rhs, point))


def _sample_word_track(rng: Random) -> Params:
    return _first_that_builds(rng, _draw_word_track, _build_word_track,
                              {"a": 1, "b": 1, "d": 1, "point": [1, 2]})


ISOQUANT_EXPONENTS = ((1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2))


def _draw_word_isoquant(rng: Random) -> Params:
    a, b = pick(rng, ISOQUANT_EXPONENTS)
    return {"a": a, "b": b, "point": [rng.randint(2, 6), rng.randint(2, 6)]}


def _build_word_isoquant(p: Params) -> Built:
    a, b = p["a"], p["b"]
    point = (p["point"][0], p["point"][1])
    lhs = [[1, a, b]]
    q0 = _value(lhs, point)
    if q0 > 2000:
        raise ValueError("output level is too large to read comfortably; resample")
    rhs = [[q0, 0, 0]]
    word = _word(_ISOQUANT, lhs, rhs, point, unit="workers per machine", q=tex(_side(lhs)), q0=q0)
    return build_curve(family="word_isoquant", difficulty=3, lhs=lhs, rhs=rhs, params=p, point=point, word=word)


def _sample_word_isoquant(rng: Random) -> Params:
    return _first_that_builds(rng, _draw_word_isoquant, _build_word_isoquant, {"a": 2, "b": 1, "point": [4, 3]})


def _draw_word_pendant(rng: Random) -> Params:
    return {"k": rng.randint(2, 9), "point": [rng.randint(1, 4), rng.randint(1, 4)]}


def _build_word_pendant(p: Params) -> Built:
    # x^3 + y^3 = k x y + c through the chosen point; c = 0 is the folium itself.
    point = (p["point"][0], p["point"][1])
    lhs = [[1, 3, 0], [1, 0, 3]]
    c = _value(lhs, point) - p["k"] * point[0] * point[1]
    if abs(c) > 20:
        raise ValueError("constant too large; resample")
    rhs = [[p["k"], 1, 1]] + ([[c, 0, 0]] if c else [])
    return build_curve(family="word_pendant", difficulty=4, lhs=lhs, rhs=rhs, params=p, point=point,
                       word=_word(_PENDANT, lhs, rhs, point))


def _sample_word_pendant(rng: Random) -> Params:
    return _first_that_builds(rng, _draw_word_pendant, _build_word_pendant, {"k": 9, "point": [2, 4]})


FAMILIES = (
    _family("circle", 1, "Circle x^2 + y^2 = r^2, possibly shifted along the x-axis", _sample_circle, _build_circle),
    _family("ellipse", 1, "Ellipse a x^2 + b y^2 = c", _sample_ellipse, _build_ellipse),
    _family("hyperbola", 1, "Hyperbola a x^2 - b y^2 = c or b y^2 - a x^2 = c", _sample_hyperbola,
            _build_hyperbola),
    _family("power_curve", 1, "y^2 or y^3 equal to a polynomial in x", _sample_power_curve, _build_power_curve),
    _family("word_mirror", 1, "Slope of an elliptical mirror's rim at a point", _sample_word_mirror,
            _build_word_mirror, word=True),
    _family("quadratic_mixed", 2, "a x^2 + b xy + d y^2 = c", _sample_quadratic_mixed, _build_quadratic_mixed),
    _family("product_term", 2, "a xy with a y^2 term on either side", _sample_product_term, _build_product_term),
    _family("word_track", 2, "Slope of a track shaped like x^2 + bxy + dy^2 = c at a point", _sample_word_track,
            _build_word_track, word=True),
    _family("folium", 3, "Folium x^3 + y^3 = kxy, possibly plus a constant", _sample_folium, _build_folium),
    _family("mixed_cubic", 3, "x^2 y or x y^2 plus a power of x or y", _sample_mixed_cubic,
            _build_mixed_cubic),
    _family("word_isoquant", 3, "Trade-off between machines and workers on x^a y^b = Q", _sample_word_isoquant,
            _build_word_isoquant, word=True),
    _family("two_mixed", 4, "Two mixed terms x^2 y and x y^2, possibly plus a power of y", _sample_two_mixed,
            _build_two_mixed),
    _family("higher_mixed", 4, "A degree 4 mixed term plus a power of x or y", _sample_higher_mixed,
            _build_higher_mixed),
    _family("slope_at_point", 4, "Tangent slope at a given point on a cubic curve", _sample_slope_at_point,
            _build_slope_at_point),
    _family("word_pendant", 4, "Slope of a folium-shaped pendant outline at a point", _sample_word_pendant,
            _build_word_pendant, word=True),
)


# --- mistakes ----------------------------------------------------------------------------


def _sides(b: Built) -> tuple[list, list]:
    return _monomials(b.equation.lhs), _monomials(b.equation.rhs)


def _bug(name: str) -> Callable[[Built], sp.Expr | None]:
    def buggy(b: Built) -> sp.Expr | None:
        return _buggy_formula(*_sides(b), name)
    return buggy


def _sign_slip(b: Built) -> sp.Expr:
    # Moved the terms without dy/dx across the equals sign but kept their signs.
    return -b.parts["formula"]


def _divided_wrong_way(b: Built) -> sp.Expr:
    return b.parts["coef"] / b.parts["other"]


def _swapped_point(b: Built) -> sp.Expr | None:
    # Point problems only: substituted x0 for y and y0 for x. The result is already
    # a number, so _at has nothing left to substitute.
    if b.at is None or b.at[x] == b.at[y]:
        return None
    return b.parts["formula"].subs({x: b.at[y], y: b.at[x]}, simultaneous=True)


def _at(b: Built, expr: sp.Expr | None) -> sp.Expr | None:
    """Mistake answers for point problems are numbers too; None if undefined there."""
    if expr is None or b.at is None:
        return expr
    value = expr.subs(b.at)
    return value if value.is_finite else None


def _pattern(tag: str, step: str, fn, note: str, signature: bool = False) -> MistakePattern:
    return MistakePattern(tag=tag, step=step, buggy=lambda b: _at(b, fn(b)), note=note, signature=signature)


MISTAKES = (
    _pattern(
        "implicit_missing_dydx", "differentiate", _bug("missing_dydx"),
        "Check the derivative of $[[y_term:yellow]]$. Since $y$ is a function of $x$, the chain rule adds a "
        "factor of $\\frac{dy}{dx}$: $\\frac{d}{dx}\\left([[y_term]]\\right) = [[y_term_prime:yellow]]$.",
        signature=True,
    ),
    _pattern(
        "implicit_missing_dydx", "differentiate", _bug("y_constant"),
        "In product terms such as $[[mixed:mint]]$ you treated $y$ as a constant. It changes with $x$, so the "
        "product rule gives $[[mixed_prime:mint]]$, and the second term carries the $\\frac{dy}{dx}$.",
    ),
    _pattern(
        "implicit_product_rule_missed", "differentiate", _bug("x_constant"),
        "Check product terms such as $[[mixed:mint]]$. You differentiated only the $y$ factor and kept the $x$ "
        "factor as it was, but the product rule differentiates each factor in turn: $[[mixed_prime:mint]]$.",
    ),
    _pattern(
        "implicit_product_rule_missed", "differentiate", _bug("product_of_derivatives"),
        "In product terms such as $[[mixed:mint]]$ you multiplied the derivatives of the two factors. The "
        "product rule adds two terms instead: $[[mixed_prime:mint]]$.",
    ),
    _pattern(
        "implicit_isolation_error", "collect", _sign_slip,
        "Check the signs as you move terms across the equals sign. A term changes sign when it moves, which "
        "gives $[[step:collect]]$.",
    ),
    _pattern(
        "implicit_isolation_error", "solve", _divided_wrong_way,
        "You divided the wrong way round. From $[[step:collect]]$, divide both sides by $[[coef:yellow]]$, the "
        "coefficient of $\\frac{dy}{dx}$.",
    ),
    _pattern(
        "constant_term_kept", "differentiate", _bug("constant_kept"),
        "The constant $[[const]]$ differentiates to $0$, so it drops out when you differentiate both sides.",
    ),
    _pattern(
        "algebra_slip", "evaluate", _swapped_point,
        "Check which number went where. At the point $[[point]]$ the first coordinate is $x$ and the second "
        "is $y$, and it looks like you swapped them.",
    ),
)


def _shape(b: Built) -> set[str]:
    left, right = _sides(b)
    return {_kind(m) for _, m in left + right}


def _hints(b: Built) -> HintLadder:
    kinds = _shape(b)
    if b.word is not None:
        nudge = "The equation does not give $y$ on its own. How can you find the slope without solving for $y$?"
    elif "mixed" in kinds:
        nudge = ("Think of $y$ as a function of $x$. Which terms need the chain rule, and which are products "
                 "that need the product rule too?")
    else:
        nudge = ("Think of $y$ as a function of $x$. What extra factor appears when you differentiate a term "
                 "with $y$ in it?")

    bigger = "Differentiate both sides with respect to $x$."
    if "y" in kinds:
        bigger += (" A power of $y$ picks up a factor of $\\frac{dy}{dx}$: "
                   "$\\frac{d}{dx}\\left([[y_term]]\\right) = [[y_term_prime:yellow]]$.")
    if "mixed" in kinds:
        bigger += " The term $[[mixed:mint]]$ is a product, so use the product rule: $[[mixed_prime:mint]]$."
    bigger += " Then collect the $\\frac{dy}{dx}$ terms on one side and divide."
    if b.at is not None:
        bigger += " Finally substitute the point $[[point]]$."
    return HintLadder(
        nudge=nudge,
        bigger=bigger,
        full_step="$[[step:differentiate]]$. Collecting the $\\frac{dy}{dx}$ terms gives $[[step:collect]]$.",
    )


SKILL = SkillSpec(
    id="calc1.derivatives.implicit_differentiation",
    slug="implicit_differentiation",
    title="Implicit differentiation",
    summary="Differentiate both sides of an equation in x and y with y as a function of x, then solve for dy/dx.",
    task="implicit_differentiate",
    families=FAMILIES,
    mistakes=MISTAKES,
    hints=_hints,
    formula=FormulaEntry(
        title="Implicit differentiation",
        latex=r"\frac{d}{dx}\,y^n = n\,y^{n-1}\,\frac{dy}{dx}, \qquad "
              r"\frac{d}{dx}\,(x\,y) = y + x\,\frac{dy}{dx}",
        note="Differentiate both sides with respect to $x$, treating $y$ as a function of $x$. Collect the "
             "$\\frac{dy}{dx}$ terms on one side, factor out $\\frac{dy}{dx}$ and divide.",
    ),
    keywords=("implicit differentiation", "differentiate implicitly", "implicitly defined function",
              "implicit function", "y as a function of x", "dy/dx in terms of x and y",
              "treat y as a function of x", "derivative of y squared", "slope of the tangent line to the curve",
              "tangent line to a curve at a point", "folium of Descartes", "solve for dy/dx"),
    prerequisites=("calc1.derivatives.chain_rule", "calc1.derivatives.product_rule"),
)
