"""Say a SymPy expression out loud, for the narration voice and screen readers."""

from __future__ import annotations

import sympy as sp

FUNCTIONS = {
    sp.sin: "sine of", sp.cos: "cosine of", sp.tan: "tangent of", sp.sec: "secant of", sp.csc: "cosecant of",
    sp.cot: "cotangent of", sp.log: "the natural log of", sp.asin: "arcsine of", sp.acos: "arccosine of",
    sp.atan: "arctangent of",
}
POWERS = {2: "squared", 3: "cubed"}


def _number(n: sp.Rational) -> str:
    if n < 0:
        return f"negative {_number(-n)}"
    if n.q == 1:
        return str(n.p)
    if n == sp.Rational(1, 2):
        return "one half"
    return f"{n.p} over {n.q}"


def _grouped(e: sp.Expr) -> str:
    """Speak a sub-expression, marking compound pieces so the grouping is heard."""
    text = speak(e)
    return f"the quantity {text}," if isinstance(e, sp.Add) else text


def speak(e: sp.Basic) -> str:
    e = sp.sympify(e)
    if e.is_Rational:
        return _number(e)
    if e is sp.E:
        return "e"
    if e is sp.pi:
        return "pi"
    if e.is_Symbol:
        return e.name
    if isinstance(e, sp.Add):
        parts: list[str] = []
        for i, term in enumerate(e.as_ordered_terms()):
            negative = term.could_extract_minus_sign()
            body = speak(-term if negative else term)
            if i == 0:
                parts.append(f"negative {body}" if negative else body)
            else:
                parts.append(f"{'minus' if negative else 'plus'} {body}")
        return " ".join(parts)
    if isinstance(e, sp.Mul):
        if e.could_extract_minus_sign():
            return f"negative {speak(-e)}"
        num, den = sp.fraction(e)
        if den != 1:
            return f"{_grouped(num)} over {_grouped(den)}"
        coeff, rest = e.as_coeff_Mul()
        out = _number(coeff) if coeff != 1 else ""
        for factor in sp.Mul.make_args(rest):
            # "3 x squared" reads naturally; anything bigger gets an explicit "times".
            simple = factor.is_Symbol or (isinstance(factor, sp.Pow) and factor.base.is_Symbol
                                          and factor.exp.is_Integer and factor.exp > 0)
            joiner = " " if simple else " times "
            out = f"{out}{joiner if out else ''}{_grouped(factor)}"
        return out
    if isinstance(e, sp.Pow):
        base, exp = e.as_base_exp()
        if base is sp.E:
            return f"e to the {_grouped(exp)}"
        if exp == sp.Rational(1, 2):
            return f"the square root of {_grouped(base)}"
        if exp == -1:
            return f"one over {_grouped(base)}"
        if exp.is_Integer and int(exp) in POWERS:
            return f"{_grouped(base)} {POWERS[int(exp)]}"
        return f"{_grouped(base)} to the power {speak(exp)}"
    if isinstance(e, sp.exp):
        return f"e to the {_grouped(e.args[0])}"
    for fn, name in FUNCTIONS.items():
        if isinstance(e, fn):
            return f"{name} {_grouped(e.args[0])}"
    if isinstance(e, sp.Eq):
        return f"{speak(e.lhs)} equals {speak(e.rhs)}"
    return str(e)
