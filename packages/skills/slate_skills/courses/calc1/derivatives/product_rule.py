"""Product rule: (fg)' = f'g + fg', and (fgh)' = f'gh + fg'h + fgh' for three factors.

Each family samples integer parameters for two or three factors, multiplies
them, and derives the key the way a student would: differentiate each factor
from a table of basic derivatives, build one term per factor (that factor
differentiated, the others kept), add the terms and tidy up. The verifier then
checks the key against ``sp.diff`` independently.

Every factor is a function of the bare variable, so no family needs the chain
rule. Factors are described by JSON-friendly specs, decoded by :func:`factor_for`.

Parts available to notes and hints:

``f``, ``g``, ``h``                      the factors in the order the student sees them (``h`` only for three)
``f_prime``, ``g_prime``, ``h_prime``    their derivatives
``last`` / ``last_prime``                the last factor and its derivative
``rest`` / ``rest_primes``               the factors after ``f``, and the product of their derivatives
``assembled``                            the sum of the product-rule terms before tidying

Snippets: ``rule`` (the rule in the problem's own letters), ``rest`` (overrides
the part so the factors keep their on-screen order), ``primes_product`` (the
factor derivatives multiplied, coloured), ``last_colored`` (the last factor in
its step colour), and ``power_factor``, ``power_exponent`` and
``power_exponent_step`` for the first power of the variable among the factors
(``k sqrt(t)`` for a factor ``k sqrt(t) + c``). A factor with a negative or
fractional exponent also overrides its ``f``/``f_prime`` entry so it prints as
``x^{-2}`` rather than as a fraction.

For a word problem, a sample where two mistake patterns (or a pattern and the
key) give the same number is rejected, since the grader could not tell which
mistake was made.
"""

from __future__ import annotations

from collections.abc import Callable
from random import Random

import sympy as sp

from ....core.sampling import nonzero_int, pick, poly_coeffs, poly_from
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
TRANSCENDENTAL = ("sin", "cos", "exp", "ln")
PART_NAMES = ("f", "g", "h")
# f and its derivative are yellow, g and its derivative mint. Only two board
# colours exist, so a third factor stays plain.
PART_COLORS = ("yellow", "mint", None)


def _basic(name: str, v: sp.Symbol) -> tuple[sp.Expr, sp.Expr]:
    # Derivatives written the way a textbook table lists them; the verifier's
    # sp.diff oracle is what decides they are right.
    table = {
        "sin": (sp.sin(v), sp.cos(v)),
        "cos": (sp.cos(v), -sp.sin(v)),
        "exp": (sp.exp(v), sp.exp(v)),
        "ln": (sp.log(v), 1 / v),
    }
    return table[name]


def _power_rule_coeffs(coeffs: list[int]) -> list[int]:
    """Coefficients of the derivative of ``poly_from(coeffs)``, one power-rule step per term."""
    degree = len(coeffs) - 1
    return [c * (degree - i) for i, c in enumerate(coeffs[:-1])]


def factor_for(spec: str | list, v: sp.Symbol) -> tuple[sp.Expr, sp.Expr, str]:
    """Decode a factor spec into ``(factor, derivative, kind)``.

    ``"sin"``, ``"cos"``, ``"exp"`` and ``"ln"`` are table functions,
    ``["scale", a, "sin"]`` is ``a sin v`` (any table function),
    ``["poly", [a, b, c]]`` is ``a v^2 + b v + c``, ``["mono", a, n]`` is
    ``a v^n``, ``["pow", a, p, q]`` is ``a v^(p/q)`` and ``["root", k, c]`` is
    ``k sqrt(v) + c``.
    """
    if isinstance(spec, str):
        f, fp = _basic(spec, v)
        return f, fp, spec
    kind = spec[0]
    if kind == "scale":
        f, fp = _basic(spec[2], v)
        return spec[1] * f, spec[1] * fp, spec[2]
    if kind == "poly":
        coeffs = spec[1]
        return poly_from(coeffs, v), poly_from(_power_rule_coeffs(coeffs), v), kind
    if kind == "mono":
        a, n = spec[1], spec[2]
        return a * v**n, a * n * v ** (n - 1), kind
    if kind == "pow":
        a, r = spec[1], sp.Rational(spec[2], spec[3])
        return a * v**r, a * r * v ** (r - 1), kind
    if kind == "root":
        k, c = spec[1], spec[2]
        return k * sp.sqrt(v) + c, sp.Rational(k, 2) / sp.sqrt(v), kind
    raise ValueError(f"unknown factor {spec!r}")


def _kind(spec: str | list) -> str:
    """``"sin"``, ``"poly"``, ``"root"`` and so on; a scaled table function reports its function."""
    if isinstance(spec, str):
        return spec
    return spec[2] if spec[0] == "scale" else spec[0]


def _scale(spec: str | list) -> int:
    """The constant in front of a scaled table function, 1 for anything else."""
    return spec[1] if not isinstance(spec, str) and spec[0] == "scale" else 1


def _exponent(spec: str | list) -> sp.Rational | None:
    """The power-rule exponent of a power factor, or ``None`` for anything else."""
    kind = _kind(spec)
    if kind == "mono":
        return sp.Integer(spec[2])
    if kind == "pow":
        return sp.Rational(spec[2], spec[3])
    if kind == "root":
        return sp.Rational(1, 2)
    return None


# --- LaTeX helpers --------------------------------------------------------


def _exponent_tex(r: sp.Rational) -> str:
    if r.q == 1:
        return str(r.p)
    sign = "-" if r < 0 else ""
    return rf"{sign}\frac{{{abs(r.p)}}}{{{r.q}}}"


def _power_tex(a: sp.Rational, r: sp.Rational, v: sp.Symbol) -> str:
    """``a v^r`` with the exponent written out, so ``x^{-2}`` does not print as ``1/x^2``."""
    if r == 0:
        return tex(a)
    body = tex(v) if r == 1 else rf"{tex(v)}^{{{_exponent_tex(r)}}}"
    if a == 1:
        return body
    if a == -1:
        return "-" + body
    return rf"{tex(a)} {body}"


def _needs_parens(expr: sp.Expr, first: bool) -> bool:
    # Sums always get brackets in a product; a negative factor does unless it
    # opens the whole line.
    return expr.is_Add or (not first and expr.could_extract_minus_sign())


def _piece(latex: str, expr: sp.Expr, color: str | None, first: bool) -> str:
    if _needs_parens(expr, first):
        latex = rf"\left({latex}\right)"
    return highlight(latex, color) if color else latex


def _product_tex(pieces: list[tuple[str, sp.Expr, str | None]], *, first: bool) -> str:
    return r" \cdot ".join(_piece(lt, e, c, first and i == 0) for i, (lt, e, c) in enumerate(pieces))


# --- builder --------------------------------------------------------------


def _display_order(expr: sp.Expr, decoded: list[tuple]) -> list[tuple]:
    """Sort factors the way SymPy prints ``expr`` so ``f`` is the left factor on screen.

    Each factor (less its numeric coefficient) must survive as its own factor
    of ``expr``. If SymPy merged two factors, for example ``x^2 sqrt(x)`` into
    ``x^(5/2)``, the parts would no longer match what the student sees, so the
    sample is rejected.
    """
    shown = list(expr.as_ordered_factors())

    def position(item: tuple) -> int:
        core = item[0].as_coeff_Mul()[1]
        if core not in shown:
            raise ValueError("SymPy merged or rewrote a factor; resample")
        return shown.index(core)

    return sorted(decoded, key=position)


def _in_display_order(specs: list, v: sp.Symbol) -> list:
    """``specs`` sorted the way SymPy prints the product of their factors."""
    decoded = [(*factor_for(s, v), s) for s in specs]
    return [d[3] for d in _display_order(sp.Mul(*[d[0] for d in decoded]), decoded)]


TIDY: dict[str, Callable[[sp.Expr, sp.Symbol], sp.Expr]] = {
    # Nothing to combine: the terms are already as simple as they get.
    "none": lambda e, v: e,
    # Polynomial factors only: multiply out and collect like terms.
    "expand": lambda e, v: sp.expand(e),
    # Pull out what every term shares, such as e^x.
    "factor": lambda e, v: sp.factor_terms(e),
    # Polynomial times e^x: one polynomial in front of e^x, common factors pulled out.
    "exp": lambda e, v: sp.factor_terms(sp.collect(sp.expand(e), sp.exp(v))),
    # Over one denominator, for square roots and negative or fractional powers.
    "together": lambda e, v: sp.factor_terms(sp.together(e)),
    # Multiply out the polynomial parts and group them by trig and log factors.
    "collect": lambda e, v: sp.collect(sp.expand(e), [sp.sin(v), sp.cos(v), sp.log(v)]),
    # As collect, then pull out common factors (three-factor products).
    "grouped": lambda e, v: sp.factor_terms(sp.collect(sp.expand(e), [sp.sin(v), sp.cos(v), sp.log(v)])),
}


def _terms(fs: list[sp.Expr], ds: list[sp.Expr], which: range | list[int] | None = None) -> sp.Expr:
    """Sum of the product-rule terms: in term ``i`` factor ``i`` is differentiated, the rest are kept."""
    n = len(fs)
    idx = range(n) if which is None else which
    return sp.Add(*[sp.Mul(*[ds[j] if j == i else fs[j] for j in range(n)]) for i in idx])


def build_product(*, family: str, difficulty: int, var: sp.Symbol, specs: list, params: Params,
                  tidy: str = "none", names: list[str] | None = None, fn: str = "y", keep_order: bool = False,
                  word: WordContext | None = None, at: dict | None = None) -> Built:
    """Multiply the factors in ``specs`` and walk the product rule.

    The factor specs in the order the student sees them go into
    ``params["shown"]`` and the letters used for them into ``params["names"]``,
    so mistake patterns and hints can reason about the structure without
    knowing the family. ``keep_order`` keeps ``specs`` in the given order (word
    problems and families whose prompt is written out by hand).
    """
    decoded = [(*factor_for(s, var), s) for s in specs]
    expr = sp.Mul(*[d[0] for d in decoded])
    ordered = _display_order(expr, decoded)
    if not keep_order:
        decoded = ordered

    n = len(decoded)
    names = list(names or PART_NAMES[:n])
    fs = [d[0] for d in decoded]
    ds = [d[1] for d in decoded]
    kinds = [d[2] for d in decoded]
    shown = [d[3] for d in decoded]
    params = {**params, "shown": shown, "names": names}

    assembled = _terms(fs, ds)
    key = TIDY[tidy](assembled, var)

    # LaTeX for each factor and derivative. Power factors are written out by
    # hand so a negative exponent stays an exponent.
    f_tex, d_tex = [], []
    for f, fp, kind, spec in decoded:
        if kind == "pow":
            a, r = sp.Integer(spec[1]), sp.Rational(spec[2], spec[3])
            f_tex.append(_power_tex(a, r, var))
            d_tex.append(_power_tex(a * r, r - 1, var))
        else:
            f_tex.append(tex(f))
            d_tex.append(tex(fp))

    parts: dict[str, sp.Expr] = {
        "last": fs[-1],
        "last_prime": ds[-1],
        "rest": sp.Mul(*fs[1:]),
        "rest_primes": sp.Mul(*ds[1:]),
        "assembled": assembled,
    }
    snippets: dict[str, str] = {}
    for i in range(n):
        parts[PART_NAMES[i]] = fs[i]
        parts[f"{PART_NAMES[i]}_prime"] = ds[i]
        if kinds[i] == "pow":
            snippets[PART_NAMES[i]] = f_tex[i]
            snippets[f"{PART_NAMES[i]}_prime"] = d_tex[i]

    colors = PART_COLORS[:n]
    fac = [(f_tex[i], fs[i], colors[i]) for i in range(n)]
    der = [(d_tex[i], ds[i], colors[i]) for i in range(n)]
    term_tex = [_product_tex([der[j] if j == i else fac[j] for j in range(n)], first=i == 0) for i in range(n)]
    rule = " + ".join(" ".join(nm + ("'" if j == i else "") for j, nm in enumerate(names)) for i in range(n))

    power_idx = next((i for i, s in enumerate(shown) if _exponent(s) is not None), 0)
    r = _exponent(shown[power_idx])
    power_factor = f_tex[power_idx]
    if _kind(shown[power_idx]) == "root":
        # Point at k sqrt(t) itself, not at k sqrt(t) + c.
        power_factor = tex(shown[power_idx][1] * sp.sqrt(var))
    snippets.update({
        "rule": rule,
        # The factors after f in the order the student sees them (SymPy would reorder the product).
        "rest": " ".join(_piece(f_tex[i], fs[i], None, i == 1) for i in range(1, n)),
        "primes_product": _product_tex(der, first=True),
        "last_colored": highlight(f_tex[-1], colors[-1]) if colors[-1] else f_tex[-1],
        "power_factor": power_factor,
        "power_exponent": _exponent_tex(r) if r is not None else "n",
        "power_exponent_step": (
            rf"{_exponent_tex(r)} - 1 = {_exponent_tex(r - 1)}" if r is not None else "n - 1"
        ),
    })

    v = tex(var)
    lhs = rf"\frac{{d{fn}}}{{d{v}}}" if at is None else rf"{fn}'({v})"
    count = "two" if n == 2 else "three"
    steps = [
        Step(
            id="identify",
            title=f"Name the {count} factors",
            latex=r",\quad ".join(
                f"{nm}({v}) = {highlight(f_tex[i], colors[i]) if colors[i] else f_tex[i]}"
                for i, nm in enumerate(names)
            ),
        ),
        Step(
            id="differentiate",
            title="Differentiate each factor",
            latex=r",\quad ".join(
                f"{nm}'({v}) = {highlight(d_tex[i], colors[i]) if colors[i] else d_tex[i]}"
                for i, nm in enumerate(names)
            ),
        ),
        Step(
            id="assemble",
            title="Apply the product rule",
            latex=rf"{lhs} = {rule} = " + " + ".join(term_tex),
            expr=assembled,
        ),
    ]

    key_out = key
    point = None
    if at is None:
        steps.append(Step(id="simplify", title="Simplify", latex=rf"{lhs} = {tex(key)}", expr=key))
    else:
        t0 = sp.Rational(at["value"])
        point = {var: t0}
        fv = [f.subs(point) for f in fs]
        dv = [d.subs(point) for d in ds]
        key_out = _terms(fv, dv)
        if key_out == 0:
            raise ValueError("a zero rate makes a poor question; resample")
        fac_v = [(tex(fv[i]), fv[i], colors[i]) for i in range(n)]
        der_v = [(tex(dv[i]), dv[i], colors[i]) for i in range(n)]
        num_tex = " + ".join(
            _product_tex([der_v[j] if j == i else fac_v[j] for j in range(n)], first=i == 0) for i in range(n)
        )
        steps.append(Step(
            id="evaluate",
            title=f"Evaluate at ${v} = {tex(t0)}$",
            latex=rf"{fn}'({tex(t0)}) = {num_tex} = {tex(key_out)}",
            expr=key_out,
        ))

    if word is not None:
        prompt = f"{word.text} {word.question}"
    else:
        shown_tex = " ".join(f_tex) if keep_order else tex(expr)
        prompt = rf"Differentiate ${fn} = {shown_tex}$."

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
        # A point answer is one number, so two mistakes easily land on the same
        # value (w'h = wh' at t0, say). The grader would then name the wrong one.
        wrong = [w for w in (m.buggy(built) for m in MISTAKES) if w is not None]
        if len(set(wrong)) < len(wrong) or key_out in wrong:
            raise ValueError("two mistakes give the same number here; resample")
    return built


# --- families -------------------------------------------------------------


def _family(id: str, difficulty: int, description: str, sample, build, word: bool = False) -> Family:
    return Family(id=id, difficulty=difficulty, description=description, sample=sample, build=build, word=word)


# d1 ----------------------------------------------------------------------

def _sample_mono_trig(rng: Random) -> Params:
    return {"a": nonzero_int(rng, -5, 5), "n": rng.randint(1, 4), "trig": pick(rng, TRIG)}


def _build_mono_trig(p: Params) -> Built:
    return build_product(family="mono_trig", difficulty=1, var=x, specs=[["mono", p["a"], p["n"]], p["trig"]],
                         params=p, tidy="collect")


def _sample_mono_exp(rng: Random) -> Params:
    return {"a": nonzero_int(rng, -5, 5), "n": rng.randint(1, 4)}


def _build_mono_exp(p: Params) -> Built:
    return build_product(family="mono_exp", difficulty=1, var=x, specs=[["mono", p["a"], p["n"]], "exp"],
                         params=p, tidy="exp")


def _sample_two_linear(rng: Random) -> Params:
    # Proportional factors would make a square (or a multiple of one), not a
    # product of two. And when ac = ad - bc, multiplying the derivatives and
    # subtracting the terms give the same number, so the two mistakes blur.
    while True:
        a, b = nonzero_int(rng, -4, 4), nonzero_int(rng, -7, 7)
        c, d = rng.randint(1, 5), nonzero_int(rng, -7, 7)
        if a * d != b * c and a * c != a * d - b * c:
            return {"f": [a, b], "g": [c, d]}


def _build_two_linear(p: Params) -> Built:
    return build_product(family="two_linear", difficulty=1, var=x, specs=[["poly", p["f"]], ["poly", p["g"]]],
                         params=p, tidy="expand")


# d2 ----------------------------------------------------------------------

def _sample_poly_trig(rng: Random) -> Params:
    return {"poly": poly_coeffs(rng, 2, lo=-5, hi=5), "trig": pick(rng, TRIG)}


def _build_poly_trig(p: Params) -> Built:
    return build_product(family="poly_trig", difficulty=2, var=x, specs=[["poly", p["poly"]], p["trig"]],
                         params=p, tidy="collect")


def _sample_poly_exp(rng: Random) -> Params:
    return {"poly": poly_coeffs(rng, 2, lo=-5, hi=5)}


def _build_poly_exp(p: Params) -> Built:
    return build_product(family="poly_exp", difficulty=2, var=x, specs=[["poly", p["poly"]], "exp"], params=p,
                         tidy="exp")


def _sample_poly_ln(rng: Random) -> Params:
    # No constant term, so f times 1/x divides out to a polynomial.
    lead, other = nonzero_int(rng, -4, 4), nonzero_int(rng, -6, 6)
    if rng.random() < 0.6:
        return {"poly": [lead, other, 0]}
    return pick(rng, [{"poly": [lead, other, 0, 0]}, {"poly": [lead, 0, other, 0]}])


def _build_poly_ln(p: Params) -> Built:
    return build_product(family="poly_ln", difficulty=2, var=x, specs=[["poly", p["poly"]], "ln"], params=p,
                         tidy="collect")


# d3 ----------------------------------------------------------------------

def _sample_poly_ln_const(rng: Random) -> Params:
    # A constant term leaves a 1/x behind after simplifying.
    a = rng.randint(1, 4)
    b = pick(rng, [0, 0, *range(-4, 5)])
    c = nonzero_int(rng, -6, 6)
    return {"poly": [a, b, c]}


def _build_poly_ln_const(p: Params) -> Built:
    return build_product(family="poly_ln_const", difficulty=3, var=x, specs=[["poly", p["poly"]], "ln"],
                         params=p, tidy="collect")


def _sample_linear_sqrt(rng: Random) -> Params:
    # b != 0 keeps (ax+b) a sum; a x sqrt(x) would merge into a single power.
    return {"a": nonzero_int(rng, -4, 5), "b": nonzero_int(rng, -6, 6)}


def _build_linear_sqrt(p: Params) -> Built:
    return build_product(family="linear_sqrt", difficulty=3, var=x, specs=[["poly", [p["a"], p["b"]]], ["root", 1, 0]],
                         params=p, tidy="together")


def _sample_sqrt_transcendental(rng: Random) -> Params:
    return {"k": pick(rng, [1, 1, 2, 3, 4, 5, -1, -2, -3]), "other": pick(rng, TRANSCENDENTAL)}


def _build_sqrt_transcendental(p: Params) -> Built:
    return build_product(family="sqrt_transcendental", difficulty=3, var=x, specs=[["root", p["k"], 0], p["other"]],
                         params=p, tidy="together")


def _sample_transcendental_pair(rng: Random) -> Params:
    # Only six pairs exist, so a constant in front keeps repeats rare.
    first = pick(rng, TRANSCENDENTAL)
    second = pick(rng, [k for k in TRANSCENDENTAL if k != first])
    return {"a": pick(rng, [1, 1, 1, 2, 3, 4, 5, -1, -2, -3]), "pair": [first, second]}


def _build_transcendental_pair(p: Params) -> Built:
    # The constant belongs to whichever function SymPy prints first, so f is
    # "3 e^x" in "3 e^x sin x" rather than g being "3 sin x".
    first, second = _in_display_order(p["pair"], x)
    a = p.get("a", 1)
    specs = [first if a == 1 else ["scale", a, first], second]
    return build_product(family="transcendental_pair", difficulty=3, var=x, specs=specs, params=p, tidy="factor")


# d4 ----------------------------------------------------------------------

def _sample_triple(rng: Random) -> Params:
    first = pick(rng, TRANSCENDENTAL)
    second = pick(rng, [k for k in TRANSCENDENTAL if k != first])
    return {"a": nonzero_int(rng, -3, 4), "n": rng.randint(1, 3), "pair": [first, second]}


def _build_triple(p: Params) -> Built:
    specs = [["mono", p["a"], p["n"]], *p["pair"]]
    return build_product(family="triple", difficulty=4, var=x, specs=specs, params=p, tidy="grouped")


# Exponents for the power factor: negative integers, and fractions other than 1/2
# (sqrt(x) is the d3 case).
POWERS = ([-1, 1], [-2, 1], [-3, 1], [-1, 2], [3, 2], [5, 2], [1, 3], [2, 3], [4, 3])


def _sample_power_transcendental(rng: Random) -> Params:
    return {"a": pick(rng, [1, 1, 2, 3, 4, -1, -2]), "r": list(pick(rng, POWERS)), "other": pick(rng, TRANSCENDENTAL)}


def _build_power_transcendental(p: Params) -> Built:
    # SymPy prints x^(-2) e^x as a fraction, so the prompt is written out by hand
    # with the power factor first.
    num, den = p["r"]
    return build_product(family="power_transcendental", difficulty=4, var=x,
                         specs=[["pow", p["a"], num, den], p["other"]], params=p, tidy="together",
                         keep_order=True)


# word problems -------------------------------------------------------------

_RECTANGLE = (
    ("A rectangle is changing shape. After $t$ seconds its width is $w(t) = {w}$ cm and its height is "
     "$h(t) = {h}$ cm, so its area is $A(t) = w(t)\\,h(t)$."),
    "How fast is the area changing, in cm²/s, at $t = {t0}$?",
)
_REVENUE = (
    ("A theater lowers its ticket price a little each week to fill more seats. After $t$ weeks a ticket "
     "costs $p(t) = {p}$ dollars and $q(t) = {q}$ people come to each show, so the revenue from one show "
     "is $R(t) = p(t)\\,q(t)$ dollars."),
    "At what rate is the revenue from one show changing at $t = {t0}$, in dollars per week?",
)
_BOX = (
    ("A rectangular box is expanding. After $t$ seconds its length, width and height are "
     "$\\ell(t) = {l}$, $w(t) = {w}$ and $h(t) = {h}$ cm, so its volume is $V(t) = \\ell(t)\\,w(t)\\,h(t)$."),
    "How fast is the volume increasing, in cm³/s, at $t = {t0}$?",
)


def _sample_word_rectangle(rng: Random) -> Params:
    t0 = rng.randint(1, 4)
    a, b = rng.randint(1, 4), rng.randint(1, 9)
    if rng.random() < 0.5:
        # Height grows quadratically.
        return {"w": [a, b], "h": [rng.randint(1, 3), 0, rng.randint(1, 9)], "t0": t0}
    # Height shrinks linearly but stays positive past t0.
    c = rng.randint(1, 3)
    return {"w": [a, b], "h": [-c, c * t0 + rng.randint(2, 8)], "t0": t0}


def _build_word_rectangle(p: Params) -> Built:
    w, h = poly_from(p["w"], t), poly_from(p["h"], t)
    text, question = _RECTANGLE
    word = WordContext(text=text.format(w=tex(w), h=tex(h)), question=question.format(t0=p["t0"]), unit="cm²/s")
    return build_product(family="word_rectangle", difficulty=2, var=t, specs=[["poly", p["w"]], ["poly", p["h"]]],
                         params=p, names=["w", "h"], fn="A", keep_order=True, word=word, at={"value": p["t0"]})


def _sample_word_revenue(rng: Random) -> Params:
    # t0 is a perfect square and k a multiple of 2 sqrt(t0), so every value is a
    # whole number. The ticket still costs 5 to 30 dollars at t0.
    s = rng.randint(1, 3)
    t0 = s * s
    b = rng.randint(1, 3)
    a = b * t0 + rng.randint(5, 30)
    k = 2 * s * rng.randint(1, 3)
    c = 10 * rng.randint(2, 9)
    return {"price": [-b, a], "sales": [k, c], "t0": t0}


def _build_word_revenue(p: Params) -> Built:
    price = poly_from(p["price"], t)
    sales = p["sales"][0] * sp.sqrt(t) + p["sales"][1]
    text, question = _REVENUE
    word = WordContext(text=text.format(p=tex(price), q=tex(sales)), question=question.format(t0=p["t0"]),
                       unit="dollars per week")
    return build_product(family="word_revenue", difficulty=3, var=t,
                         specs=[["poly", p["price"]], ["root", *p["sales"]]], params=p, names=["p", "q"], fn="R",
                         keep_order=True, word=word, at={"value": p["t0"]})


def _sample_word_box(rng: Random) -> Params:
    # No two sides proportional (t + 2 and 2t + 4): their terms would be equal,
    # so leaving out either one would give the same wrong number.
    while True:
        dims = [[rng.randint(1, 3), rng.randint(1, 8)] for _ in range(3)]
        if all(a * d != b * c for i, (a, b) in enumerate(dims) for c, d in dims[i + 1:]):
            return {"dims": dims, "t0": rng.randint(1, 3)}


def _build_word_box(p: Params) -> Built:
    l, w, h = (poly_from(d, t) for d in p["dims"])
    text, question = _BOX
    word = WordContext(text=text.format(l=tex(l), w=tex(w), h=tex(h)), question=question.format(t0=p["t0"]),
                       unit="cm³/s")
    return build_product(family="word_box", difficulty=4, var=t, specs=[["poly", d] for d in p["dims"]], params=p,
                         names=[r"\ell", "w", "h"], fn="V", keep_order=True, word=word, at={"value": p["t0"]})


FAMILIES = (
    _family("mono_trig", 1, "Monomial times sin or cos", _sample_mono_trig, _build_mono_trig),
    _family("mono_exp", 1, "Monomial times e^x", _sample_mono_exp, _build_mono_exp),
    _family("two_linear", 1, "Product of two linear factors", _sample_two_linear, _build_two_linear),
    _family("poly_trig", 2, "Quadratic times sin or cos", _sample_poly_trig, _build_poly_trig),
    _family("poly_exp", 2, "Quadratic times e^x", _sample_poly_exp, _build_poly_exp),
    _family("poly_ln", 2, "Polynomial with no constant term times ln x", _sample_poly_ln, _build_poly_ln),
    _family("word_rectangle", 2, "Rate of change of a rectangle's area at a time", _sample_word_rectangle,
            _build_word_rectangle, word=True),
    _family("poly_ln_const", 3, "Quadratic with a constant term times ln x", _sample_poly_ln_const,
            _build_poly_ln_const),
    _family("linear_sqrt", 3, "Linear factor times sqrt(x)", _sample_linear_sqrt, _build_linear_sqrt),
    _family("sqrt_transcendental", 3, "Multiple of sqrt(x) times sin, cos, e^x or ln x",
            _sample_sqrt_transcendental, _build_sqrt_transcendental),
    _family("transcendental_pair", 3, "Two of sin, cos, e^x and ln x, often with a constant in front",
            _sample_transcendental_pair, _build_transcendental_pair),
    _family("word_revenue", 3, "Rate of change of revenue, ticket price times attendance, at a time",
            _sample_word_revenue, _build_word_revenue, word=True),
    _family("triple", 4, "Monomial times two of sin, cos, e^x and ln x", _sample_triple, _build_triple),
    _family("power_transcendental", 4, "Negative or fractional power of x times sin, cos, e^x or ln x",
            _sample_power_transcendental, _build_power_transcendental),
    _family("word_box", 4, "Rate of change of a box's volume, three changing sides", _sample_word_box,
            _build_word_box, word=True),
)


# --- mistakes -------------------------------------------------------------


def _shown(b: Built) -> list:
    return b.params["shown"]


def _kinds(b: Built) -> list[str]:
    return [_kind(s) for s in _shown(b)]


def _factors(b: Built) -> tuple[list[sp.Expr], list[sp.Expr]]:
    names = PART_NAMES[:len(_shown(b))]
    return [b.parts[k] for k in names], [b.parts[f"{k}_prime"] for k in names]


def _with_derivative(b: Built, i: int | None, wrong: sp.Expr) -> sp.Expr | None:
    """The product rule done right except that factor ``i`` gets the derivative ``wrong``."""
    if i is None:
        return None
    fs, ds = _factors(b)
    ds = [*ds[:i], wrong, *ds[i + 1:]]
    return _terms(fs, ds)


def _index_of(b: Built, *kinds: str) -> int | None:
    """Position of the first factor whose kind is listed, trying ``kinds`` in order."""
    shown = _kinds(b)
    for kind in kinds:
        if kind in shown:
            return shown.index(kind)
    return None


def _product_of_derivatives(b: Built) -> sp.Expr:
    return sp.Mul(*_factors(b)[1])


def _drop_last_term(b: Built) -> sp.Expr | None:
    # Two factors: kept only f'g. Three: forgot the term where h is differentiated.
    fs, ds = _factors(b)
    wrong = _terms(fs, ds, range(len(fs) - 1))
    # With g = e^x, f'g is the same answer as f'g'; leave that to the signature pattern.
    return None if wrong == _product_of_derivatives(b) else wrong


def _drop_first_term(b: Built) -> sp.Expr | None:
    # Two factors: kept only fg'. Three: forgot the term where f is differentiated.
    fs, ds = _factors(b)
    wrong = _terms(fs, ds, range(1, len(fs)))
    return None if wrong == _product_of_derivatives(b) else wrong


def _drop_middle_term(b: Built) -> sp.Expr | None:
    # Three factors only: wrote f'gh + fgh' and forgot fg'h.
    fs, ds = _factors(b)
    if len(fs) != 3:
        return None
    return _terms(fs, ds, [0, 2])


def _grouped_product_of_derivatives(b: Built) -> sp.Expr | None:
    # (f (gh))' = f' gh + f (gh)', with (gh)' taken as g'h'.
    fs, ds = _factors(b)
    if len(fs) != 3:
        return None
    # With e^x as g or h, g'h' is gh' or g'h, so the answer is just a dropped
    # term and the missing-term patterns explain it better.
    if "exp" in _kinds(b)[1:]:
        return None
    return ds[0] * fs[1] * fs[2] + fs[0] * ds[1] * ds[2]


def _trig_flip_index(b: Built) -> int | None:
    # d/dx cos x = sin x is the usual slip, so flip cos when there is one.
    return _index_of(b, "cos", "sin")


def _trig_sign(b: Built) -> sp.Expr | None:
    i = _trig_flip_index(b)
    return None if i is None else _with_derivative(b, i, -_factors(b)[1][i])


def _subtracted_terms(b: Built) -> sp.Expr | None:
    fs, ds = _factors(b)
    if len(fs) != 2:
        return None
    # Subtracting fg' is the same as flipping the sign of g' when g is the trig
    # factor; the trig pattern explains that case better.
    if _trig_flip_index(b) == 1:
        return None
    return ds[0] * fs[1] - fs[0] * ds[1]


def _ln_derivative_one(b: Built) -> sp.Expr | None:
    i = _index_of(b, "ln")
    return None if i is None else _with_derivative(b, i, _scale(_shown(b)[i]) * sp.Integer(1))


def _exp_as_power(b: Built) -> sp.Expr | None:
    # d/dx e^x written as x e^(x - 1), as if e^x were x^n.
    i = _index_of(b, "exp")
    return None if i is None else _with_derivative(b, i, _scale(_shown(b)[i]) * b.var * sp.exp(b.var - 1))


def _power_index(b: Built) -> int | None:
    for i, spec in enumerate(_shown(b)):
        if _exponent(spec) is not None:
            return i
    return None


def _power_coefficient_dropped(b: Built) -> sp.Expr | None:
    # Lowered the exponent but never multiplied by it: d/dx sqrt(x) = 1/sqrt(x).
    i = _power_index(b)
    if i is None:
        return None
    r = _exponent(_shown(b)[i])
    if r == 1:
        return None
    return _with_derivative(b, i, _factors(b)[1][i] / r)


def _negative_exponent_slip(b: Built) -> sp.Expr | None:
    i = _index_of(b, "pow")
    if i is None:
        return None
    spec = _shown(b)[i]
    a, p, q = spec[1], spec[2], spec[3]
    r = sp.Rational(p, q)
    v = b.var
    if r > 0 and q == 1:
        return None  # a positive whole exponent has no slip of this kind
    if r < 0:
        # Moved the exponent towards zero: x^-2 -> -2 x^-1.
        wrong = a * r * v ** (r + 1)
    else:
        # Took one off the numerator only: x^(3/2) -> (3/2) x^(2/2).
        wrong = a * r * v ** sp.Rational(p - 1, q)
    return _with_derivative(b, i, wrong)


def _at(b: Built, expr: sp.Expr | None) -> sp.Expr | None:
    """Mistake answers for 'evaluate at a point' problems are numbers too."""
    if expr is None or b.at is None:
        return expr
    return expr.subs(b.at)


def _pattern(tag: str, step: str, fn, note: str, signature: bool = False) -> MistakePattern:
    return MistakePattern(tag=tag, step=step, buggy=lambda b: _at(b, fn(b)), note=note, signature=signature)


MISTAKES = (
    _pattern(
        "product_of_derivatives", "assemble", _product_of_derivatives,
        "Check how you combined the derivatives. Multiplying them, $[[primes_product]]$, is not the product "
        "rule: each term differentiates one factor and keeps the rest, $[[rule]]$.",
        signature=True,
    ),
    _pattern(
        "product_rule_missing_term", "assemble", _drop_last_term,
        "Your answer is missing the term where $[[last_colored]]$ is differentiated and everything else is "
        "kept. The product rule needs one term for each factor.",
    ),
    _pattern(
        "product_rule_missing_term", "assemble", _drop_first_term,
        "Your answer is missing the term where $[[f:yellow]]$ is differentiated and everything else is "
        "kept. The product rule needs one term for each factor.",
    ),
    _pattern(
        "product_rule_missing_term", "assemble", _drop_middle_term,
        "Your answer is missing the term where $[[g:mint]]$ is differentiated and everything else is "
        "kept. With three factors the product rule has three terms.",
    ),
    _pattern(
        "product_of_derivatives", "assemble", _grouped_product_of_derivatives,
        "Treating $[[rest]]$ as one factor is fine, but its derivative needs the product rule too. "
        "You multiplied the two derivatives instead and got $[[rest_primes]]$.",
    ),
    _pattern(
        "sign_error", "assemble", _subtracted_terms,
        "Check the sign between the two terms. The product rule adds them, $[[rule]]$; subtracting is the "
        "quotient rule's pattern.",
    ),
    _pattern(
        "trig_derivative_sign", "differentiate", _trig_sign,
        "Recheck the sign of the trig derivative: $\\frac{d}{dx}\\sin x = \\cos x$ but "
        "$\\frac{d}{dx}\\cos x = -\\sin x$.",
    ),
    _pattern(
        "exp_log_derivative_error", "differentiate", _ln_derivative_one,
        "Recheck the derivative of $\\ln x$. It is $\\frac{1}{x}$, not $1$.",
    ),
    _pattern(
        "exp_log_derivative_error", "differentiate", _exp_as_power,
        "The factor $e^x$ is not a power of $x$, so the power rule does not apply to it. Its derivative is "
        "$e^x$ itself.",
    ),
    _pattern(
        "power_coefficient_dropped", "differentiate", _power_coefficient_dropped,
        "Recheck the derivative of $[[power_factor]]$. The power rule multiplies by the old exponent, "
        "$[[power_exponent]]$, as well as lowering it by one.",
    ),
    _pattern(
        "negative_exponent_slip", "differentiate", _negative_exponent_slip,
        "Recheck the new exponent in the derivative of $[[power_factor]]$. The power rule subtracts exactly "
        "one: $[[power_exponent_step]]$.",
    ),
)


WORD_QUANTITY = {"word_rectangle": "area", "word_revenue": "revenue", "word_box": "volume"}


def _hints(b: Built) -> HintLadder:
    names = b.params["names"]
    kinds = _kinds(b)
    if b.family in WORD_QUANTITY:
        nudge = (f"The {WORD_QUANTITY[b.family]} is a product of quantities that change with time. "
                 "How do you differentiate a product?")
    elif len(names) == 3:
        nudge = ("This is a product of three functions. "
                 "What happens to the product rule when there is a third factor?")
    else:
        nudge = ("This is a product of two functions. "
                 "Which two factors are multiplied, and can you differentiate each one?")

    letters = [f"${nm} = [[{PART_NAMES[i]}{':' + PART_COLORS[i] if PART_COLORS[i] else ''}]]$"
               for i, nm in enumerate(names)]
    named = ", ".join(letters[:-1]) + " and " + letters[-1]
    rule = " + ".join(" ".join(nm + ("'" if j == i else "") for j, nm in enumerate(names)) for i in range(len(names)))
    if len(names) == 3:
        bigger = (f"Let {named}. With three factors the product rule has three terms, one for each factor you "
                  f"differentiate: ${rule}$.")
    else:
        bigger = f"Let {named}. The product rule gives ${rule}$, so find the derivative of each factor first."
    if "pow" in kinds:
        bigger += " Use the power rule on the power of $x$, even though the exponent is negative or a fraction."
    if b.at is not None:
        (value,) = b.at.values()
        bigger += f" Then substitute $t = {tex(value)}$."
    return HintLadder(nudge=nudge, bigger=bigger, full_step="$[[step:assemble]]$")


SKILL = SkillSpec(
    id="calc1.derivatives.product_rule",
    slug="product_rule",
    title="Product rule",
    summary="Differentiate a product: differentiate one factor at a time, keep the others, and add the terms.",
    task="differentiate",
    families=FAMILIES,
    mistakes=MISTAKES,
    hints=_hints,
    formula=FormulaEntry(
        title="Product rule",
        latex=r"\frac{d}{dx}\big[f(x)\,g(x)\big] = f'(x)\,g(x) + f(x)\,g'(x)",
        note="Differentiate one factor and keep the other, then swap and add. Three factors give three terms: "
             "$(fgh)' = f'gh + fg'h + fgh'$.",
    ),
    keywords=("product rule", "derivative of a product", "product of two functions", "differentiating products",
              "f'g + fg'", "u'v + uv'", "derivative of the first times the second",
              "first times the derivative of the second", "product rule for three functions"),
    prerequisites=("calc1.derivatives.power_rule",),
)
