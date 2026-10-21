"""Chain rule: d/dx f(g(x)) = f'(g(x)) g'(x).

This is the reference skill file. Each family samples integer parameters,
builds the composition layer by layer, and derives the key by multiplying the
layer derivatives, the way a student would. The verifier then checks the key
against ``sp.diff`` independently.

Parts available to notes and hints:

``outer``                  outermost function written in ``u``
``outer_prime``            its derivative in ``u``
``inside``                 everything inside the outer function, in ``x``
``inside_prime``           d/dx of ``inside`` (itself a chain for nested problems)
``outer_prime_at_inside``  the outer derivative evaluated at the inside
``innermost`` / ``innermost_prime``   the deepest layer and its derivative

Snippets: ``expr_colored`` (outer in mint, inside in yellow).
"""

from __future__ import annotations

from random import Random

import sympy as sp

from ....core.sampling import nonzero_int, pick, poly_coeffs, poly_from
from ....core.text import highlight, tex, tex_compose
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

x, t, u = sp.symbols("x t u")

# name -> (f(u), f'(u)). Derivatives are written the way a textbook table lists
# them; the verifier's sp.diff oracle is what decides they are right.
OUTERS: dict[str, tuple[sp.Expr, sp.Expr]] = {
    "sin": (sp.sin(u), sp.cos(u)),
    "cos": (sp.cos(u), -sp.sin(u)),
    "tan": (sp.tan(u), sp.sec(u) ** 2),
    "exp": (sp.exp(u), sp.exp(u)),
    "ln": (sp.log(u), 1 / u),
    "sqrt": (sp.sqrt(u), 1 / (2 * sp.sqrt(u))),
}
TRIG_SIGN_OUTERS = ("sin", "cos")


def power_outer(n: sp.Rational | int) -> tuple[sp.Expr, sp.Expr]:
    n = sp.Rational(n)
    return u**n, n * u ** (n - 1)


def outer_for(spec: str | list) -> tuple[sp.Expr, sp.Expr]:
    """Decode a JSON-friendly layer description.

    ``"sin"`` is a table function, ``["pow", p, q]`` is ``u**(p/q)`` and
    ``["plus", c, "sin"]`` is ``c + sin(u)``.
    """
    if isinstance(spec, str):
        return OUTERS[spec]
    kind = spec[0]
    if kind == "pow":
        return power_outer(sp.Rational(spec[1], spec[2]))
    if kind == "plus":
        f, fp = OUTERS[spec[2]]
        return spec[1] + f, fp
    raise ValueError(f"unknown layer {spec!r}")


def _is_power(spec: str | list) -> bool:
    return not isinstance(spec, str) and spec[0] == "pow"


def _trig_name(spec: str | list) -> str | None:
    if isinstance(spec, str):
        return spec
    return spec[2] if spec[0] == "plus" else None


def build_chain(*, family: str, difficulty: int, var: sp.Symbol, layers: list, inner: sp.Expr,
                params: Params, fn: str = "f", word: WordContext | None = None,
                at: dict | None = None) -> Built:
    """Compose ``layers`` (outermost first) around ``inner`` and walk the chain rule.

    The layer specs are recorded in ``params["layers"]`` so mistake patterns
    can reason about the structure without knowing the family.
    """
    params = {**params, "layers": layers}
    funcs = [outer_for(spec) for spec in layers]

    # comps[i] is the input to layer i; comps[-1] is the innermost expression.
    comps: list[sp.Expr] = [inner]
    for f, _ in reversed(funcs):
        comps.insert(0, f.subs(u, comps[0]))
    expr = comps[0]
    comps = comps[1:]  # comps[i] is now what layer i is applied to
    # SymPy canonicalises some compositions (sin(-5x+2) becomes -sin(5x-2)).
    # The parts would then no longer match what the student sees, so reject.
    if not all(expr.has(c) for c in comps):
        raise ValueError("SymPy rewrote the composition; resample")

    factors = [fp.subs(u, comps[i]) for i, (_, fp) in enumerate(funcs)]
    innermost_prime = sp.diff(inner, var)
    key = sp.Mul(*factors) * innermost_prime

    inside = comps[0]
    inside_prime = sp.Mul(*factors[1:]) * innermost_prime
    outer, outer_prime = funcs[0]

    parts = {
        "u": u,
        "outer": outer,
        "outer_prime": outer_prime,
        "inside": inside,
        "inside_prime": inside_prime,
        "outer_prime_at_inside": factors[0],
        "innermost": inner,
        "innermost_prime": innermost_prime,
        "layer_factors": sp.Mul(*factors),
    }
    snippets = {
        "expr_colored": tex_compose(outer, u, inside, inner_color="yellow", outer_color="mint"),
        "outer_at_inside_colored": tex_compose(outer_prime, u, inside, inner_color="yellow"),
    }

    v = tex(var)
    steps = [
        Step(
            id="identify",
            title="Spot the inside and the outside",
            latex=rf"u = {highlight(tex(inside), 'yellow')},\quad {fn}(u) = {highlight(tex(outer), 'mint')}",
        ),
        Step(
            id="outer_derivative",
            title="Differentiate the outside, keep the inside",
            latex=rf"{fn}'(u) = {tex(outer_prime)} \;\Rightarrow\; {snippets['outer_at_inside_colored']}",
            expr=factors[0],
            partial_tag="dropped_inner_derivative",
        ),
        Step(
            id="inner_derivative",
            title="Differentiate the inside",
            latex=rf"\frac{{du}}{{d{v}}} = {highlight(tex(inside_prime), 'yellow')}",
            expr=inside_prime,
        ),
        Step(
            id="multiply",
            title="Multiply the two derivatives",
            latex=rf"\frac{{d}}{{d{v}}}\,{snippets['expr_colored']} = {highlight(tex(factors[0]), 'mint')}"
                  rf" \cdot {highlight(tex(inside_prime), 'yellow')} = {tex(key)}",
            expr=key,
        ),
    ]

    key_out = key
    point = None
    if at is not None:
        point = {var: sp.Rational(at["value"])}
        key_out = sp.simplify(key.subs(point))
        steps.append(Step(
            id="evaluate",
            title=f"Evaluate at ${v} = {tex(point[var])}$",
            latex=rf"{fn}'({tex(point[var])}) = {tex(key_out)}",
            expr=key_out,
        ))

    if word is not None:
        prompt = f"{word.text} {word.question}"
    else:
        prompt = rf"Differentiate ${fn}({v}) = {tex(expr)}$."

    return Built(
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


# --- families -------------------------------------------------------------


def _linear(rng: Random, *, a_max: int = 6, b_max: int = 9) -> list[int]:
    # a != +-1 keeps the inner derivative visible; b != 0 keeps it a real composition.
    return [nonzero_int(rng, -a_max, a_max, exclude=(1, -1)), nonzero_int(rng, -b_max, b_max)]


def _quadratic(rng: Random, *, positive: bool = False) -> list[int]:
    """Quadratic coefficients. ``positive`` keeps the quadratic positive at 0 and for
    large |x| so ln of it is a real function over most of the plotted range."""
    while True:
        a, b, c = poly_coeffs(rng, 2, lo=-5, hi=5, min_terms=2)
        if not positive or (a > 0 and c > 0 and b * b < 4 * a * c):
            return [a, b, c]


def _family(id: str, difficulty: int, description: str, sample, build, word: bool = False) -> Family:
    return Family(id=id, difficulty=difficulty, description=description, sample=sample, build=build, word=word)


# d1 ----------------------------------------------------------------------

def _sample_linear_power(rng: Random) -> Params:
    return {"inner": _linear(rng), "n": rng.randint(2, 6)}


def _build_linear_power(p: Params) -> Built:
    return build_chain(family="linear_power", difficulty=1, var=x, layers=[["pow", p["n"], 1]],
                       inner=poly_from(p["inner"], x), params=p)


# Trig arguments keep a positive leading coefficient: SymPy pulls a leading
# minus out of sin, cos and tan, which would change the visible inside.

def _sample_trig_linear(rng: Random) -> Params:
    a = rng.randint(2, 9)
    b = pick(rng, [0, 0, *range(-5, 6)])
    return {"outer": pick(rng, ["sin", "cos"]), "inner": [a, b]}


def _build_trig_linear(p: Params) -> Built:
    return build_chain(family="trig_linear", difficulty=1, var=x, layers=[p["outer"]],
                       inner=poly_from(p["inner"], x), params=p)


def _sample_exp_linear(rng: Random) -> Params:
    return {"inner": [nonzero_int(rng, -8, 8, exclude=(1, -1)), rng.randint(-5, 5)]}


def _build_exp_linear(p: Params) -> Built:
    return build_chain(family="exp_linear", difficulty=1, var=x, layers=["exp"],
                       inner=poly_from(p["inner"], x), params=p)


# d2 ----------------------------------------------------------------------

def _sample_poly_power(rng: Random) -> Params:
    return {"inner": _quadratic(rng), "n": rng.randint(2, 5)}


def _build_poly_power(p: Params) -> Built:
    return build_chain(family="poly_power", difficulty=2, var=x, layers=[["pow", p["n"], 1]],
                       inner=poly_from(p["inner"], x), params=p)


def _sample_trig_poly(rng: Random) -> Params:
    k = pick(rng, [2, 3])
    a = rng.randint(1, 5)
    c = rng.randint(-9, 9)
    return {"outer": pick(rng, ["sin", "cos"]), "k": k, "a": a, "c": c}


def _build_trig_poly(p: Params) -> Built:
    inner = p["a"] * x ** p["k"] + p["c"]
    return build_chain(family="trig_poly", difficulty=2, var=x, layers=[p["outer"]], inner=inner, params=p)


def _sample_exp_poly(rng: Random) -> Params:
    return {"a": nonzero_int(rng, -4, 4), "b": rng.randint(-6, 6)}


def _build_exp_poly(p: Params) -> Built:
    inner = p["a"] * x**2 + p["b"] * x
    return build_chain(family="exp_poly", difficulty=2, var=x, layers=["exp"], inner=inner, params=p)


def _sample_sqrt_poly(rng: Random) -> Params:
    return {"a": rng.randint(1, 5), "c": rng.randint(1, 9)}


def _build_sqrt_poly(p: Params) -> Built:
    inner = p["a"] * x**2 + p["c"]
    return build_chain(family="sqrt_poly", difficulty=2, var=x, layers=["sqrt"], inner=inner, params=p)


# d3 ----------------------------------------------------------------------

def _sample_ln_poly(rng: Random) -> Params:
    return {"inner": _quadratic(rng, positive=True)}


def _build_ln_poly(p: Params) -> Built:
    return build_chain(family="ln_poly", difficulty=3, var=x, layers=["ln"],
                       inner=poly_from(p["inner"], x), params=p)


def _sample_negative_power(rng: Random) -> Params:
    return {"inner": _quadratic(rng), "n": rng.randint(1, 4)}


def _build_negative_power(p: Params) -> Built:
    return build_chain(family="negative_power", difficulty=3, var=x, layers=[["pow", -p["n"], 1]],
                       inner=poly_from(p["inner"], x), params=p)


def _sample_fractional_power(rng: Random) -> Params:
    num, den = pick(rng, [(3, 2), (1, 3), (2, 3), (5, 2), (1, 4)])
    return {"inner": [rng.randint(1, 4), 0, rng.randint(1, 9)], "pq": [num, den]}


def _build_fractional_power(p: Params) -> Built:
    num, den = p["pq"]
    return build_chain(family="fractional_power", difficulty=3, var=x, layers=[["pow", num, den]],
                       inner=poly_from(p["inner"], x), params=p)


def _sample_tan_poly(rng: Random) -> Params:
    return {"a": rng.randint(1, 4), "c": rng.randint(-5, 5)}


def _build_tan_poly(p: Params) -> Built:
    inner = p["a"] * x**2 + p["c"]
    return build_chain(family="tan_poly", difficulty=3, var=x, layers=["tan"], inner=inner, params=p)


# d4: two layers of composition ---------------------------------------------

def _sample_power_of_trig(rng: Random) -> Params:
    return {"n": rng.randint(2, 4), "trig": pick(rng, ["sin", "cos"]), "a": rng.randint(2, 5)}


def _build_power_of_trig(p: Params) -> Built:
    return build_chain(family="power_of_trig", difficulty=4, var=x, layers=[["pow", p["n"], 1], p["trig"]],
                       inner=p["a"] * x, params=p)


def _sample_exp_of_trig(rng: Random) -> Params:
    return {"trig": pick(rng, ["sin", "cos"]), "a": rng.randint(1, 4), "k": pick(rng, [1, 2])}


def _build_exp_of_trig(p: Params) -> Built:
    inner = p["a"] * x ** p["k"]
    if p["k"] == 1 and p["a"] == 1:
        inner = inner + 1
    return build_chain(family="exp_of_trig", difficulty=4, var=x, layers=["exp", p["trig"]], inner=inner,
                       params=p)


def _sample_sqrt_of_trig_poly(rng: Random) -> Params:
    return {"trig": pick(rng, ["sin", "cos"]), "c": rng.randint(2, 6), "a": rng.randint(1, 3)}


def _build_sqrt_of_trig_poly(p: Params) -> Built:
    # sqrt(c + sin(a x^2)): three derivatives to multiply.
    return build_chain(family="sqrt_of_trig_poly", difficulty=4, var=x, layers=["sqrt", ["plus", p["c"], p["trig"]]],
                       inner=p["a"] * x**2, params=p)


# word problems ---------------------------------------------------------------

_PARTICLE = (
    "A particle moves along a line so that its position after $t$ seconds is $s(t) = {expr}$ meters.",
    "What is its velocity, in m/s, at $t = {t0}$?",
)
_RIPPLE = (
    "A ripple spreads across a pond. Its radius after $t$ seconds is $r(t) = {expr}$ centimeters.",
    "How fast is the radius growing, in cm/s, at $t = {t0}$?",
)


def _sample_word_particle(rng: Random) -> Params:
    return {"a": rng.randint(2, 4), "b": rng.randint(1, 3), "n": rng.randint(2, 3), "t0": rng.randint(1, 3)}


def _build_word_particle(p: Params) -> Built:
    inner = p["a"] * t + p["b"]
    expr = (inner) ** p["n"]
    text, question = _PARTICLE
    word = WordContext(text=text.format(expr=tex(expr)), question=question.format(t0=p["t0"]), unit="m/s")
    return build_chain(family="word_particle", difficulty=2, var=t, layers=[["pow", p["n"], 1]], inner=inner,
                       params=p, fn="s", word=word, at={"value": p["t0"]})


def _sample_word_ripple(rng: Random) -> Params:
    while True:
        r0, a, t0 = rng.randint(2, 5), rng.randint(2, 6), rng.randint(1, 4)
        b = r0 * r0 - a * t0
        if b >= 1:
            return {"a": a, "b": b, "t0": t0}


def _build_word_ripple(p: Params) -> Built:
    inner = p["a"] * t + p["b"]
    text, question = _RIPPLE
    word = WordContext(text=text.format(expr=tex(sp.sqrt(inner))), question=question.format(t0=p["t0"]),
                       unit="cm/s")
    return build_chain(family="word_ripple", difficulty=3, var=t, layers=["sqrt"], inner=inner, params=p,
                       fn="r", word=word, at={"value": p["t0"]})


FAMILIES = (
    _family("linear_power", 1, "Power of a linear function, (ax+b)^n", _sample_linear_power, _build_linear_power),
    _family("trig_linear", 1, "sin or cos of a linear function", _sample_trig_linear, _build_trig_linear),
    _family("exp_linear", 1, "e to a linear function", _sample_exp_linear, _build_exp_linear),
    _family("poly_power", 2, "Power of a quadratic", _sample_poly_power, _build_poly_power),
    _family("trig_poly", 2, "sin or cos of a polynomial", _sample_trig_poly, _build_trig_poly),
    _family("exp_poly", 2, "e to a quadratic", _sample_exp_poly, _build_exp_poly),
    _family("sqrt_poly", 2, "Square root of a quadratic", _sample_sqrt_poly, _build_sqrt_poly),
    _family("word_particle", 2, "Velocity of a particle with position (at+b)^n", _sample_word_particle,
            _build_word_particle, word=True),
    _family("ln_poly", 3, "Natural log of a quadratic", _sample_ln_poly, _build_ln_poly),
    _family("negative_power", 3, "Reciprocal power of a quadratic", _sample_negative_power, _build_negative_power),
    _family("fractional_power", 3, "Fractional power of a quadratic", _sample_fractional_power,
            _build_fractional_power),
    _family("tan_poly", 3, "tan of a quadratic", _sample_tan_poly, _build_tan_poly),
    _family("word_ripple", 3, "Growth rate of a ripple with radius sqrt(at+b)", _sample_word_ripple,
            _build_word_ripple, word=True),
    _family("power_of_trig", 4, "Power of sin or cos of a linear function", _sample_power_of_trig,
            _build_power_of_trig),
    _family("exp_of_trig", 4, "e to sin or cos of a polynomial", _sample_exp_of_trig, _build_exp_of_trig),
    _family("sqrt_of_trig_poly", 4, "Square root of a constant plus sin or cos of a quadratic",
            _sample_sqrt_of_trig_poly, _build_sqrt_of_trig_poly),
)


# --- mistakes -------------------------------------------------------------


def _outer_spec(b: Built):
    return b.params["layers"][0]


def _nested(b: Built) -> bool:
    return len(b.params["layers"]) > 1


def _has_trig_sign_layer(b: Built) -> bool:
    return any(_trig_name(spec) in TRIG_SIGN_OUTERS for spec in b.params["layers"])


def _dropped_inner(b: Built) -> sp.Expr:
    return b.parts["outer_prime_at_inside"]


def _dropped_innermost(b: Built) -> sp.Expr | None:
    # Multiplied every layer's derivative except the innermost one.
    return b.parts["layer_factors"] if _nested(b) else None


def _composed(b: Built) -> sp.Expr:
    return b.parts["outer_prime"].subs(u, b.parts["inside_prime"])


def _outer_not_differentiated(b: Built) -> sp.Expr:
    # Kept the outer function as it was and only multiplied by the inside's derivative.
    return b.parts["outer"].subs(u, b.parts["inside"]) * b.parts["inside_prime"]


def _trig_sign(b: Built) -> sp.Expr | None:
    return -b.key if _has_trig_sign_layer(b) else None


def _exponent_not_reduced(b: Built) -> sp.Expr | None:
    spec = _outer_spec(b)
    if not _is_power(spec):
        return None
    n = sp.Rational(spec[1], spec[2])
    return n * b.parts["inside"] ** n * b.parts["inside_prime"]


def _coefficient_dropped(b: Built) -> sp.Expr | None:
    spec = _outer_spec(b)
    if spec == "sqrt":
        return b.parts["inside_prime"] / sp.sqrt(b.parts["inside"])
    if _is_power(spec) and spec[2] != 1:
        n = sp.Rational(spec[1], spec[2])
        return b.parts["inside"] ** (n - 1) * b.parts["inside_prime"]
    return None


def _negative_exponent_slip(b: Built) -> sp.Expr | None:
    spec = _outer_spec(b)
    if not _is_power(spec) or sp.Rational(spec[1], spec[2]) >= 0:
        return None
    n = sp.Rational(spec[1], spec[2])
    return n * b.parts["inside"] ** (n + 1) * b.parts["inside_prime"]


def _exp_as_power(b: Built) -> sp.Expr | None:
    if _outer_spec(b) != "exp":
        return None
    inside = b.parts["inside"]
    return inside * sp.exp(inside - 1) * b.parts["inside_prime"]


def _at(b: Built, expr: sp.Expr | None) -> sp.Expr | None:
    """Mistake answers for 'evaluate at a point' problems are numbers too."""
    if expr is None or b.at is None:
        return expr
    return expr.subs(b.at)


def _pattern(tag: str, step: str, fn, note: str, signature: bool = False) -> MistakePattern:
    return MistakePattern(tag=tag, step=step, buggy=lambda b: _at(b, fn(b)), note=note, signature=signature)


MISTAKES = (
    _pattern(
        "dropped_inner_derivative", "multiply", _dropped_inner,
        "Check the step where you multiply. You differentiated the outside and got "
        "$[[outer_prime_at_inside:mint]]$, but the chain rule also multiplies by the derivative of the "
        "inside, $\\frac{d}{dx}\\left([[inside:yellow]]\\right)$.",
        signature=True,
    ),
    _pattern(
        "dropped_inner_derivative", "inner_derivative", _dropped_innermost,
        "There are two layers inside the outer function here. You multiplied by the middle layer's "
        "derivative but stopped before the innermost one, $[[innermost_prime:yellow]]$.",
    ),
    _pattern(
        "composed_derivatives", "multiply", _composed,
        "Look at how you combined the two derivatives. You plugged the inside's derivative into the outer "
        "derivative. The chain rule keeps the inside as it is in the outer derivative and multiplies by "
        "$[[inside_prime:yellow]]$ afterwards.",
    ),
    _pattern(
        "wrong_outer_derivative", "outer_derivative", _outer_not_differentiated,
        "You multiplied by the inside's derivative but left the outside function as it was. "
        "Differentiate the outside first: $[[outer_prime]]$, evaluated at the inside.",
    ),
    _pattern(
        "trig_derivative_sign", "outer_derivative", _trig_sign,
        "Recheck the sign of your trig derivative: $\\frac{d}{du}\\sin u = \\cos u$ but "
        "$\\frac{d}{du}\\cos u = -\\sin u$.",
    ),
    _pattern(
        "power_exponent_not_reduced", "outer_derivative", _exponent_not_reduced,
        "In the outer derivative you brought the power down but kept the same exponent. The power rule "
        "lowers the exponent by one: $[[outer_prime]]$.",
    ),
    _pattern(
        "power_coefficient_dropped", "outer_derivative", _coefficient_dropped,
        "In the outer derivative you lowered the exponent but did not multiply by the old exponent. "
        "The outer derivative is $[[outer_prime]]$.",
    ),
    _pattern(
        "negative_exponent_slip", "outer_derivative", _negative_exponent_slip,
        "Watch the exponent arithmetic in the outer derivative. Lowering a negative exponent by one makes "
        "it more negative: $[[outer_prime]]$.",
    ),
    _pattern(
        "exp_log_derivative_error", "outer_derivative", _exp_as_power,
        "The outer function is $e^u$, which is not a power of $u$. Its derivative is $e^u$ itself, then "
        "multiply by the inside's derivative.",
    ),
)


def _hints(b: Built) -> HintLadder:
    if _nested(b):
        bigger = (
            "Work from the outside in. Let $u = [[inside:yellow]]$ so the outside is $[[outer:mint]]$. "
            "The inside is itself a composition, so its derivative needs the chain rule again."
        )
    else:
        bigger = (
            "Let $u = [[inside:yellow]]$, so the outside is $[[outer:mint]]$ as a function of $u$. "
            "Differentiate the outside with respect to $u$, then multiply by $u'$."
        )
    return HintLadder(
        nudge="This is one function inside another. Which part is the inside?",
        bigger=bigger,
        full_step="$[[step:multiply]]$",
    )


SKILL = SkillSpec(
    id="calc1.derivatives.chain_rule",
    slug="chain_rule",
    title="Chain rule",
    summary="Differentiate a composition: the outer derivative at the inside, times the inside's derivative.",
    task="differentiate",
    families=FAMILIES,
    mistakes=MISTAKES,
    hints=_hints,
    formula=FormulaEntry(
        title="Chain rule",
        latex=r"\frac{d}{dx}\, f\big(g(x)\big) = f'\big(g(x)\big)\, g'(x)",
        note="Differentiate the outside and keep the inside, then multiply by the derivative of the inside.",
    ),
    keywords=("chain rule", "composite function", "composition", "inner function", "outer function",
              "function of a function"),
    prerequisites=("calc1.derivatives.power_rule",),
)
