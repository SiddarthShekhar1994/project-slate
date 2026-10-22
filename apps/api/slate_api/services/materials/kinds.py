"""Problem kinds Slate can check without a hand-written skill template.

A problem read from course materials arrives as a *spec*: its kind plus the
mathematics in Slate's answer syntax, for example
``{"kind": "limit", "expr": "sin(3x)/x", "var": "x", "to": "0"}``. Every
string in a spec goes through the same parser that reads student answers, so
nothing from a spec is evaluated as code.

SymPy computes the answer key from the spec (the oracle for each kind below).
``verify.py`` then requires that key to agree with the answer Claude gave when
it read the problem, so two independent workings agree before a student sees
it.

===================  ==========================================  =====================
kind                 asks for                                    the student types
===================  ==========================================  =====================
derivative           f'(x), or f'(a) with ``at``                 expression / number
implicit_derivative  dy/dx on a curve, or its value at a point   expression / number
tangent_line         the tangent line at a point                 line (``y = 3x - 2``)
linear_approx        L(x) at ``at``, or L(``estimate``)          line / number
limit                a two-sided, one-sided or infinite limit    number, oo, -oo or DNE
antiderivative       an antiderivative                           expression (+ C)
definite_integral    a definite integral                         number
solve                the real solutions of an equation           list of values
critical_points      the critical points of f                    list of values
extremum             an absolute max or min: value or where      number / list of values
related_rates        an unknown rate at an instant               number
===================  ==========================================  =====================

A stored problem keeps its key (as ``srepr``), so loading it again never
reruns an oracle; :func:`build` computes the key only when it is missing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import sympy as sp
from slate_skills.core.text import tex
from slate_skills.core.types import Built, FormulaEntry, HintLadder, SkillSpec, Step

from ..verify import ParseError, parse_answer

KINDS = (
    "derivative", "implicit_derivative", "tangent_line", "linear_approx", "limit", "antiderivative",
    "definite_integral", "solve", "critical_points", "extremum", "related_rates",
)
ANSWER_KINDS = ("expression", "number", "line", "values", "limit", "antiderivative")
# Single letters only, and never e (Euler's number). Readers rename others (θ becomes t).
VARIABLES = ("x", "t", "y", "r", "s", "u", "v", "w", "z", "h")
DNE = sp.Symbol("DNE")
MAX_VALUES = 10

TEMPLATE_TASKS = ("differentiate", "implicit_differentiate")
"""Tasks the template grader already handles; the others are graded in ``answers.py``."""


class SpecError(ValueError):
    """The spec can't be read, or doesn't describe a problem SymPy can answer."""


@dataclass(frozen=True)
class KindInfo:
    title: str
    task: str
    hints: tuple[str, str, str]


KIND_INFO: dict[str, KindInfo] = {
    "derivative": KindInfo("Derivative", "differentiate", (
        "Look at the outermost operation. Is it a sum, a product, a quotient or a composition?",
        "Apply the rule for that operation, then differentiate each piece it hands you.",
        "Write the rule out with every piece filled in, then simplify.")),
    "implicit_derivative": KindInfo("Implicit differentiation", "implicit_differentiate", (
        r"Differentiate both sides with respect to $x$, treating $y$ as a function of $x$.",
        r"Every $y$ term picks up a factor of $\frac{dy}{dx}$ by the chain rule; terms like $xy$ need the product rule.",
        r"Collect the $\frac{dy}{dx}$ terms on one side, factor it out and divide.")),
    "tangent_line": KindInfo("Tangent line", "tangent_line", (
        "A line needs a point and a slope. The point is on the curve at the given spot.",
        "The slope is the derivative evaluated at that point.",
        r"Put them into point-slope form, $y - y_0 = m(x - x_0)$, and solve for $y$.")),
    "linear_approx": KindInfo("Linear approximation", "linear_approx", (
        "The linearization is the tangent line at the base point.",
        r"$L(x) = f(a) + f'(a)(x - a)$. Find $f(a)$ and $f'(a)$ first.",
        "Substitute those values, and plug in the point you're estimating if the problem asks for a number.")),
    "limit": KindInfo("Limit", "limit", (
        "Try substituting first. If you get a number, that's the limit.",
        r"If you get $\frac{0}{0}$, factor and cancel, rationalize, use a known limit, or use L'Hôpital's rule.",
        "For a one-sided or infinite limit, check the sign of each piece as you approach.")),
    "antiderivative": KindInfo("Antiderivative", "antiderivative", (
        "Which derivative rule would produce this expression? Run it backwards.",
        "Split sums apart, pull out constants, and look for a substitution if there's an inside function.",
        "Check your answer by differentiating it, and add the constant of integration.")),
    "definite_integral": KindInfo("Definite integral", "definite_integral", (
        "Find an antiderivative first.",
        r"Evaluate it at the upper limit and subtract its value at the lower limit: $F(b) - F(a)$.",
        "Watch the signs when you subtract, and simplify the result.")),
    "solve": KindInfo("Solving an equation", "solve", (
        "Get everything on one side so the other side is zero.",
        "Factor, or use a known identity, and set each factor to zero.",
        "Keep only the solutions in the allowed interval or domain.")),
    "critical_points": KindInfo("Critical points", "critical_points", (
        r"Critical points are where $f'(x) = 0$ or where $f'(x)$ doesn't exist, inside the domain of $f$.",
        r"Find $f'(x)$ and write it as a single fraction.",
        "Set the numerator to zero, check where the denominator is zero, and drop points outside the domain.")),
    "extremum": KindInfo("Absolute extremum", "extremum", (
        "The absolute max and min happen at critical points or at the endpoints.",
        "Find the critical points inside the interval, then list them with the endpoints.",
        "Evaluate the function at every candidate and compare.")),
    "related_rates": KindInfo("Related rates", "related_rates", (
        "Write one equation relating the changing quantities.",
        r"Differentiate both sides with respect to $t$; every variable picks up its own rate.",
        "Substitute the values at that instant and solve for the unknown rate.")),
}


def _generic_spec(kind: str) -> SkillSpec:
    info = KIND_INFO[kind]
    return SkillSpec(
        id=f"material.{kind}",
        slug=kind.replace("_", "-"),
        title=info.title,
        summary="",
        task=info.task,  # type: ignore[arg-type]
        families=(),
        mistakes=(),
        hints=HintLadder(*info.hints),
        formula=FormulaEntry(title=info.title, latex=""),
    )


GENERIC_SPECS: dict[str, SkillSpec] = {kind: _generic_spec(kind) for kind in KINDS}
"""What grading uses for a material problem in place of a skill: no mistake patterns."""


# --- reading spec strings ------------------------------------------------------------------

_INFINITY = {
    "oo": sp.oo, "+oo": sp.oo, "inf": sp.oo, "+inf": sp.oo, "infinity": sp.oo, "+infinity": sp.oo, "∞": sp.oo,
    "+∞": sp.oo, "-oo": -sp.oo, "-inf": -sp.oo, "-infinity": -sp.oo, "-∞": -sp.oo, "−oo": -sp.oo, "−∞": -sp.oo,
}


def _text(spec: Mapping[str, Any], key: str, *, required: bool = True) -> str:
    value = spec.get(key)
    value = "" if value is None else str(value).strip()
    if required and not value:
        raise SpecError(f"the problem has no {key}")
    return value


def _variable(name: str) -> sp.Symbol:
    if name not in VARIABLES:
        raise SpecError(f"variable {name!r} isn't one Slate can use")
    return sp.Symbol(name)


def _var(spec: Mapping[str, Any], key: str = "var", default: str = "x") -> sp.Symbol:
    return _variable(_text(spec, key, required=False) or default)


def _parse(text: str, symbols: tuple[sp.Symbol, ...]) -> tuple[sp.Expr, str]:
    try:
        parsed = parse_answer(text, symbols)
    except ParseError as exc:
        raise SpecError(f"couldn't read {text!r}: {exc}") from None
    return parsed.expr, parsed.latex


def finite_real(value: sp.Basic) -> bool:
    """A number with no variables that is real and finite."""
    if not isinstance(value, sp.Expr) or value.free_symbols or value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        return False
    try:
        number = sp.N(value, 30)
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    if not number.is_number:
        return False
    re_part, im_part = number.as_real_imag()
    return bool(re_part.is_finite) and abs(float(im_part)) <= 1e-12 * max(1.0, abs(float(re_part)))


def _number(text: str) -> tuple[sp.Expr, str]:
    clean = text.strip()
    if clean.lower() in _INFINITY:
        value = _INFINITY[clean.lower()]
        return value, tex(value)
    value, latex = _parse(clean, ())
    if not finite_real(value):
        raise SpecError(f"{text!r} isn't a real number")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", clean):
        latex = clean  # 4.1, not 41/10
    return value, latex


def _equation(text: str, symbols: tuple[sp.Symbol, ...]) -> tuple[sp.Expr, sp.Expr, str]:
    parts = text.split("=")
    if len(parts) != 2:
        raise SpecError(f"{text!r} should be an equation with one equals sign")
    lhs, lhs_tex = _parse(parts[0], symbols)
    rhs, rhs_tex = _parse(parts[1], symbols)
    return lhs, rhs, f"{lhs_tex} = {rhs_tex}"


def _assignments(text: str, names: tuple[str, ...]) -> dict[sp.Symbol, sp.Expr]:
    """``"x=3, y=4"`` as ``{x: 3, y: 4}``."""
    out: dict[sp.Symbol, sp.Expr] = {}
    for part in re.split(r"[,;]", text):
        if not part.strip():
            continue
        if "=" not in part:
            raise SpecError(f"{part.strip()!r} should look like x=3")
        name, value = (s.strip() for s in part.split("=", 1))
        if name not in names:
            raise SpecError(f"{name!r} isn't one of the problem's variables")
        number, _ = _number(value)
        if not finite_real(number):
            raise SpecError(f"{name} needs a finite value")
        out[sp.Symbol(name)] = number
    return out


def _at(spec: Mapping[str, Any], var: sp.Symbol, *, required: bool = False) -> sp.Expr | None:
    """A single point: ``"2"`` or ``"x=2"``."""
    text = _text(spec, "at", required=required)
    if not text:
        return None
    if "=" in text:
        values = _assignments(text, (var.name,))
        if var not in values:
            raise SpecError(f"the point needs a value of {var}")
        return values[var]
    value, _ = _number(text)
    if not finite_real(value):
        raise SpecError("the point needs a finite value")
    return value


@dataclass(frozen=True)
class Interval:
    lower: sp.Expr
    upper: sp.Expr
    left_closed: bool
    right_closed: bool

    @property
    def closed(self) -> bool:
        return self.left_closed and self.right_closed

    def as_set(self) -> sp.Set:
        return sp.Interval(self.lower, self.upper, not self.left_closed, not self.right_closed)

    @property
    def latex(self) -> str:
        left = "[" if self.left_closed else "("
        right = "]" if self.right_closed else ")"
        return rf"\left{left}{tex(self.lower)}, {tex(self.upper)}\right{right}"


def _interval(text: str) -> Interval | None:
    clean = text.strip()
    if not clean:
        return None
    left = clean[0] if clean[0] in "[(" else "["
    right = clean[-1] if clean[-1] in "])" else "]"
    inner = clean[1:] if clean[0] in "[(" else clean
    inner = inner[:-1] if clean[-1] in "])" else inner
    parts = inner.split(",")
    if len(parts) != 2:
        raise SpecError(f"{text!r} should be an interval like [0, 2pi]")
    lower, _ = _number(parts[0])
    upper, _ = _number(parts[1])
    if not _as_float(lower) < _as_float(upper):
        raise SpecError(f"{text!r} is empty")
    return Interval(lower, upper, left == "[" and lower.is_finite is True, right == "]" and upper.is_finite is True)


def _as_float(value: sp.Expr) -> float:
    if value == sp.oo:
        return float("inf")
    if value == -sp.oo:
        return float("-inf")
    return float(sp.N(value))


def _odd_root(e: sp.Basic) -> bool:
    return bool(e.is_Pow and e.exp.is_Rational and not e.exp.is_Integer and e.exp.q % 2 == 1)


def _real(expr: sp.Expr, symbols: tuple[sp.Symbol, ...]) -> tuple[sp.Expr, dict[sp.Symbol, sp.Symbol]]:
    """``expr`` as a calculus course reads it, for solving over the reals.

    Symbols become real, and odd roots of negative numbers are real:
    SymPy's principal branch makes $(-1)^{2/3}$ complex, but on a review sheet
    $x^{2/3}$ on $[-1, 8]$ means the real cube root squared.
    """
    mapping = {s: sp.Symbol(s.name, real=True) for s in symbols}
    real = expr.subs(mapping)
    real = real.replace(_odd_root, lambda e: sp.real_root(e.base, e.exp.q) ** e.exp.p)
    return real, mapping


def _real_derivative(real: sp.Expr, x: sp.Symbol) -> sp.Expr:
    # sign(x) from a real root differentiates to a delta at 0, a point that is
    # critical anyway (f' is undefined there or zero); drop it.
    return sp.diff(real, x).replace(sp.DiracDelta, lambda *args: sp.S.Zero)


def _is_zero(value: sp.Expr) -> bool:
    if value == 0:
        return True
    try:
        number = complex(sp.N(value, 30))
    except (TypeError, ValueError):
        return sp.simplify(value) == 0
    return abs(number) < 1e-10


def _real_values(values: sp.Set) -> list[sp.Expr]:
    if values == sp.S.EmptySet:
        return []
    if not isinstance(values, sp.FiniteSet):
        raise SpecError("SymPy couldn't list the solutions (there may be infinitely many)")
    out = [sp.nsimplify(v) if isinstance(v, sp.Float) else v for v in values]
    if len(out) > MAX_VALUES:
        raise SpecError("too many solutions to check")
    for value in out:
        if not finite_real(value):
            raise SpecError(f"solution {value} isn't a real number")
    return sorted(out, key=lambda v: float(sp.N(v)))


def _plain(expr: sp.Expr, mapping: dict[sp.Symbol, sp.Symbol]) -> sp.Expr:
    return expr.subs({real: plain for plain, real in mapping.items()})


# --- prompts --------------------------------------------------------------------------------


def _fn(spec: Mapping[str, Any], var: sp.Symbol) -> tuple[str, str]:
    """How the problem names its function: ``("f(x)", "f'(x)")`` or ``("y", "\\frac{dy}{dx}")``."""
    name = _text(spec, "name", required=False) or "f"
    if not re.fullmatch(r"[a-zA-Z]", name) or name == "e":
        name = "f"
    if name == "y":
        return "y", rf"\frac{{dy}}{{d{var.name}}}"
    return f"{name}({var.name})", f"{name}'({var.name})"


# --- the kinds -----------------------------------------------------------------------------


@dataclass
class Draft:
    """What a kind's reader produces: the problem and how to compute its key."""

    task: str
    var: sp.Symbol
    expr: sp.Expr
    prompt: str
    oracle: Callable[[], sp.Basic]
    answer: str
    dependent: sp.Symbol | None = None
    equation: sp.Equality | None = None
    at: dict[sp.Symbol, sp.Expr] | None = None


def _derivative(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    if var not in f.free_symbols:
        raise SpecError(f"the function doesn't depend on {var}")
    head, prime = _fn(spec, var)
    a = _at(spec, var)
    if a is None:
        prompt = (rf"Find ${prime}$ for ${head} = {f_tex}$." if head != "y"
                  else rf"Find ${prime}$ for $y = {f_tex}$.")
        return Draft("differentiate", var, f, prompt, lambda: sp.diff(f, var), "expression")
    if head == "y":
        prompt = rf"Find ${prime}$ at ${var.name} = {tex(a)}$ for $y = {f_tex}$."
    else:
        prompt = rf"Find ${prime.replace(f'({var.name})', f'({tex(a)})')}$ for ${head} = {f_tex}$."
    if not finite_real(f.subs(var, a)):
        raise SpecError("the function isn't defined at that point")
    return Draft("differentiate", var, f, prompt, lambda: sp.simplify(sp.diff(f, var).subs(var, a)), "number",
                 at={var: a})


def _curve(spec: Mapping[str, Any]) -> tuple[sp.Symbol, sp.Symbol, sp.Expr, sp.Expr, sp.Expr, str]:
    var = _var(spec)
    dep = _var(spec, "dependent", "y")
    if dep == var:
        raise SpecError("the two variables must differ")
    lhs, rhs, eq_tex = _equation(_text(spec, "equation"), (var, dep))
    F = lhs - rhs
    if dep not in F.free_symbols:
        raise SpecError(f"the equation doesn't involve {dep}")
    return var, dep, F, lhs, rhs, eq_tex


def _curve_point(spec: Mapping[str, Any], var: sp.Symbol, dep: sp.Symbol, F: sp.Expr) -> tuple[sp.Expr, sp.Expr]:
    point = _assignments(_text(spec, "at"), (var.name, dep.name))
    if var not in point or dep not in point:
        raise SpecError(f"the point needs values of {var} and {dep}")
    a, b = point[var], point[dep]
    if not _is_zero(F.subs({var: a, dep: b})):
        raise SpecError("that point isn't on the curve")
    return a, b


def _implicit_slope(F: sp.Expr, var: sp.Symbol, dep: sp.Symbol) -> sp.Expr:
    return -sp.diff(F, var) / sp.diff(F, dep)


def _implicit_derivative(spec: Mapping[str, Any]) -> Draft:
    var, dep, F, lhs, rhs, eq_tex = _curve(spec)
    d = rf"\frac{{d{dep.name}}}{{d{var.name}}}"
    if not _text(spec, "at", required=False):
        prompt = rf"Use implicit differentiation to find ${d}$ for ${eq_tex}$."
        return Draft("implicit_differentiate", var, F, prompt, lambda: sp.cancel(_implicit_slope(F, var, dep)),
                     "expression", dependent=dep, equation=sp.Eq(lhs, rhs, evaluate=False))
    a, b = _curve_point(spec, var, dep, F)
    prompt = rf"Use implicit differentiation to find ${d}$ at the point $({tex(a)}, {tex(b)})$ on ${eq_tex}$."

    def oracle() -> sp.Expr:
        fy = sp.diff(F, dep).subs({var: a, dep: b})
        if _is_zero(fy):
            raise SpecError("the tangent is vertical there")
        return sp.simplify(_implicit_slope(F, var, dep).subs({var: a, dep: b}))

    return Draft("implicit_differentiate", var, F, prompt, oracle, "number", dependent=dep,
                 equation=sp.Eq(lhs, rhs, evaluate=False), at={var: a, dep: b})


def _tangent_line(spec: Mapping[str, Any]) -> Draft:
    if _text(spec, "equation", required=False):
        var, dep, F, _, _, eq_tex = _curve(spec)
        a, b = _curve_point(spec, var, dep, F)
        prompt = rf"Find the equation of the line tangent to the curve ${eq_tex}$ at the point $({tex(a)}, {tex(b)})$."

        def oracle() -> sp.Expr:
            if _is_zero(sp.diff(F, dep).subs({var: a, dep: b})):
                raise SpecError("the tangent is vertical there")
            m = sp.simplify(_implicit_slope(F, var, dep).subs({var: a, dep: b}))
            return sp.expand(b + m * (var - a))

        return Draft("tangent_line", var, F, prompt, oracle, "line")
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    a = _at(spec, var, required=True)
    if not finite_real(f.subs(var, a)):
        raise SpecError("the function isn't defined at that point")
    head, _ = _fn(spec, var)
    curve = rf"$y = {f_tex}$" if head == "y" or head.startswith("f") else rf"the graph of ${head} = {f_tex}$"
    prompt = rf"Find the equation of the line tangent to {curve} at ${var.name} = {tex(a)}$."

    def oracle() -> sp.Expr:
        m = sp.simplify(sp.diff(f, var).subs(var, a))
        y0 = sp.simplify(f.subs(var, a))
        if not (finite_real(m) and finite_real(y0)):
            raise SpecError("there's no tangent line there")
        return sp.expand(y0 + m * (var - a))

    return Draft("tangent_line", var, f, prompt, oracle, "line")


def _linear_approx(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    a = _at(spec, var, required=True)
    head, _ = _fn(spec, var)
    name = "f" if head == "y" else head.split("(")[0]

    def linearization() -> sp.Expr:
        m = sp.simplify(sp.diff(f, var).subs(var, a))
        y0 = sp.simplify(f.subs(var, a))
        if not (finite_real(m) and finite_real(y0)):
            raise SpecError("the function has no linearization there")
        return y0 + m * (var - a)

    estimate = _text(spec, "estimate", required=False)
    if not estimate:
        prompt = rf"Find the linearization $L({var.name})$ of ${name}({var.name}) = {f_tex}$ at ${var.name} = {tex(a)}$."
        return Draft("linear_approx", var, f, prompt, lambda: sp.expand(linearization()), "line")
    x0, x0_tex = _number(estimate)
    prompt = (rf"Use the linearization of ${name}({var.name}) = {f_tex}$ at ${var.name} = {tex(a)}$ "
              rf"to estimate ${name}({x0_tex})$.")
    return Draft("linear_approx", var, f, prompt, lambda: sp.nsimplify(linearization().subs(var, x0)), "number")


def _limit(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    to, to_tex = _number(_text(spec, "to"))
    side = (_text(spec, "side", required=False) or "both").lower()
    if side not in ("both", "left", "right"):
        raise SpecError("side must be both, left or right")
    if not to.is_finite:
        side = "both"
    mark = {"both": "", "left": "^{-}", "right": "^{+}"}[side]
    target = r"\infty" if to == sp.oo else r"-\infty" if to == -sp.oo else to_tex
    prompt = rf"Find $\lim\limits_{{{var.name} \to {target}{mark}}} {f_tex}$."

    def one(direction: str) -> sp.Basic:
        value = sp.limit(f, var, to, direction) if to.is_finite else sp.limit(f, var, to)
        if value.has(sp.Limit):
            raise SpecError("SymPy couldn't find the limit")
        if isinstance(value, sp.AccumBounds) or value.has(sp.AccumBounds) or value in (sp.nan, sp.zoo):
            return DNE
        if value in (sp.oo, -sp.oo):
            return value
        if not finite_real(value):
            return DNE
        return sp.simplify(value)

    def oracle() -> sp.Basic:
        if side == "left":
            return one("-")
        if side == "right" or not to.is_finite:
            return one("+")
        left, right = one("-"), one("+")
        if left == right or (left not in (DNE, sp.oo, -sp.oo) and right not in (DNE, sp.oo, -sp.oo)
                             and _is_zero(left - right)):
            return right
        return DNE

    return Draft("limit", var, f, prompt, oracle, "limit")


def _antiderivative(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    prompt = rf"Find $\int {f_tex} \, d{var.name}$."

    def oracle() -> sp.Expr:
        F = sp.integrate(f, var)
        if F.has(sp.Integral):
            raise SpecError("SymPy couldn't find an antiderivative")
        return F

    return Draft("antiderivative", var, f, prompt, oracle, "antiderivative")


def _definite_integral(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    lower, lower_tex = _number(_text(spec, "lower"))
    upper, upper_tex = _number(_text(spec, "upper"))
    bound = {sp.oo: r"\infty", -sp.oo: r"-\infty"}
    prompt = (rf"Evaluate $\int_{{{bound.get(lower, lower_tex)}}}^{{{bound.get(upper, upper_tex)}}} "
              rf"{f_tex} \, d{var.name}$.")

    def oracle() -> sp.Expr:
        value = sp.integrate(f, (var, lower, upper))
        if value.has(sp.Integral) or not finite_real(value):
            raise SpecError("SymPy couldn't evaluate the integral to a finite number")
        return sp.simplify(value)

    return Draft("definite_integral", var, f, prompt, oracle, "number")


def _solve(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    lhs, rhs, eq_tex = _equation(_text(spec, "equation"), (var,))
    interval = _interval(_text(spec, "interval", required=False))
    where = rf" on ${interval.latex}$" if interval else ""
    prompt = rf"Solve ${eq_tex}$ for ${var.name}${where}."

    def oracle() -> sp.Set:
        real, mapping = _real(lhs - rhs, (var,))
        domain = interval.as_set() if interval else sp.S.Reals
        found = sp.solveset(real, mapping[var], domain)
        return sp.FiniteSet(*_real_values(found))

    return Draft("solve", var, lhs - rhs, prompt, oracle, "values")


def _critical_values(real: sp.Expr, x: sp.Symbol, domain: sp.Set) -> list[sp.Expr]:
    """Where ``real`` (a real function of the real symbol ``x``) has f' = 0 or f' undefined."""
    try:
        allowed = sp.calculus.util.continuous_domain(real, x, domain)
    except (NotImplementedError, ValueError, TypeError):
        allowed = domain
    fp = _real_derivative(real, x)
    zeros = sp.solveset(fp, x, allowed)
    undefined = sp.solveset(sp.denom(sp.together(fp)), x, allowed)
    values = set(_real_values(zeros)) | set(_real_values(undefined))
    return sorted((v for v in values if finite_real(real.subs(x, v))), key=lambda v: float(sp.N(v)))


def _critical_points(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    interval = _interval(_text(spec, "interval", required=False))
    head, _ = _fn(spec, var)
    if head == "y":
        head = f"f({var.name})"
    where = rf" on ${interval.latex}$" if interval else ""
    prompt = rf"Find all critical points of ${head} = {f_tex}${where}."
    domain = interval.as_set() if interval else sp.S.Reals

    def oracle() -> sp.Set:
        real, mapping = _real(f, (var,))
        return sp.FiniteSet(*_critical_values(real, mapping[var], domain))

    return Draft("critical_points", var, f, prompt, oracle, "values")


def _extremum(spec: Mapping[str, Any]) -> Draft:
    var = _var(spec)
    f, f_tex = _parse(_text(spec, "expr"), (var,))
    interval = _interval(_text(spec, "interval"))
    assert interval is not None
    goal = (_text(spec, "goal", required=False) or "max").lower()
    report = (_text(spec, "report", required=False) or "value").lower()
    if goal not in ("max", "min") or report not in ("value", "location"):
        raise SpecError("goal must be max or min, and report value or location")
    word = "maximum" if goal == "max" else "minimum"
    head, _ = _fn(spec, var)
    head = head if head != "y" else f"f({var.name})"
    if report == "value":
        prompt = rf"Find the absolute {word} value of ${head} = {f_tex}$ on ${interval.latex}$."
    else:
        prompt = rf"Find every ${var.name}$ where ${head} = {f_tex}$ reaches its absolute {word} on ${interval.latex}$."

    def oracle() -> sp.Basic:
        real, mapping = _real(f, (var,))
        x = mapping[var]
        inside = sp.Interval(interval.lower, interval.upper, True, True)
        candidates = list(_critical_values(real, x, inside))
        if interval.left_closed:
            candidates.append(interval.lower)
        if interval.right_closed:
            candidates.append(interval.upper)
        values = []
        for c in candidates:
            v = sp.simplify(real.subs(x, c))
            if finite_real(v):
                values.append((c, v))
        if not values:
            raise SpecError("there's nothing to compare")
        pick = max if goal == "max" else min
        best = pick(float(sp.N(v)) for _, v in values)
        # An open or infinite end must not beat (or tie) the best candidate.
        for end, closed, direction in ((interval.lower, interval.left_closed, "+"),
                                       (interval.upper, interval.right_closed, "-")):
            if closed:
                continue
            edge = sp.limit(real, x, end, direction) if end.is_finite else sp.limit(real, x, end)
            if edge.has(sp.Limit):
                raise SpecError("SymPy couldn't check the ends of the interval")
            if edge in (sp.oo, -sp.oo):
                if (edge == sp.oo) == (goal == "max"):
                    raise SpecError(f"the function has no absolute {word} there")
                continue
            if isinstance(edge, sp.AccumBounds) or not finite_real(edge):
                raise SpecError("SymPy couldn't check the ends of the interval")
            # Approaching the open end must not do better than the best value attained.
            edge_value = float(sp.N(edge))
            tolerance = 1e-12 * max(1.0, abs(best))
            if (edge_value > best + tolerance) if goal == "max" else (edge_value < best - tolerance):
                raise SpecError(f"the function has no absolute {word} there")
        winners = [(c, v) for c, v in values if abs(float(sp.N(v)) - best) <= 1e-12 * max(1.0, abs(best))]
        if report == "value":
            return winners[0][1]
        return sp.FiniteSet(*sorted({c for c, _ in winners}, key=lambda c: float(sp.N(c))))

    return Draft("extremum", var, f, prompt, oracle, "number" if report == "value" else "values")


def _related_rates(spec: Mapping[str, Any]) -> Draft:
    names = tuple(n.strip() for n in re.split(r"[,\s]+", _text(spec, "variables")) if n.strip())
    if len(names) < 2 or len(set(names)) != len(names):
        raise SpecError("list the changing quantities, at least two")
    symbols = tuple(_variable(n) for n in names)
    lhs, rhs, _ = _equation(_text(spec, "relation"), symbols)
    F = lhs - rhs
    values = _assignments(_text(spec, "values"), names)
    rates = _assignments(_text(spec, "rates"), names)
    find = _variable(_text(spec, "find"))
    if find not in symbols:
        raise SpecError("the unknown rate must be one of the variables")
    if set(values) != set(symbols):
        raise SpecError("give every variable's value at that instant")
    if set(rates) | {find} != set(symbols) or find in rates:
        raise SpecError("give every rate except the one asked for")
    if not _is_zero(F.subs(values)):
        raise SpecError("the values don't satisfy the relation")

    def oracle() -> sp.Expr:
        c = sp.diff(F, find).subs(values)
        if _is_zero(c):
            raise SpecError("the relation can't determine that rate at this instant")
        known = sum(sp.diff(F, v).subs(values) * rate for v, rate in rates.items())
        return sp.nsimplify(sp.simplify(-known / c))

    # The prompt is always the problem's own wording; see build().
    return Draft("related_rates", find, F, "", oracle, "number")


READERS: dict[str, Callable[[Mapping[str, Any]], Draft]] = {
    "derivative": _derivative,
    "implicit_derivative": _implicit_derivative,
    "tangent_line": _tangent_line,
    "linear_approx": _linear_approx,
    "limit": _limit,
    "antiderivative": _antiderivative,
    "definite_integral": _definite_integral,
    "solve": _solve,
    "critical_points": _critical_points,
    "extremum": _extremum,
    "related_rates": _related_rates,
}
WORD_ONLY = ("related_rates",)
"""Kinds whose prompt is always the problem's own wording."""


def read(spec: Mapping[str, Any]) -> Draft:
    kind = spec.get("kind")
    if kind not in READERS:
        raise SpecError(f"Slate can't check {kind!r} problems")
    return READERS[kind](spec)


# --- building ---------------------------------------------------------------------------------


def key_latex(key: sp.Basic) -> str:
    if key == DNE:
        return r"\text{DNE}"
    if key == sp.S.EmptySet:
        return r"\text{none}"
    if isinstance(key, sp.FiniteSet):
        return ", ".join(tex(v) for v in key)
    return tex(key)


def dump_key(key: sp.Basic) -> str:
    return sp.srepr(key)


def load_key(text: str) -> sp.Basic:
    # srepr written by this module and stored by the server, never anything a student typed.
    return sp.sympify(text, locals={"DNE": DNE})


def build(params: Mapping[str, Any], *, statement_ok: Callable[[str], bool] = lambda _: True) -> Built:
    """The problem that ``params`` describe, with its key.

    ``params`` hold ``spec`` (the kind and its math), optionally ``key`` (the
    stored oracle answer, ``srepr``), ``statement`` (the problem in its own
    words), ``word`` (show the statement rather than a generated prompt),
    ``steps`` (worked steps as ``{"title", "latex"}``) and ``difficulty``.
    Without a stored key the oracle runs, which can be slow: do that inside
    the grading sandbox.
    """
    spec = dict(params["spec"])
    draft = read(spec)
    stored = params.get("key")
    key = load_key(stored) if stored else draft.oracle()
    statement = str(params.get("statement") or "").strip()
    word = bool(params.get("word")) or spec.get("kind") in WORD_ONLY
    usable = bool(statement) and statement_ok(statement)
    if spec.get("kind") in WORD_ONLY and not usable:
        raise SpecError("a word problem needs its statement, with its math between dollar signs")
    prompt = statement if word and usable else draft.prompt
    latex = key_latex(key)
    steps = [Step(id=f"s{i + 1}", title=str(s.get("title", "")).strip(), latex=str(s.get("latex", "")).strip())
             for i, s in enumerate(params.get("steps") or []) if str(s.get("latex", "")).strip()]
    final = key if draft.answer in ("expression", "number", "line", "antiderivative") else None
    steps.append(Step(id="answer", title="Answer", latex=latex, expr=final))
    full = {**params, "spec": spec, "key": dump_key(key), "answer": draft.answer, "word": word}
    return Built(
        family=f"material:{spec['kind']}",
        difficulty=int(params.get("difficulty") or 2),
        task=draft.task,  # type: ignore[arg-type]
        var=draft.var,
        expr=draft.expr,
        key=key,  # type: ignore[arg-type]
        steps=tuple(steps),
        parts={},
        params=full,
        prompt=prompt,
        equation=draft.equation,
        dependent=draft.dependent,
        at=draft.at,
    )


def answer_kind(built: Built) -> str:
    return str(built.params.get("answer") or ("number" if built.at else "expression"))


def answer_symbols(built: Built) -> tuple[sp.Symbol, ...]:
    """The variables a student's answer may use."""
    kind = answer_kind(built)
    if kind in ("number", "values", "limit"):
        return ()
    if kind == "expression" and built.dependent is not None:
        return (built.var, built.dependent)
    return (built.var,)


def signature(spec: Mapping[str, Any], key: str) -> str:
    """Identity of a problem's mathematics: the same spec and key are the same problem."""
    canonical = json.dumps({k: spec[k] for k in sorted(spec)}, sort_keys=True, default=str)
    return hashlib.sha256(f"material|{canonical}|{key}".encode()).hexdigest()[:24]
