"""Power rule: d/dx x^n = n x^(n-1), applied term by term.

Every problem here is a sum of terms a*x^n, sometimes in disguise: negative
powers written as 1/x^n, fractional powers written as roots, or (at the
challenge level) a quotient or product that has to be split or multiplied out
first. Each family samples the terms, builds the expression the student sees,
and derives the key the way a student would: bring each exponent down, lower
it by one, and let constants go to zero. The verifier then checks the key
against ``sp.diff`` independently.

Parts available to notes and hints:

``power_form``                     the function as a sum of a*x^n terms (SymPy form)
``derivative``                     the derivative, before any point is substituted
``focus`` / ``focus_prime``        the first term whose exponent is not 0 or 1, and its derivative
``constant``                       the constant term after rewriting (0 when there is none)
``numerator`` / ``denominator``    quotient families only
``factor`` / ``bracket``           product families only

Snippets write exponents out (``5 x^{-2}`` rather than ``\\frac{5}{x^{2}}``):
``rewritten`` (the whole function as powers), ``fx`` and ``fprime`` (``f(x)``,
``f'(x)``), ``focus_power`` / ``focus_prime_power``, ``neg_power`` /
``neg_prime_power`` (first negative exponent) and ``frac_power`` /
``frac_prime_power`` (first fractional exponent). The ``neg_*`` and ``frac_*``
snippets fall back to the focus term when the problem has no such exponent;
the notes that use them are only shown when one exists.
"""

from __future__ import annotations

from collections.abc import Callable
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

x, t, r, s, q = sp.symbols("x t r s q")

Term = tuple[sp.Expr, sp.Rational]
"""``(a, n)`` for one term ``a * x**n``."""

Rule = Callable[[sp.Expr, sp.Rational], "Term | None"]
"""What a student does to one term: the derivative term it produces, or None for zero."""


def _q(value: int | str) -> sp.Rational:
    """Exact rational from a JSON value: an int, or a string such as ``"3/2"``."""
    return sp.Rational(value)


def _decode(spec: list) -> list[Term]:
    return [(_q(a), _q(n)) for a, n in spec]


def _sum(terms: list[Term], var: sp.Symbol) -> sp.Expr:
    return sp.Add(*[a * var**n for a, n in terms])


def _terms_of(expr: sp.Expr, var: sp.Symbol) -> list[Term]:
    """Split a sum of single powers back into ``(a, n)`` pairs, in SymPy's print order."""
    return [term.as_coeff_exponent(var) for term in expr.as_ordered_terms()]


# --- the rule, one term at a time ---------------------------------------------
# Mistake patterns reuse these with a wrong rule, so a buggy answer is built the
# same way as the key, just with the student's slip in place of the right move.


def _correct(a: sp.Expr, n: sp.Rational) -> Term | None:
    return None if n == 0 else (n * a, n - 1)


def _not_reduced(a: sp.Expr, n: sp.Rational) -> Term | None:
    # Brought the exponent down but kept it: 3x^4 -> 12x^4.
    return None if n == 0 else (n * a, n)


def _coefficient_dropped(a: sp.Expr, n: sp.Rational) -> Term | None:
    # Lowered the exponent but never multiplied by it: 3x^4 -> 3x^3.
    return None if n == 0 else (a, n - 1)


def _negative_slip(a: sp.Expr, n: sp.Rational) -> Term | None:
    # Moved a negative exponent toward zero: 5x^-2 -> -10x^-1.
    if n < 0:
        return (n * a, n + 1)
    return _correct(a, n)


def _fraction_slip(a: sp.Expr, n: sp.Rational) -> Term | None:
    # Took one off the numerator only: 4x^(3/2) -> 6x^(2/2) = 6x.
    if not n.is_integer:
        return (n * a, sp.Rational(n.p - 1, n.q))
    return _correct(a, n)


def _constant_kept(a: sp.Expr, n: sp.Rational) -> Term | None:
    return (a, n) if n == 0 else _correct(a, n)


def _apply(terms: list[Term], var: sp.Symbol, rule: Rule) -> sp.Expr:
    out = [rule(a, n) for a, n in terms]
    return sp.Add(*[c * var**e for c, e in (o for o in out if o is not None)])


def _differentiate(expr: sp.Expr, var: sp.Symbol) -> sp.Expr:
    """Power rule on a small sum of single powers, such as a numerator or one factor."""
    return _apply(_terms_of(expr, var), var, _correct)


# --- LaTeX ---------------------------------------------------------------------


def tex_power(a: sp.Expr, n: sp.Rational, var: sp.Symbol, *, color: str | None = None) -> str:
    """``a x^n`` with the exponent written out (``5 x^{-2}``, not ``\\frac{5}{x^{2}}``).

    ``color`` highlights the exponent; ``x^1`` is then written ``x^{1}`` so the
    exponent the rule brings down is visible.
    """
    if n == 0:
        return tex(a)
    exponent = highlight(tex(n), color) if color else tex(n)
    power = tex(var) if n == 1 and not color else f"{tex(var)}^{{{exponent}}}"
    if a == 1:
        return power
    if a == -1:
        return f"-{power}"
    return f"{tex(a)} {power}"


def join_terms(pieces: list[str]) -> str:
    """Join signed term LaTeX into a sum, writing ``+ -3`` as ``- 3``."""
    out = pieces[0]
    for piece in pieces[1:]:
        out += f" - {piece[1:].lstrip()}" if piece.startswith("-") else f" + {piece}"
    return out


def _factor(value: sp.Expr) -> str:
    """LaTeX for a factor in a product, in brackets when negative."""
    out = tex(value)
    return rf"\left({out}\right)" if value.is_negative else out


def tex_power_rule(a: sp.Expr, n: sp.Rational, var: sp.Symbol) -> str:
    """One term of the power rule step: the exponent brought down (yellow), lowered by one (mint)."""
    if n == 0:
        return "0"
    down = highlight(_factor(n), "yellow")
    lowered = highlight(f"{tex(n)} - 1", "mint")
    coefficient = "" if a == 1 else rf" \cdot {_factor(a)}"
    return rf"{down}{coefficient}\, {tex(var)}^{{{lowered}}}"


# --- builder -------------------------------------------------------------------


def build_power(*, family: str, difficulty: int, var: sp.Symbol, terms: list[Term], params: Params,
                expr: sp.Expr | None = None, form: str | None = None, middle: str | None = None,
                extra_parts: dict[str, sp.Expr] | None = None, fn: str = "f",
                word: WordContext | None = None, at: dict | None = None) -> Built:
    """Walk the power rule over ``terms`` (each ``(a, n)`` for ``a * var**n``).

    Without ``expr`` the student sees the plain sum, in SymPy's form and order.
    Quotient and product families pass the unexpanded ``expr``, a ``form``
    (``"quotient"`` or ``"product"``), the ``middle`` LaTeX that splits it into
    single powers, and ``terms`` in the order ``middle`` lists them.
    """
    v = tex(var)
    fx, fprime = f"{fn}({v})", f"{fn}'({v})"

    if expr is None:
        expr = _sum(terms, var)
        shown = _terms_of(expr, var)
        if len(shown) != len(terms):
            raise ValueError("two terms merged into one; resample")
        terms = shown
        form = "poly" if all(n.is_integer and n >= 0 for _, n in terms) else "powers"
    if form is None:
        raise ValueError("an unexpanded expression needs a form")
    if len({n for _, n in terms}) != len(terms):
        raise ValueError("two terms share an exponent after rewriting; resample")
    # With only exponents 0 and 1 the factor brought down is 1, so a student who
    # never brings it down still gets the key: the problem would not test the rule.
    if all(n in (0, 1) for _, n in terms):
        raise ValueError("every exponent is 0 or 1; resample")
    params = {**params, "form": form}

    derivative = _apply(terms, var, _correct)

    focus = next(term for term in terms if term[1] not in (0, 1))
    negative = next((term for term in terms if term[1] < 0), focus)
    fractional = next((term for term in terms if not term[1].is_integer), focus)
    constant = sp.Add(*[a for a, n in terms if n == 0])

    parts = {
        "power_form": _sum(terms, var),
        "derivative": derivative,
        "focus": focus[0] * var ** focus[1],
        "focus_prime": _sum([_correct(*focus)], var),
        "constant": constant,
        **(extra_parts or {}),
    }
    snippets = {
        "fx": fx,
        "fprime": fprime,
        "rewritten": join_terms([tex_power(a, n, var) for a, n in terms]),
        "focus_power": tex_power(*focus, var),
        "focus_prime_power": tex_power(*_correct(*focus), var),
        "neg_power": tex_power(*negative, var),
        "neg_prime_power": tex_power(*_correct(*negative), var),
        "frac_power": tex_power(*fractional, var),
        "frac_prime_power": tex_power(*_correct(*fractional), var),
    }

    powers = join_terms([tex_power(a, n, var, color="yellow") for a, n in terms])
    if form == "poly":
        rewrite_title, rewrite = "Spot the exponent on each term", rf"{fx} = {powers}"
    elif form == "powers":
        rewrite_title, rewrite = f"Rewrite each term as a power of ${v}$", rf"{fx} = {tex(expr)} = {powers}"
    elif form == "quotient":
        rewrite_title = f"Split the fraction into powers of ${v}$"
        rewrite = rf"{fx} = {tex(expr)} = {middle} = {powers}"
    elif form == "product":
        rewrite_title = f"Multiply out into powers of ${v}$"
        rewrite = rf"{fx} = {tex(expr)} = {middle} = {powers}"
    else:
        raise ValueError(f"unknown form {form!r}")

    # The derivative with exponents written out, in the order SymPy prints the
    # key, then the key itself when it looks different (roots, fractions).
    tidy = join_terms([tex_power(c, e, var) for c, e in _terms_of(derivative, var)])
    if tidy.replace(" ", "") != tex(derivative).replace(" ", ""):
        tidy += f" = {tex(derivative)}"

    steps = [
        Step(id="rewrite", title=rewrite_title, latex=rewrite),
        Step(
            id="power_rule",
            title="Apply the power rule to each term",
            latex=rf"{fprime} = " + " + ".join(tex_power_rule(a, n, var) for a, n in terms),
            expr=derivative,
        ),
        Step(id="simplify", title="Simplify each term", latex=rf"{fprime} = {tidy}", expr=derivative),
    ]

    key = derivative
    point = None
    if at is not None:
        value = sp.Rational(at["value"])
        point = {var: value}
        key = sp.simplify(derivative.subs(point))
        # At a single point the signature mistakes can land on the right number
        # (at x = 1, x^n and x^(n-1) agree), which would make the problem useless.
        for rule in (_not_reduced, _coefficient_dropped):
            if sp.simplify(_apply(terms, var, rule).subs(point) - key) == 0:
                raise ValueError("a signature mistake gives the right number here; resample")
        steps.append(Step(
            id="evaluate",
            title=f"Evaluate at ${v} = {tex(value)}$",
            latex=rf"{fn}'({tex(value)}) = {tex(key)}",
            expr=key,
        ))

    prompt = f"{word.text} {word.question}" if word is not None else rf"Differentiate ${fx} = {tex(expr)}$."

    return Built(
        family=family,
        difficulty=difficulty,
        task="differentiate",
        var=var,
        expr=expr,
        key=key,
        steps=tuple(steps),
        parts=parts,
        params=params,
        prompt=prompt,
        at=point,
        word=word,
        snippets=snippets,
    )


def build_quotient(*, family: str, difficulty: int, var: sp.Symbol, numerator: list[Term], den: sp.Rational,
                   params: Params, **kwargs) -> Built:
    """``(sum of powers) / x^den``, split term by term into single powers."""
    top = _sum(numerator, var)
    bottom = var**den
    expr = top / bottom
    # SymPy keeps a sum over a power as a fraction; make sure it still shows the numerator.
    if not expr.has(top) or len(numerator) < 2:
        raise ValueError("SymPy rewrote the fraction; resample")
    ordered = _terms_of(top, var)
    bottom_tex = tex_power(1, den, var)
    middle = join_terms([
        ("-" if a < 0 else "") + rf"\frac{{{tex(abs(a) * var**m)}}}{{{bottom_tex}}}" for a, m in ordered
    ])
    terms = [(a, m - den) for a, m in ordered]
    return build_power(family=family, difficulty=difficulty, var=var, terms=terms, params=params, expr=expr,
                       form="quotient", middle=middle,
                       extra_parts={"numerator": top, "denominator": bottom}, **kwargs)


def build_product(*, family: str, difficulty: int, var: sp.Symbol, factor: sp.Rational, bracket: list[Term],
                  params: Params, **kwargs) -> Built:
    """``x^factor * (sum of powers)``, multiplied out into single powers."""
    front = var**factor
    inside = _sum(bracket, var)
    expr = front * inside
    if not expr.has(inside) or len(bracket) < 2:
        raise ValueError("SymPy multiplied the product out; resample")
    ordered = _terms_of(inside, var)
    middle = join_terms([
        tex_power(b, factor, var) + ("" if m == 0 else rf" \cdot {tex_power(1, m, var)}") for b, m in ordered
    ])
    terms = [(b, m + factor) for b, m in ordered]
    return build_power(family=family, difficulty=difficulty, var=var, terms=terms, params=params, expr=expr,
                       form="product", middle=middle, extra_parts={"factor": front, "bracket": inside},
                       **kwargs)


# --- families ------------------------------------------------------------------


def _family(id: str, difficulty: int, description: str, sample, build, word: bool = False) -> Family:
    return Family(id=id, difficulty=difficulty, description=description, sample=sample, build=build, word=word)


def _sum_family(id: str, difficulty: int):
    """``build`` for families whose params are just ``{"terms": [[a, n], ...]}``."""
    def build(p: Params) -> Built:
        return build_power(family=id, difficulty=difficulty, var=x, terms=_decode(p["terms"]), params=p)
    return build


def _maybe_constant(rng: Random, terms: list, chance: float = 0.5) -> list:
    if rng.random() < chance:
        terms.append([nonzero_int(rng, -9, 9), 0])
    return terms


# d1 ----------------------------------------------------------------------------

def _sample_single_power(rng: Random) -> Params:
    return {"terms": [[nonzero_int(rng, -9, 9), rng.randint(2, 9)]]}


def _sample_polynomial(rng: Random) -> Params:
    m = rng.randint(2, 5)
    k = rng.randint(1, m - 1)
    return {"terms": [[nonzero_int(rng, -6, 6), m], [nonzero_int(rng, -9, 9), k], [nonzero_int(rng, -9, 9), 0]]}


# d2 ----------------------------------------------------------------------------

def _sample_negative_powers(rng: Random) -> Params:
    terms = [[nonzero_int(rng, -6, 6), rng.randint(1, 4)], [nonzero_int(rng, -8, 8), -rng.randint(1, 3)]]
    return {"terms": _maybe_constant(rng, terms)}


def _sample_square_root(rng: Random) -> Params:
    # An even coefficient on sqrt(x) keeps the key's coefficients whole.
    terms = [[2 * nonzero_int(rng, -5, 5), "1/2"], [nonzero_int(rng, -6, 6), rng.randint(1, 3)]]
    return {"terms": _maybe_constant(rng, terms)}


# d3 ----------------------------------------------------------------------------
# Coefficients are multiples of the exponent's denominator so the key has whole
# coefficients and the difficulty stays in the exponent arithmetic.

_FRACTIONAL = ("3/2", "5/2", "2/3", "4/3", "5/3", "3/4", "1/3")
_NEGATIVE_ROOTS = ("-1/2", "-1/3", "-3/2")
_ROOT_PARTNERS = ("1/2", "1/3", -1, -2, -3)


def _scaled_coefficient(rng: Random, exponent: int | str, k_max: int = 2) -> int:
    return _q(exponent).q * nonzero_int(rng, -k_max, k_max)


def _sample_fractional_exponents(rng: Random) -> Params:
    exps = rng.sample(_FRACTIONAL, 2)
    terms = [[_scaled_coefficient(rng, n), n] for n in exps]
    if rng.random() < 0.4:
        terms.append([nonzero_int(rng, -5, 5), rng.randint(2, 3)])
    return {"terms": terms}


def _sample_root_reciprocals(rng: Random) -> Params:
    exps = [pick(rng, _NEGATIVE_ROOTS), *rng.sample(_ROOT_PARTNERS, rng.randint(1, 2))]
    return {"terms": [[_scaled_coefficient(rng, n, 3 if _q(n).q == 1 else 2), n] for n in exps]}


_RATIONAL_EXPONENTS = (2, 3, 4, 5, 6, -1, -2, -3, "3/2", "4/3", "2/3")


def _sample_rational_coefficients(rng: Random) -> Params:
    # Coefficient m/n on x^n differentiates to m x^(n-1): fractions in the
    # problem, whole numbers in the key.
    while True:
        terms = []
        for n in rng.sample(_RATIONAL_EXPONENTS, rng.randint(2, 3)):
            a = nonzero_int(rng, -4, 4) / _q(n)
            terms.append([str(a), n])
        if sum(1 for a, _ in terms if not _q(a).is_integer) >= 2:
            return {"terms": terms}


# d4: rewrite first ----------------------------------------------------------------

def _sample_split_fraction(rng: Random) -> Params:
    den = rng.randint(1, 3)
    while True:
        exps = sorted(rng.sample(range(den + 4), rng.randint(2, 3)), reverse=True)
        # At least one power above the denominator and one below it, so the
        # rewrite produces both positive and negative exponents.
        if exps[0] > den and exps[-1] < den:
            return {"den": den, "num": [[nonzero_int(rng, -6, 6), m] for m in exps]}


def _build_split_fraction(p: Params) -> Built:
    return build_quotient(family="split_fraction", difficulty=4, var=x, numerator=_decode(p["num"]),
                          den=_q(p["den"]), params=p)


def _sample_split_root_fraction(rng: Random) -> Params:
    root = pick(rng, ["1/2", "1/2", "1/3"])
    exps = sorted(rng.sample([2, 1, 0], rng.randint(2, 3)), reverse=True)
    return {"root": root, "num": [[_q(root).q * nonzero_int(rng, -3, 3), m] for m in exps]}


def _build_split_root_fraction(p: Params) -> Built:
    return build_quotient(family="split_root_fraction", difficulty=4, var=x, numerator=_decode(p["num"]),
                          den=_q(p["root"]), params=p)


def _sample_distribute_power(rng: Random) -> Params:
    factor = pick(rng, ["1/2", "1/2", "1/3", 1, 2])
    while True:
        exps = sorted(rng.sample([2, 1, 0, -1, -2], 2), reverse=True)
        # A negative power inside the bracket is what makes this more than expanding a polynomial.
        if exps[-1] < 0 and not all(m + _q(factor) in (0, 1) for m in exps):
            return {"factor": factor, "bracket": [[nonzero_int(rng, -5, 5), m] for m in exps]}


def _build_distribute_power(p: Params) -> Built:
    return build_product(family="distribute_power", difficulty=4, var=x, factor=_q(p["factor"]),
                         bracket=_decode(p["bracket"]), params=p)


# word problems ------------------------------------------------------------------

_PARTICLE = (
    "A particle moves along a line so that its position after $t$ seconds is $s(t) = {expr}$ meters.",
    "What is its velocity, in m/s, at $t = {t0}$?",
)
_BALL = (
    "A ball is thrown straight up from a balcony. Its height after $t$ seconds is $h(t) = {expr}$ meters.",
    "What is its velocity, in m/s, at $t = {t0}$?",
)


def _sample_word_velocity(rng: Random) -> Params:
    if rng.random() < 0.5:
        while True:
            a, b, c = rng.randint(1, 2), rng.randint(-9, 9), rng.randint(-12, 12)
            d, t0 = rng.randint(0, 20), rng.randint(2, 4)
            # Skip a zero velocity and the one case where dropping the brought-down
            # exponent gives the right number (b = -2 a t0).
            if 3 * a * t0**2 + 2 * b * t0 + c != 0 and b != -2 * a * t0:
                terms = [[coef, n] for coef, n in ((a, 3), (b, 2), (c, 1), (d, 0)) if coef != 0]
                return {"story": "particle", "terms": terms, "t0": t0}
    while True:
        v0, h0, t0 = rng.randint(12, 30), rng.randint(2, 40), rng.randint(2, 4)
        # Still in the air at t0, and not exactly at the top (velocity 0).
        if -5 * t0**2 + v0 * t0 + h0 > 0 and v0 != 10 * t0:
            return {"story": "ball", "terms": [[-5, 2], [v0, 1], [h0, 0]], "t0": t0}


def _build_word_velocity(p: Params) -> Built:
    terms = _decode(p["terms"])
    text, question = _PARTICLE if p["story"] == "particle" else _BALL
    fn = "s" if p["story"] == "particle" else "h"
    word = WordContext(text=text.format(expr=tex(_sum(terms, t))), question=question.format(t0=p["t0"]),
                       unit="m/s")
    return build_power(family="word_velocity", difficulty=2, var=t, terms=terms, params=p, fn=fn, word=word,
                       at={"value": p["t0"]})


# name -> (symbol, function letter, coefficient, exponent, story, question, unit)
_SHAPES: dict[str, tuple] = {
    "sphere_volume": (
        r, "V", sp.Rational(4, 3) * sp.pi, 3,
        "A spherical balloon is being inflated. When its radius is $r$ cm, its volume is $V(r) = {expr}$ cubic cm.",
        r"How fast is the volume changing with respect to the radius, $\frac{{dV}}{{dr}}$, when $r = {x0}$?",
        "cubic cm per cm",
    ),
    "sphere_area": (
        r, "S", 4 * sp.pi, 2,
        "The surface area of a ball of radius $r$ cm is $S(r) = {expr}$ square cm.",
        r"Find $\frac{{dS}}{{dr}}$, the rate the surface area grows as the radius grows, when $r = {x0}$.",
        "square cm per cm",
    ),
    "circle_area": (
        r, "A", sp.pi, 2,
        "An oil spill spreads in a circle. When its radius is $r$ meters it covers $A(r) = {expr}$ square meters.",
        r"How fast does the area change with respect to the radius, $\frac{{dA}}{{dr}}$, when $r = {x0}$?",
        "square m per m",
    ),
    "cube_volume": (
        s, "V", sp.Integer(1), 3,
        "An ice cube has side length $s$ cm, so its volume is $V(s) = {expr}$ cubic cm.",
        r"Find $\frac{{dV}}{{ds}}$, the rate the volume changes with the side length, when $s = {x0}$.",
        "cubic cm per cm",
    ),
}


def _sample_word_geometry(rng: Random) -> Params:
    return {"shape": pick(rng, sorted(_SHAPES)), "x0": rng.randint(2, 6)}


def _build_word_geometry(p: Params) -> Built:
    var, fn, a, n, text, question, unit = _SHAPES[p["shape"]]
    terms = [(a, sp.Integer(n))]
    word = WordContext(text=text.format(expr=tex(_sum(terms, var))), question=question.format(x0=p["x0"]),
                       unit=unit)
    return build_power(family="word_geometry", difficulty=2, var=var, terms=terms, params=p, fn=fn, word=word,
                       at={"value": p["x0"]})


_PLANT = (
    "A sunflower is $h(t) = {expr}$ cm tall $t$ days after it is planted.",
    "How fast is it growing, in cm per day, when $t = {t0}$?",
)


def _sample_word_growth(rng: Random) -> Params:
    # Perfect-square days keep sqrt(t0) whole.
    return {"a": pick(rng, [4, 6, 8, 10, 12]), "b": rng.randint(2, 15), "t0": pick(rng, [4, 9, 16, 25, 36])}


def _build_word_growth(p: Params) -> Built:
    terms = [(sp.Integer(p["a"]), sp.Rational(1, 2)), (sp.Integer(p["b"]), sp.Integer(0))]
    text, question = _PLANT
    word = WordContext(text=text.format(expr=tex(_sum(terms, t))), question=question.format(t0=p["t0"]),
                       unit="cm per day")
    return build_power(family="word_growth", difficulty=3, var=t, terms=terms, params=p, fn="h", word=word,
                       at={"value": p["t0"]})


_AVERAGE_COST = (
    ("A workshop's total cost to build $q$ chairs is $C(q) = {cost}$ dollars, so the average cost per chair "
     "is $A(q) = {expr}$ dollars."),
    "Find $A'({q0})$, the rate at which the average cost per chair is changing when $q = {q0}$.",
)


def _sample_word_average_cost(rng: Random) -> Params:
    while True:
        a, b = rng.randint(1, 4), pick(rng, list(range(20, 85, 5)))
        c, q0 = pick(rng, [200, 300, 400, 500, 600, 800, 900, 1200]), pick(rng, [10, 20, 30])
        if sp.Rational(c, q0**2) != a:  # A'(q0) = a - c/q0^2 would be 0
            return {"a": a, "b": b, "c": c, "q0": q0}


def _build_word_average_cost(p: Params) -> Built:
    numerator = [(sp.Integer(p["a"]), sp.Integer(2)), (sp.Integer(p["b"]), sp.Integer(1)),
                 (sp.Integer(p["c"]), sp.Integer(0))]
    cost = _sum(numerator, q)
    text, question = _AVERAGE_COST
    word = WordContext(text=text.format(cost=tex(cost), expr=tex(cost / q)),
                       question=question.format(q0=p["q0"]), unit="dollars per chair per chair")
    return build_quotient(family="word_average_cost", difficulty=4, var=q, numerator=numerator,
                          den=sp.Integer(1), params=p, fn="A", word=word, at={"value": p["q0"]})


FAMILIES = (
    _family("single_power", 1, "A constant times one power of x, a x^n", _sample_single_power,
            _sum_family("single_power", 1)),
    _family("polynomial", 1, "Two powers of x plus a constant", _sample_polynomial, _sum_family("polynomial", 1)),
    _family("negative_powers", 2, "A power of x plus a/x^k", _sample_negative_powers,
            _sum_family("negative_powers", 2)),
    _family("square_root", 2, "A multiple of sqrt(x) plus a power of x", _sample_square_root,
            _sum_family("square_root", 2)),
    _family("word_velocity", 2, "Velocity at a time from a polynomial position", _sample_word_velocity,
            _build_word_velocity, word=True),
    _family("word_geometry", 2, "Rate of change of a volume or area formula at a given size",
            _sample_word_geometry, _build_word_geometry, word=True),
    _family("fractional_exponents", 3, "Powers like x^(3/2) and x^(2/3), cube roots included",
            _sample_fractional_exponents, _sum_family("fractional_exponents", 3)),
    _family("root_reciprocals", 3, "Reciprocals of roots such as a/sqrt(x), with other roots and 1/x^k",
            _sample_root_reciprocals, _sum_family("root_reciprocals", 3)),
    _family("rational_coefficients", 3, "Fractional coefficients such as x^6/3 and 5/(2x^2)",
            _sample_rational_coefficients, _sum_family("rational_coefficients", 3)),
    _family("word_growth", 3, "Growth rate of a plant with height a sqrt(t) + b", _sample_word_growth,
            _build_word_growth, word=True),
    _family("split_fraction", 4, "A polynomial over x^k, split into powers first", _sample_split_fraction,
            _build_split_fraction),
    _family("split_root_fraction", 4, "A polynomial over sqrt(x) or a cube root, split into powers first",
            _sample_split_root_fraction, _build_split_root_fraction),
    _family("distribute_power", 4, "A power of x times a bracket such as sqrt(x)(x + 1/x), multiplied out first",
            _sample_distribute_power, _build_distribute_power),
    _family("word_average_cost", 4, "Rate of change of an average cost (aq^2 + bq + c)/q at a given q",
            _sample_word_average_cost, _build_word_average_cost, word=True),
)


# --- mistakes ------------------------------------------------------------------


def _terms(b: Built) -> list[Term]:
    return _terms_of(b.parts["power_form"], b.var)


def _with(rule: Rule, applies: Callable[[list[Term]], bool] = lambda terms: True):
    """A buggy answer that applies ``rule`` to every term of the rewritten function."""
    def buggy(b: Built) -> sp.Expr | None:
        terms = _terms(b)
        return _apply(terms, b.var, rule) if applies(terms) else None
    return buggy


def _quotient_ratio(b: Built) -> sp.Expr | None:
    if "numerator" not in b.parts:
        return None
    return _differentiate(b.parts["numerator"], b.var) / _differentiate(b.parts["denominator"], b.var)


def _product_of_derivatives(b: Built) -> sp.Expr | None:
    if "factor" not in b.parts:
        return None
    return _differentiate(b.parts["factor"], b.var) * _differentiate(b.parts["bracket"], b.var)


def _factor_as_constant(b: Built) -> sp.Expr | None:
    # Treated the power in front like a constant multiple and differentiated only the bracket.
    if "factor" not in b.parts:
        return None
    return b.parts["factor"] * _differentiate(b.parts["bracket"], b.var)


def _at(b: Built, expr: sp.Expr | None) -> sp.Expr | None:
    """Mistake answers for 'evaluate at a point' problems are numbers too."""
    if expr is None or b.at is None:
        return expr
    return expr.subs(b.at)


def _pattern(tag: str, step: str, fn, note: str, signature: bool = False) -> MistakePattern:
    return MistakePattern(tag=tag, step=step, buggy=lambda b: _at(b, fn(b)), note=note, signature=signature)


MISTAKES = (
    _pattern(
        "power_exponent_not_reduced", "power_rule", _with(_not_reduced),
        "In the power rule step you brought the exponent down but kept the old power. The exponent also drops "
        "by one, so $[[focus_power:yellow]]$ becomes $[[focus_prime_power:mint]]$.",
        signature=True,
    ),
    _pattern(
        "power_coefficient_dropped", "power_rule", _with(_coefficient_dropped),
        "In the power rule step you lowered the exponent but never multiplied by it. The old exponent comes "
        "down as a factor, so $[[focus_power:yellow]]$ becomes $[[focus_prime_power:mint]]$.",
        signature=True,
    ),
    _pattern(
        "constant_term_kept", "power_rule", _with(_constant_kept, lambda terms: any(n == 0 for _, n in terms)),
        "In the power rule step, the constant $[[constant:yellow]]$ never changes, so its derivative is $0$ "
        "and it drops out of the answer.",
    ),
    _pattern(
        "negative_exponent_slip", "power_rule", _with(_negative_slip, lambda terms: any(n < 0 for _, n in terms)),
        "Recheck the exponent on $[[neg_power:yellow]]$. Lowering a negative exponent by one makes it more "
        "negative, so that term becomes $[[neg_prime_power:mint]]$.",
    ),
    _pattern(
        "negative_exponent_slip", "power_rule",
        _with(_fraction_slip, lambda terms: any(not n.is_integer for _, n in terms)),
        "Recheck the exponent on $[[frac_power:yellow]]$. Take a whole $1$ off the fraction, not $1$ off its "
        "numerator, so that term becomes $[[frac_prime_power:mint]]$.",
    ),
    _pattern(
        "quotient_as_derivative_ratio", "rewrite", _quotient_ratio,
        "Differentiating the top and the bottom separately does not give the derivative of a fraction. Split "
        "it into $[[rewritten]]$ first, then use the power rule on each term.",
    ),
    _pattern(
        "product_of_derivatives", "rewrite", _product_of_derivatives,
        "The derivative of a product is not the product of the derivatives. Multiply it out to "
        "$[[rewritten]]$ first, then use the power rule on each term.",
    ),
    _pattern(
        "product_rule_missing_term", "rewrite", _factor_as_constant,
        "The power in front is not a constant, so it cannot sit outside the derivative. Multiply it into the "
        "bracket to get $[[rewritten]]$, then differentiate each term.",
    ),
)


def _hints(b: Built) -> HintLadder:
    v = tex(b.var)
    form = b.params["form"]
    if b.word is not None:
        nudge = f"Which derivative gives the rate the question asks for, and at what value of ${v}$?"
    else:
        nudge = {
            "poly": "What is the exponent on each term, and what does the power rule do with it?"
                    if len(_terms(b)) > 1 else "What is the exponent, and what does the power rule do with it?",
            "powers": f"Can you write every term, roots and fractions included, as a number times a power of ${v}$?",
            "quotient": "Could you split the fraction into separate terms before you differentiate?",
            "product": "Could you multiply the product out first, so every term is a single power?",
        }[form]

    terms = _terms(b)
    each = " on each term" if len(terms) > 1 else ""
    bigger = (
        rf"Write $[[fx]] = [[rewritten]]$. Then use $\frac{{d}}{{d{v}}}\,{v}^n = n\,{v}^{{n-1}}${each}: "
        "bring the exponent down and lower it by one."
    )
    if any(n == 0 for _, n in terms):
        bigger += " The constant term has derivative $0$."
    if b.at is not None:
        (value,) = b.at.values()
        bigger = f"The rate you want is $[[fprime]]$ at ${v} = {tex(value)}$. {bigger}"
    return HintLadder(nudge=nudge, bigger=bigger, full_step="$[[step:power_rule]]$")


SKILL = SkillSpec(
    id="calc1.derivatives.power_rule",
    slug="power_rule",
    title="Power rule",
    summary="Differentiate sums of powers term by term: bring each exponent down and lower it by one, and "
            "constants go to zero.",
    task="differentiate",
    families=FAMILIES,
    mistakes=MISTAKES,
    hints=_hints,
    formula=FormulaEntry(
        title="Power rule",
        latex=r"\frac{d}{dx}\, x^{n} = n\,x^{n-1}",
        note="Works for any real exponent, including negative and fractional ones. Constant multiples carry "
             "through, sums go term by term, and a constant on its own has derivative 0.",
    ),
    keywords=("power rule", "derivative of x^n", "n x^(n-1)", "constant multiple rule", "sum rule",
              "difference rule", "sum and difference rules", "derivative of a constant",
              "derivative of a polynomial", "differentiating polynomials", "negative exponents",
              "fractional exponents", "rational exponents", "derivative of a square root", "derivative of 1/x",
              "basic differentiation rules", "term by term"),
    prerequisites=(),
)
