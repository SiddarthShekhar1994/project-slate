"""Quotient rule: (f/g)' = (f'g - fg')/g^2.

Each family samples integer parameters for a top ``f`` and a bottom ``g``,
divides them, and derives the key the way a student would: differentiate the
top and the bottom from a table of basic derivatives (with the product rule
when the top is itself a product), put ``f'g - fg'`` over ``g^2`` and tidy up.
The verifier then checks the key against ``sp.diff`` independently.

Every piece is a function of the bare variable, so no family needs the chain
rule. Pieces are described by JSON-friendly specs, decoded by :func:`piece_for`.
The specs of the top and bottom go into ``params["f_spec"]`` and
``params["g_spec"]`` so mistake patterns can redo the derivatives with a
student's slip.

Parts available to notes and hints:

``f`` / ``f_prime``    the top and its derivative
``g`` / ``g_prime``    the bottom and its derivative
``assembled``          the quotient rule with the pieces plugged in, before tidying
``v``                  the variable

Snippets: ``rule`` (the rule as a formula), ``expr_colored`` (top in yellow,
bottom in mint), ``num_terms`` (``f'g - fg'`` with the pieces filled in and
coloured), ``f_g_prime`` (the term ``f g'`` coloured) and ``g_squared`` (the
bottom squared, coloured).
"""

from __future__ import annotations

from collections.abc import Callable
from math import gcd
from random import Random

import sympy as sp

from ....core.sampling import nonzero_int, pick, poly_from
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

x, t = sp.symbols("x t")

TRIG = ("sin", "cos")
TRANSCENDENTAL = ("exp", "sin", "cos", "ln")


# --- pieces ---------------------------------------------------------------


def _table(name: str, v: sp.Symbol, slip: str | None = None) -> tuple[sp.Expr, sp.Expr]:
    """``(T(v), T'(v))`` from a table of basic derivatives, or with a student's ``slip``.

    Derivatives are written the way a textbook table lists them; the
    verifier's sp.diff oracle is what decides they are right.
    """
    if name == "sin":
        return sp.sin(v), -sp.cos(v) if slip == "sin_sign" else sp.cos(v)
    if name == "cos":
        return sp.cos(v), sp.sin(v) if slip == "cos_sign" else -sp.sin(v)
    if name == "exp":
        return sp.exp(v), v * sp.exp(v - 1) if slip == "exp_power" else sp.exp(v)
    if name == "ln":
        return sp.log(v), sp.Integer(1) if slip == "ln_one" else 1 / v
    raise ValueError(f"unknown function {name!r}")


def _power_rule_coeffs(coeffs: list[int]) -> list[int]:
    """Coefficients of the derivative of ``poly_from(coeffs)``, one power-rule step per term."""
    degree = len(coeffs) - 1
    return [c * (degree - i) for i, c in enumerate(coeffs[:-1])]


def piece_for(spec: list, v: sp.Symbol, slip: str | None = None) -> tuple[sp.Expr, sp.Expr]:
    """Decode a top or bottom spec into ``(piece, derivative)``.

    ``["poly", [a, b, c]]`` is ``a v^2 + b v + c``, ``["mono", a, n]`` is
    ``a v^n``, ``["fn", c, k, name]`` is ``c + k T(v)`` for a table function
    ``T``, ``["prod", a, m, name]`` is the product ``a v^m T(v)`` and
    ``["root", k, c]`` is ``k sqrt(v) + c``.

    ``slip`` replays a student's error: ``"cos_sign"``, ``"sin_sign"``,
    ``"ln_one"`` and ``"exp_power"`` change a table derivative,
    ``"product_of_derivatives"`` differentiates a product as ``P' T'``, and
    ``"sqrt_coefficient"`` takes d/dv sqrt(v) to be ``1/sqrt(v)``.
    """
    kind = spec[0]
    if kind == "poly":
        coeffs = spec[1]
        return poly_from(coeffs, v), poly_from(_power_rule_coeffs(coeffs), v)
    if kind == "mono":
        a, n = spec[1], spec[2]
        return a * v**n, a * n * v ** (n - 1)
    if kind == "fn":
        c, k, name = spec[1], spec[2], spec[3]
        T, dT = _table(name, v, slip)
        return c + k * T, k * dT
    if kind == "prod":
        a, m, name = spec[1], spec[2], spec[3]
        T, dT = _table(name, v, slip)
        P, dP = a * v**m, a * m * v ** (m - 1)
        if slip == "product_of_derivatives":
            return P * T, dP * dT
        return P * T, dP * T + P * dT
    if kind == "root":
        k, c = spec[1], spec[2]
        d = k / sp.sqrt(v) if slip == "sqrt_coefficient" else sp.Rational(k, 2) / sp.sqrt(v)
        return k * sp.sqrt(v) + c, d
    raise ValueError(f"unknown piece {spec!r}")


def _functions(spec: list) -> set[str]:
    """Table functions a spec uses."""
    return {spec[3]} if spec[0] in ("fn", "prod") else set()


def _coprime(top: list, bottom: list, v: sp.Symbol = x) -> bool:
    """True when SymPy sees no common factor, so ``f/g`` stays as written."""
    f, _ = piece_for(top, v)
    g, _ = piece_for(bottom, v)
    return sp.gcd(f, g) == 1


def _no_double_root(coeffs: list[int]) -> bool:
    # A bottom like x^2 + 2x + 1 is a square, and the key would then cancel a factor.
    if len(coeffs) != 3:
        return True
    p, q, r = coeffs
    return q * q != 4 * p * r


# --- LaTeX helpers --------------------------------------------------------


def _piece(expr: sp.Expr, color: str | None, *, first: bool = False, latex: str | None = None) -> str:
    """One factor of a product in the rule. Sums always get brackets; a negative
    factor does too unless it opens the line."""
    out = tex(expr) if latex is None else latex
    if expr.is_Add or (not first and expr.could_extract_minus_sign()):
        out = rf"\left({out}\right)"
    return highlight(out, color) if color else out


def _squared(expr: sp.Expr, color: str | None) -> str:
    inner = highlight(tex(expr), color) if color else tex(expr)
    if expr.is_Symbol or (expr.is_Integer and expr > 0):
        return rf"{inner}^{{2}}"
    return rf"\left({inner}\right)^{{2}}"


def _numerator_tex(f: sp.Expr, fp: sp.Expr, g: sp.Expr, gp: sp.Expr) -> str:
    return (rf"{_piece(fp, 'yellow', first=True)} \cdot {_piece(g, 'mint')}"
            rf" - {_piece(f, 'yellow')} \cdot {_piece(gp, 'mint')}")


RULE_TEX = r"\frac{f' g - f g'}{g^{2}}"


# --- tidying the answer ------------------------------------------------------


def _gens(v: sp.Symbol) -> list[sp.Expr]:
    return [sp.sin(v), sp.cos(v), sp.exp(v), sp.log(v)]


def _tidy_expand(num: sp.Expr, g: sp.Expr, v: sp.Symbol) -> sp.Expr:
    # Polynomial pieces: multiply out the numerator and collect like terms.
    return sp.expand(num) / g**2


def _tidy_collect(num: sp.Expr, g: sp.Expr, v: sp.Symbol) -> sp.Expr:
    # Group the numerator by sin, cos, e^x and ln, then pull out what every term shares.
    return sp.factor_terms(sp.collect(sp.expand(num), _gens(v))) / g**2


def _tidy_monomial(num: sp.Expr, g: sp.Expr, v: sp.Symbol) -> sp.Expr:
    # g = a v^n: both numerator terms carry a v^(n-1), which cancels against g^2 = a^2 v^(2n).
    a, n = g.as_coeff_exponent(v)
    common = a * v ** (n - 1)
    reduced = sp.factor_terms(sp.collect(sp.expand(num / common), _gens(v)))
    return reduced / (a * v ** (n + 1))


def _tidy_pythagoras(num: sp.Expr, g: sp.Expr, v: sp.Symbol) -> sp.Expr:
    # sin^2 + cos^2 always turns up in the numerator of a sin-over-cos quotient.
    s, c = sp.sin(v), sp.cos(v)
    top = sp.expand(sp.expand(num).subs(s**2, 1 - c**2))
    return sp.factor(top / g**2)


def _tidy_together(num: sp.Expr, g: sp.Expr, v: sp.Symbol) -> sp.Expr:
    # A square root leaves a fraction inside the numerator; write it over one denominator.
    top, den = sp.fraction(sp.together(num))
    return sp.expand(top) / (den * g**2)


TIDY: dict[str, Callable[[sp.Expr, sp.Expr, sp.Symbol], sp.Expr]] = {
    "expand": _tidy_expand,
    "collect": _tidy_collect,
    "monomial": _tidy_monomial,
    "pythagoras": _tidy_pythagoras,
    "together": _tidy_together,
}

TIDY_TITLES = {
    "expand": "Simplify the numerator",
    "collect": "Simplify the numerator",
    "monomial": "Cancel the common power of $x$",
    "pythagoras": r"Simplify with $\sin^2 x + \cos^2 x = 1$",
    "together": "Combine the fractions in the numerator",
}


# --- builder --------------------------------------------------------------


def build_quotient(*, family: str, difficulty: int, var: sp.Symbol, top: list, bottom: list, params: Params,
                   tidy: str = "expand", fn: str = "y", word: WordContext | None = None,
                   at: dict | None = None) -> Built:
    """Divide ``top`` by ``bottom`` and walk the quotient rule.

    ``at`` is ``{"value": number}`` or ``{"value": expr, "tex": latex}`` for a
    word problem that asks for the rate at one point.
    """
    f, fp = piece_for(top, var)
    g, gp = piece_for(bottom, var)
    if sp.gcd(f, g) != 1:
        raise ValueError("top and bottom share a factor; resample")
    expr = f / g
    # The student sees SymPy's form of expr. If it is no longer f over g (a
    # factor cancelled, a sign moved out front), the named parts would not
    # match what is on screen, so reject.
    if sp.fraction(expr) != (f, g):
        raise ValueError("SymPy rewrote the quotient; resample")
    params = {**params, "f_spec": top, "g_spec": bottom}

    numerator = fp * g - f * gp
    assembled = numerator / g**2
    key = TIDY[tidy](numerator, g, var)

    if tidy == "monomial" and g.as_coeff_exponent(var)[1] == 1:
        tidy_title = TIDY_TITLES["collect"]  # nothing to cancel when g is a multiple of x
    else:
        tidy_title = TIDY_TITLES[tidy]

    num_tex = _numerator_tex(f, fp, g, gp)
    g_sq = _squared(g, "mint")
    parts = {
        "f": f,
        "g": g,
        "f_prime": fp,
        "g_prime": gp,
        "assembled": assembled,
        "v": var,
    }
    snippets = {
        "rule": RULE_TEX,
        "expr_colored": rf"\frac{{{highlight(tex(f), 'yellow')}}}{{{highlight(tex(g), 'mint')}}}",
        "num_terms": num_tex,
        "f_g_prime": rf"{_piece(f, 'yellow', first=True)} \cdot {_piece(gp, 'mint')}",
        "g_squared": g_sq,
    }

    v = tex(var)
    lhs = rf"\frac{{d{fn}}}{{d{v}}}" if at is None else rf"{fn}'({v})"
    differentiate_title = (
        "Differentiate the top with the product rule, then the bottom" if top[0] == "prod"
        else "Differentiate the top and the bottom"
    )
    steps = [
        Step(
            id="identify",
            title="Name the top and the bottom",
            latex=rf"f({v}) = {highlight(tex(f), 'yellow')},\quad g({v}) = {highlight(tex(g), 'mint')}",
        ),
        Step(
            id="differentiate",
            title=differentiate_title,
            latex=rf"f'({v}) = {highlight(tex(fp), 'yellow')},\quad g'({v}) = {highlight(tex(gp), 'mint')}",
        ),
        Step(
            id="assemble",
            title="Apply the quotient rule",
            latex=rf"{lhs} = {RULE_TEX} = \frac{{{num_tex}}}{{{g_sq}}}",
            expr=assembled,
        ),
        Step(
            id="simplify",
            title=tidy_title,
            latex=rf"{lhs} = {tex(key)}",
            expr=key,
        ),
    ]

    key_out = key
    point = None
    if at is not None:
        t0 = sp.sympify(at["value"])
        t0_tex = at.get("tex", tex(t0))
        point = {var: t0}
        f0, fp0, g0, gp0 = (e.subs(point) for e in (f, fp, g, gp))
        key_out = (fp0 * g0 - f0 * gp0) / g0**2
        if key_out == 0:
            raise ValueError("a zero rate makes a poor question; resample")
        steps.append(Step(
            id="evaluate",
            title=f"Evaluate at ${v} = {t0_tex}$",
            latex=rf"{fn}'({t0_tex}) = \frac{{{_numerator_tex(f0, fp0, g0, gp0)}}}{{{_squared(g0, 'mint')}}}"
                  rf" = {tex(key_out)}",
            expr=key_out,
        ))

    if word is not None:
        prompt = f"{word.text} {word.question}"
    else:
        prompt = rf"Differentiate ${fn} = {tex(expr)}$."

    built = Built(
        family=family,
        difficulty=difficulty,
        task="differentiate",
        var=var,
        expr=expr,
        key=key_out,
        steps=tuple(steps),
        parts=parts,
        params=params,
        prompt=prompt,
        at=point,
        word=word,
        snippets=snippets,
    )
    if point is not None:
        _require_distinct_answers(built)
    return built


def _require_distinct_answers(b: Built) -> None:
    """Reject a point problem where two mistakes, or a mistake and the key, give the same number.

    Formulas rarely coincide, but single numbers often do (``f'/g`` and
    ``(f'g - fg')/g`` agree whenever ``f'g - fg' = f'`` at the point), and
    then the feedback could only name one of the two slips.
    """
    seen = {b.key}
    for pattern in MISTAKES:
        wrong = pattern.buggy(b)
        if wrong is None:
            continue
        if wrong in seen:
            raise ValueError(f"{pattern.tag} gives the same number as another answer; resample")
        seen.add(wrong)


def _builds(build: Callable[[Params], Built], params: Params) -> bool:
    try:
        build(params)
    except ValueError:
        return False
    return True


# --- families -------------------------------------------------------------


def _family(id: str, difficulty: int, description: str, sample, build, word: bool = False) -> Family:
    return Family(id=id, difficulty=difficulty, description=description, sample=sample, build=build, word=word)


def _linear(rng: Random, *, a_lo: int = 1, a_hi: int = 4, b_lo: int = -6, b_hi: int = 6) -> list[int]:
    """``[a, b]`` for ``a x + b`` with ``b != 0`` and no common factor, so it does not read as ``2(x + 2)``."""
    while True:
        a, b = nonzero_int(rng, a_lo, a_hi), nonzero_int(rng, b_lo, b_hi)
        if gcd(a, b) == 1:
            return [a, b]


# d1 ----------------------------------------------------------------------

def _readable_top(a: int, b: int) -> bool:
    # A top like -4x - 2 reads as a sign mistake; 3 - 2x is fine.
    return gcd(a, b) == 1 and not (a < 0 and b < 0)


def _sample_linear_over_linear(rng: Random) -> Params:
    while True:
        a, b = nonzero_int(rng, -5, 5), nonzero_int(rng, -7, 7)
        c, d = _linear(rng, b_lo=-7, b_hi=7)
        # ad = bc would make the top a multiple of the bottom: a constant, not a quotient.
        # ad - bc = a would make (f'g - fg')/g the same answer as f'/g.
        if a * d - b * c not in (0, a) and _readable_top(a, b):
            return {"top": [a, b], "bottom": [c, d]}


def _build_linear_over_linear(p: Params) -> Built:
    return build_quotient(family="linear_over_linear", difficulty=1, var=x, top=["poly", p["top"]],
                          bottom=["poly", p["bottom"]], params=p)


def _sample_power_over_linear(rng: Random) -> Params:
    return {"k": pick(rng, [1, 1, 1, 2, 3]), "n": rng.randint(2, 4), "bottom": _linear(rng)}


def _build_power_over_linear(p: Params) -> Built:
    return build_quotient(family="power_over_linear", difficulty=1, var=x, top=["mono", p["k"], p["n"]],
                          bottom=["poly", p["bottom"]], params=p)


# d2 ----------------------------------------------------------------------

def _sample_poly_over_quadratic(rng: Random) -> Params:
    while True:
        a, b = nonzero_int(rng, -5, 5), nonzero_int(rng, -6, 6)
        if rng.random() < 0.6 and _readable_top(a, b):
            top = ["poly", [a, b]]
        else:
            top = ["mono", rng.randint(1, 4), pick(rng, [1, 2])]
        coeffs = [pick(rng, [1, 1, 2]), rng.randint(-4, 4), nonzero_int(rng, -6, 6)]
        bottom = ["poly", coeffs]
        if _no_double_root(coeffs) and _coprime(top, bottom):
            return {"top": top, "bottom": bottom}


def _build_poly_over_quadratic(p: Params) -> Built:
    return build_quotient(family="poly_over_quadratic", difficulty=2, var=x, top=p["top"], bottom=p["bottom"],
                          params=p)


def _sample_trig_over_x(rng: Random) -> Params:
    top = ["fn", 0, pick(rng, [1, 1, 2, 3, 4, 5]), pick(rng, TRIG)]
    if rng.random() < 0.75:
        bottom = ["mono", 1, pick(rng, [1, 1, 2, 3])]
    else:
        bottom = ["poly", [1, rng.randint(1, 5)]]
    return {"top": top, "bottom": bottom}


def _build_trig_over_x(p: Params) -> Built:
    tidy = "monomial" if p["bottom"][0] == "mono" else "collect"
    return build_quotient(family="trig_over_x", difficulty=2, var=x, top=p["top"], bottom=p["bottom"], params=p,
                          tidy=tidy)


def _sample_exp_over_linear(rng: Random) -> Params:
    return {"k": pick(rng, [1, 1, 2, 3]), "bottom": _linear(rng)}


def _build_exp_over_linear(p: Params) -> Built:
    return build_quotient(family="exp_over_linear", difficulty=2, var=x, top=["fn", 0, p["k"], "exp"],
                          bottom=["poly", p["bottom"]], params=p, tidy="collect")


# d3 ----------------------------------------------------------------------

def _sample_ln_over_power(rng: Random) -> Params:
    return {"c": pick(rng, [0, 0, 0, 1, 2, 3, -1, -2]), "a": pick(rng, [1, 1, 1, 2]), "n": rng.randint(1, 3)}


def _build_ln_over_power(p: Params) -> Built:
    return build_quotient(family="ln_over_power", difficulty=3, var=x, top=["fn", p["c"], 1, "ln"],
                          bottom=["mono", p["a"], p["n"]], params=p, tidy="monomial")


def _sample_trig_ratio(rng: Random) -> Params:
    first = pick(rng, TRIG)
    second = "cos" if first == "sin" else "sin"
    return {"top": ["fn", pick(rng, [0, 0, 1, 2, 3]), 1, first], "bottom": ["fn", pick(rng, [0, 1, 1, 2, 3]), 1, second]}


def _build_trig_ratio(p: Params) -> Built:
    return build_quotient(family="trig_ratio", difficulty=3, var=x, top=p["top"], bottom=p["bottom"], params=p,
                          tidy="pythagoras")


def _sample_quadratic_over_quadratic(rng: Random) -> Params:
    while True:
        top = [rng.randint(1, 3), rng.randint(-5, 5), rng.randint(-5, 5)]
        bottom = [pick(rng, [1, 1, 2]), rng.randint(-4, 4), nonzero_int(rng, -6, 6)]
        if top[1] == top[2] == 0 or not _no_double_root(bottom):
            continue
        if _coprime(["poly", top], ["poly", bottom]):
            return {"top": top, "bottom": bottom}


def _build_quadratic_over_quadratic(p: Params) -> Built:
    return build_quotient(family="quadratic_over_quadratic", difficulty=3, var=x, top=["poly", p["top"]],
                          bottom=["poly", p["bottom"]], params=p)


# d4 ----------------------------------------------------------------------

def _sample_product_over_poly(rng: Random) -> Params:
    top = ["prod", 1, pick(rng, [1, 1, 2]), pick(rng, TRANSCENDENTAL)]
    if rng.random() < 0.6:
        bottom = ["poly", [1, nonzero_int(rng, -5, 5)]]
    else:
        bottom = ["poly", [1, 0, rng.randint(1, 6)]]
    return {"top": top, "bottom": bottom}


def _build_product_over_poly(p: Params) -> Built:
    return build_quotient(family="product_over_poly", difficulty=4, var=x, top=p["top"], bottom=p["bottom"],
                          params=p, tidy="collect")


def _sample_sqrt_quotient(rng: Random) -> Params:
    if rng.random() < 0.6:
        # sqrt(x) + c over a x + b or x^2 + c. Positive constants on the bottom
        # keep a hidden factor like (sqrt(x) - 1)/(x - 1) out.
        top = ["root", 1, pick(rng, [0, 0, 1, 2, -1])]
        if rng.random() < 0.6:
            bottom = ["poly", _linear(rng, a_hi=3, b_lo=1, b_hi=6)]
        else:
            bottom = ["poly", [1, 0, rng.randint(1, 6)]]
        return {"top": top, "bottom": bottom}
    # a x + b over sqrt(x) + c, avoiding a x + b = a (sqrt(x) - c)(sqrt(x) + c).
    c = rng.randint(1, 4)
    while True:
        a, b = _linear(rng, a_hi=3)
        if b != -a * c * c:
            return {"top": ["poly", [a, b]], "bottom": ["root", 1, c]}


def _build_sqrt_quotient(p: Params) -> Built:
    return build_quotient(family="sqrt_quotient", difficulty=4, var=x, top=p["top"], bottom=p["bottom"], params=p,
                          tidy="together")


# word problems -------------------------------------------------------------

_CONCENTRATION = (
    ("A drug is injected into a patient's bloodstream. Its concentration $t$ hours later is "
     "$c(t) = {expr}$ milligrams per litre."),
    "How fast is the concentration changing, in mg/L per hour, at $t = {t0}$?",
)
_AVERAGE_COST = (
    ("A workshop's total cost to build $x$ tables is $C(x) = {cost}$ dollars, so the average cost per table "
     "is $A(x) = \\frac{{C(x)}}{{x}} = {expr}$."),
    "How fast is the average cost per table changing at $x = {x0}$, in dollars per table for each extra table?",
)
_POPULATION = (
    "A lake is stocked with fish. After $t$ years the number of fish is modelled by $P(t) = {expr}$.",
    "How fast is the population growing, in fish per year, when $t = {t0}$?",
)


def _sample_word_concentration(rng: Random) -> Params:
    # Rejects t0^2 = b, the peak where the rate is zero, and points where two mistakes agree.
    while True:
        p = {"a": rng.randint(2, 9), "b": rng.randint(1, 9), "t0": rng.randint(1, 4)}
        if _builds(_build_word_concentration, p):
            return p


def _build_word_concentration(p: Params) -> Built:
    top, bottom = ["mono", p["a"], 1], ["poly", [1, 0, p["b"]]]
    expr = piece_for(top, t)[0] / piece_for(bottom, t)[0]
    text, question = _CONCENTRATION
    word = WordContext(text=text.format(expr=tex(expr)), question=question.format(t0=p["t0"]), unit="mg/L per hour")
    return build_quotient(family="word_concentration", difficulty=2, var=t, top=top, bottom=bottom, params=p,
                          tidy="collect", fn="c", word=word, at={"value": p["t0"]})


def _sample_word_average_cost(rng: Random) -> Params:
    # Rejects a x0^2 = c, where the average cost bottoms out and the rate is zero,
    # and points where two mistakes agree.
    while True:
        cost = [rng.randint(1, 3), 10 * rng.randint(1, 6), 100 * rng.randint(2, 15)]
        p = {"cost": cost, "x0": pick(rng, [10, 20, 25, 50])}
        if _builds(_build_word_average_cost, p):
            return p


def _build_word_average_cost(p: Params) -> Built:
    top, bottom = ["poly", p["cost"]], ["mono", 1, 1]
    cost = piece_for(top, x)[0]
    text, question = _AVERAGE_COST
    word = WordContext(text=text.format(cost=tex(cost), expr=tex(cost / x)), question=question.format(x0=p["x0"]),
                       unit="dollars per table per table")
    return build_quotient(family="word_average_cost", difficulty=3, var=x, top=top, bottom=bottom, params=p,
                          tidy="collect", fn="A", word=word, at={"value": p["x0"]})


def _sample_word_population(rng: Random) -> Params:
    # a = (b + 1)^2 m makes the rate at t = 0 the whole number b m. b = 1 is
    # left out: then f'/g and (f'g - fg')/g are the same function.
    while True:
        b, m = pick(rng, [2, 3, 4, 9]), pick(rng, [10, 20, 50])
        p = {"a": (b + 1) ** 2 * m, "b": b, "when": pick(rng, ["zero", "ln"])}
        if _builds(_build_word_population, p):
            return p


def _build_word_population(p: Params) -> Built:
    top, bottom = ["fn", 0, p["a"], "exp"], ["fn", p["b"], 1, "exp"]
    expr = piece_for(top, t)[0] / piece_for(bottom, t)[0]
    # At t = ln b the population is half of a, where it grows fastest.
    if p["when"] == "ln":
        at = {"value": sp.log(p["b"]), "tex": rf"\ln {p['b']}"}
    else:
        at = {"value": 0}
    text, question = _POPULATION
    t0_tex = at.get("tex", "0")
    word = WordContext(text=text.format(expr=tex(expr)), question=question.format(t0=t0_tex), unit="fish per year")
    return build_quotient(family="word_population", difficulty=4, var=t, top=top, bottom=bottom, params=p,
                          tidy="collect", fn="P", word=word, at=at)


FAMILIES = (
    _family("linear_over_linear", 1, "Linear over linear, (ax+b)/(cx+d)", _sample_linear_over_linear,
            _build_linear_over_linear),
    _family("power_over_linear", 1, "Power of x over a linear function", _sample_power_over_linear,
            _build_power_over_linear),
    _family("poly_over_quadratic", 2, "Linear or monomial over a quadratic", _sample_poly_over_quadratic,
            _build_poly_over_quadratic),
    _family("trig_over_x", 2, "sin or cos over a power of x or x + b", _sample_trig_over_x, _build_trig_over_x),
    _family("exp_over_linear", 2, "e^x over a linear function", _sample_exp_over_linear, _build_exp_over_linear),
    _family("word_concentration", 2, "Rate of change of a drug concentration at/(t^2+b) at a time",
            _sample_word_concentration, _build_word_concentration, word=True),
    _family("ln_over_power", 3, "ln x plus a constant over a power of x", _sample_ln_over_power,
            _build_ln_over_power),
    _family("trig_ratio", 3, "sin over cos style quotients, c + sin x over c + cos x", _sample_trig_ratio,
            _build_trig_ratio),
    _family("quadratic_over_quadratic", 3, "Quadratic over quadratic", _sample_quadratic_over_quadratic,
            _build_quadratic_over_quadratic),
    _family("word_average_cost", 3, "Rate of change of average cost C(x)/x at a production level",
            _sample_word_average_cost, _build_word_average_cost, word=True),
    _family("product_over_poly", 4, "x or x^2 times e^x, sin, cos or ln over x + b or x^2 + c",
            _sample_product_over_poly, _build_product_over_poly),
    _family("sqrt_quotient", 4, "Quotients with sqrt(x) in the top or the bottom", _sample_sqrt_quotient,
            _build_sqrt_quotient),
    _family("word_population", 4, "Growth rate of a population a e^t/(b + e^t) at a time", _sample_word_population,
            _build_word_population, word=True),
)


# --- mistakes -------------------------------------------------------------


def _pieces(b: Built, slip: str | None = None) -> tuple[sp.Expr, sp.Expr, sp.Expr, sp.Expr]:
    f, fp = piece_for(b.params["f_spec"], b.var, slip)
    g, gp = piece_for(b.params["g_spec"], b.var, slip)
    return f, fp, g, gp


def _swapped(b: Built) -> sp.Expr:
    f, fp, g, gp = _pieces(b)
    return (f * gp - fp * g) / g**2


def _not_squared(b: Built) -> sp.Expr:
    f, fp, g, gp = _pieces(b)
    return (fp * g - f * gp) / g


def _derivative_ratio(b: Built) -> sp.Expr:
    _, fp, _, gp = _pieces(b)
    return fp / gp


def _trig_slip(b: Built) -> str | None:
    # d/dx cos x = sin x is the usual slip, so flip cos when there is one.
    used = _functions(b.params["f_spec"]) | _functions(b.params["g_spec"])
    if "cos" in used:
        return "cos_sign"
    if "sin" in used:
        return "sin_sign"
    return None


def _plus_instead_of_minus(b: Built) -> sp.Expr | None:
    f, fp, g, gp = _pieces(b)
    slip = _trig_slip(b)
    if slip is not None:
        _, sfp, _, sgp = _pieces(b, slip)
        # A flipped cos derivative on the bottom alone gives this same answer;
        # the trig pattern explains that case better.
        if sfp == fp and sgp == -gp:
            return None
    return (fp * g + f * gp) / g**2


def _top_only(b: Built) -> sp.Expr:
    # Treated the bottom as a constant: f'/g, the quotient rule without the f g' term.
    _, fp, g, _ = _pieces(b)
    return fp / g


def _with_slip(slip: str) -> Callable[[Built], sp.Expr | None]:
    """The quotient rule done right, but with the derivatives a ``slip`` produces."""

    def wrong(b: Built) -> sp.Expr | None:
        f, fp, g, gp = _pieces(b)
        _, sfp, _, sgp = _pieces(b, slip)
        if sfp == fp and sgp == gp:
            return None  # the slip cannot happen on this problem
        return (sfp * g - f * sgp) / g**2

    return wrong


def _exp_power(b: Built) -> sp.Expr | None:
    wrong = _with_slip("exp_power")(b)
    # At t = 0 this slip makes every derivative zero, and a zero answer has
    # too many other explanations to blame on e^t.
    if wrong is not None and b.at is not None and wrong.subs(b.at) == 0:
        return None
    return wrong


def _trig_sign(b: Built) -> sp.Expr | None:
    slip = _trig_slip(b)
    return None if slip is None else _with_slip(slip)(b)


def _at(b: Built, expr: sp.Expr | None) -> sp.Expr | None:
    """Mistake answers for 'evaluate at a point' problems are numbers too."""
    if expr is None or b.at is None:
        return expr
    value = expr.subs(b.at)
    # A slip can put a zero in a denominator at the point; there is no answer to match then.
    if value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        return None
    return value


def _pattern(tag: str, step: str, fn, note: str, signature: bool = False) -> MistakePattern:
    return MistakePattern(tag=tag, step=step, buggy=lambda b: _at(b, fn(b)), note=note, signature=signature)


MISTAKES = (
    _pattern(
        "quotient_numerator_swapped", "assemble", _swapped,
        "Check the order in the numerator. It starts with the derivative of the top, $[[num_terms]]$; "
        "subtracting the other way round flips the sign of the whole answer.",
        signature=True,
    ),
    _pattern(
        "quotient_denominator_not_squared", "assemble", _not_squared,
        "Look at the denominator. The quotient rule divides by the bottom squared, $[[g_squared]]$, "
        "not by $[[g:mint]]$ itself.",
        signature=True,
    ),
    _pattern(
        "quotient_as_derivative_ratio", "assemble", _derivative_ratio,
        "You divided the derivative of the top by the derivative of the bottom, but the quotient rule is "
        "$[[rule]]$. It uses $[[f:yellow]]$ and $[[g:mint]]$ themselves as well as their derivatives.",
    ),
    _pattern(
        "quotient_plus_instead_of_minus", "assemble", _plus_instead_of_minus,
        "Check the sign between the two terms on top. The quotient rule subtracts, $[[num_terms]]$; "
        "adding them is the product rule's pattern.",
    ),
    _pattern(
        "dropped_term", "assemble", _top_only,
        "You differentiated the top but treated the bottom as a constant. The bottom changes too, so the "
        "numerator also subtracts $[[f_g_prime]]$ and everything goes over $[[g_squared]]$.",
    ),
    _pattern(
        "product_of_derivatives", "differentiate", _with_slip("product_of_derivatives"),
        "The top, $[[f:yellow]]$, is a product, so its derivative needs the product rule: "
        "$f' = [[f_prime:yellow]]$. Multiplying the derivatives of its two factors is not enough.",
    ),
    _pattern(
        "trig_derivative_sign", "differentiate", _trig_sign,
        "Recheck the sign of the trig derivative: $\\frac{d}{dx}\\sin x = \\cos x$ but "
        "$\\frac{d}{dx}\\cos x = -\\sin x$.",
    ),
    _pattern(
        "exp_log_derivative_error", "differentiate", _with_slip("ln_one"),
        "Recheck the derivative of $\\ln [[v]]$. It is $\\frac{1}{[[v]]}$, not $1$.",
    ),
    _pattern(
        "exp_log_derivative_error", "differentiate", _exp_power,
        "The function $e^{[[v]]}$ is not a power of $[[v]]$, so the power rule does not apply to it. "
        "Its derivative is $e^{[[v]]}$ itself.",
    ),
    _pattern(
        "power_coefficient_dropped", "differentiate", _with_slip("sqrt_coefficient"),
        "Recheck the derivative of $\\sqrt{[[v]]} = [[v]]^{1/2}$. The power rule brings the $\\frac{1}{2}$ "
        "down, so it is $\\frac{1}{2\\sqrt{[[v]]}}$.",
    ),
)


WORD_QUANTITY = {
    "word_concentration": "concentration",
    "word_average_cost": "average cost",
    "word_population": "population",
}


def _hints(b: Built) -> HintLadder:
    top, bottom = b.params["f_spec"], b.params["g_spec"]
    if b.family in WORD_QUANTITY:
        nudge = (f"The {WORD_QUANTITY[b.family]} is one function of ${tex(b.var)}$ divided by another. "
                 "How do you differentiate a quotient?")
    else:
        nudge = "This is one function divided by another. Which part is the top, which is the bottom, and what rule fits?"

    bigger = ("Let $f = [[f:yellow]]$ be the top and $g = [[g:mint]]$ the bottom. "
              "The quotient rule gives $[[rule]]$, so find $f'$ and $g'$ first.")
    if top[0] == "prod":
        bigger += " The top is a product, so $f'$ needs the product rule."
    if "root" in (top[0], bottom[0]):
        bigger += " Write $\\sqrt{x}$ as $x^{1/2}$ to differentiate it."
    if b.family == "trig_ratio":
        bigger += " Afterwards, $\\sin^2 x + \\cos^2 x = 1$ tidies the numerator."
    if b.at is not None:
        evaluate = next(s for s in b.steps if s.id == "evaluate")
        bigger += f" Then {evaluate.title[0].lower()}{evaluate.title[1:]}."
    return HintLadder(nudge=nudge, bigger=bigger, full_step="$[[step:assemble]]$")


SKILL = SkillSpec(
    id="calc1.derivatives.quotient_rule",
    slug="quotient_rule",
    title="Quotient rule",
    summary="Differentiate a quotient: the top's derivative times the bottom, minus the top times the bottom's "
            "derivative, all over the bottom squared.",
    task="differentiate",
    families=FAMILIES,
    mistakes=MISTAKES,
    hints=_hints,
    formula=FormulaEntry(
        title="Quotient rule",
        latex=r"\frac{d}{dx}\left[\frac{f(x)}{g(x)}\right] = \frac{f'(x)\,g(x) - f(x)\,g'(x)}{\big[g(x)\big]^{2}}",
        note="Start with the derivative of the top: the order matters because of the minus sign. "
             "Divide by the bottom squared, not the bottom.",
    ),
    keywords=("quotient rule", "derivative of a quotient", "quotient of two functions", "differentiating quotients",
              "derivative of a fraction", "derivative of a rational function", "low d-high minus high d-low",
              "f'g - fg'", "u'v - uv'", "over the denominator squared", "derivative of tan x"),
    prerequisites=("calc1.derivatives.power_rule", "calc1.derivatives.product_rule"),
)
