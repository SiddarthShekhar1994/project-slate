"""Read and grade answers to problems from course materials.

Derivative problems (``differentiate`` and ``implicit_differentiate``) go
through the template grader unchanged. The other kinds take answers that are
not one expression, so they are read and compared here:

- number: a value, optionally after ``x =`` and with units after it (``-1.5 ft/s``)
- line: ``y = 3x - 2``, ``L(x) = ...``, point-slope form ``y - 1 = 3(x - 1)``, or just ``3x - 2``
- values: a list like ``-2, 2``, ``x = -2 or x = 2`` or ``x = ±2``; ``none`` when there are none
- limit: a number, ``oo`` (or infinity), ``-oo`` or ``DNE``
- antiderivative: any antiderivative; ``+ C`` is optional, but its absence is pointed out

Correctness is decided the same way as everywhere else in Slate: symbolically,
with the numeric screen first (see ``verify/equivalence.py``). A decimal counts
when it is the exact answer correctly rounded to the places typed (two or more).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import sympy as sp
from slate_skills.core.mistakes import mistake_type
from slate_skills.core.text import tex

from ..grading.grade import Grade, MistakeResult, _rounded_match
from ..verify import ParseError, constant_ratio, equivalent, parse_answer
from ..verify.parse import CONSTANTS, FUNCTIONS
from .kinds import DNE, answer_kind, answer_symbols, finite_real

# "x =", "f'(2) =", "dy/dt =", "L(4.1) =", "V'(t) ="
_LHS = re.compile(r"^\s*(?:d\s*[a-zA-Z]\s*/\s*d\s*[a-zA-Z]|[a-zA-Z]\w*'*(?:\s*\([^()=]*\))?)\s*=\s*(?=\S)")
_UNIT_TAIL = re.compile(r"^(?P<value>.*?[\d)a-z])\s+(?P<unit>[a-zA-Z][a-zA-Z0-9^/·*\s]*)$")
_CONSTANT = re.compile(r"\s*\+\s*[CcKk]\s*$")
_NONE = {"none", "no solution", "no solutions", "no values", "no value", "no critical points", "no critical point",
         "empty", "empty set", "∅", "{}", "dne"}
_LIMIT_WORDS = {
    "oo": sp.oo, "+oo": sp.oo, "∞": sp.oo, "+∞": sp.oo, "inf": sp.oo, "infinity": sp.oo, "+infinity": sp.oo,
    "positive infinity": sp.oo,
    "-oo": -sp.oo, "−oo": -sp.oo, "-∞": -sp.oo, "−∞": -sp.oo, "-inf": -sp.oo, "-infinity": -sp.oo,
    "−infinity": -sp.oo, "negative infinity": -sp.oo, "minus infinity": -sp.oo,
    "dne": DNE, "does not exist": DNE, "doesn't exist": DNE, "doesnt exist": DNE, "no limit": DNE,
    "undefined": DNE, "d.n.e.": DNE, "d.n.e": DNE,
}


@dataclass(frozen=True)
class Reading:
    """A student's answer as read for comparison."""

    value: Any  # an expression, a list of numbers, or oo, -oo, DNE
    latex: str
    places: int = 0  # decimal places typed (for numbers and values)
    note: str | None = None


# --- reading ----------------------------------------------------------------------------------


def _strip_lhs(text: str) -> str:
    return _LHS.sub("", text, count=1)


def _places(text: str) -> int:
    decimals = re.findall(r"\d*\.(\d+)", text)
    return max((len(d) for d in decimals), default=0)


def _number(text: str, *, units: bool = False) -> tuple[sp.Expr, str, int]:
    """A number, after any ``x =``. With ``units``, a trailing unit (``ft/s``) is ignored."""
    clean = _strip_lhs(text).strip()
    try:
        parsed = parse_answer(clean, ())
    except ParseError as first:
        match = _UNIT_TAIL.match(clean) if units else None
        names = set(FUNCTIONS) | set(CONSTANTS)
        if match is None or any(w.lower() in names for w in re.findall(r"[a-zA-Z]+", match.group("unit"))):
            raise first from None
        try:
            parsed = parse_answer(match.group("value"), ())
        except ParseError:
            raise first from None
        clean = match.group("value")
    return parsed.expr, parsed.latex, _places(clean)


def _values(text: str) -> tuple[list[sp.Expr], str, int]:
    clean = text.strip()
    if clean.lower().rstrip(".") in _NONE:
        return [], r"\text{none}", 0
    clean = re.sub(r"^\s*[{\[]\s*|\s*[}\]]\s*$", "", clean)
    parts = [p for p in re.split(r",|;|\bor\b|\band\b", clean) if p.strip()]
    if not parts:
        raise ParseError("Type the values separated by commas, or none.")
    values: list[sp.Expr] = []
    latex: list[str] = []
    places = 0
    for part in parts:
        part = _strip_lhs(part).strip()
        signs = [1]
        if part.startswith(("±", "+-", "+/-")):
            part = re.sub(r"^(±|\+/-|\+-)", "", part)
            signs = [-1, 1]
        value, value_tex, value_places = _number(part)
        places = max(places, value_places)
        for sign in signs:
            v = sign * value
            if not any(v == w for w in values):
                values.append(v)
                latex.append(tex(v) if len(signs) > 1 else value_tex)
    return values, ", ".join(latex), places


def _line(text: str, var: sp.Symbol) -> tuple[sp.Expr, str]:
    """``y = 3x - 2``, ``L(x) = ...``, ``y - 1 = 3(x - 1)`` or ``3x - 2``, as an expression in ``var``."""
    if "=" not in text:
        parsed = parse_answer(text, (var,))
        return parsed.expr, parsed.latex
    left, right = text.split("=", 1)
    if re.fullmatch(rf"\s*(?:y|[A-Za-z]\s*\(\s*{var.name}\s*\))\s*", left):
        parsed = parse_answer(right, (var,))
        return parsed.expr, f"y = {parsed.latex}"
    y = sp.Symbol("y")
    if var == y:
        raise ParseError("Write the line as an expression.")
    try:
        lhs = parse_answer(left, (var, y))
        rhs = parse_answer(right, (var, y))
    except ParseError:
        raise ParseError("Write the line as y = mx + b, or in point-slope form.") from None
    solved = sp.solve(sp.Eq(lhs.expr, rhs.expr), y)
    if len(solved) != 1 or solved[0].has(y):
        raise ParseError("Write the line as y = mx + b, or in point-slope form.")
    return sp.expand(solved[0]), f"{lhs.latex} = {rhs.latex}"


def _limit(text: str) -> tuple[Any, str, int]:
    word = re.sub(r"\s+", " ", _strip_lhs(text).strip().lower()).rstrip(".")
    if word in _LIMIT_WORDS:
        value = _LIMIT_WORDS[word]
        return value, (r"\text{DNE}" if value == DNE else tex(value)), 0
    return _number(text)


def limit_value(text: str) -> sp.Basic:
    """A limit's value as written: a number, ``oo``, ``-oo`` or :data:`DNE`."""
    return _limit(text)[0]


def read_answer(built, raw: str) -> Reading:
    """Read ``raw`` for ``built``. Raises ``ParseError`` with a message for the student."""
    if raw is None or not raw.strip():
        raise ParseError("Type an answer first.")
    kind = answer_kind(built)
    if kind == "number":
        value, latex, places = _number(raw, units=bool(built.params.get("word")))
        if value.free_symbols:
            raise ParseError("This asks for a number. Leave out the variables.")
        return Reading(value, latex, places)
    if kind == "values":
        values, latex, places = _values(raw)
        return Reading(values, latex, places)
    if kind == "limit":
        value, latex, places = _limit(raw)
        if isinstance(value, sp.Expr) and value not in (sp.oo, -sp.oo, DNE) and value.free_symbols:
            raise ParseError("A limit is a number, oo, -oo or DNE.")
        return Reading(value, latex, places)
    if kind == "line":
        value, latex = _line(raw, built.var)
        return Reading(value, latex)
    if kind == "antiderivative":
        has_constant = bool(_CONSTANT.search(raw))
        parsed = parse_answer(_CONSTANT.sub("", raw), answer_symbols(built))
        note = None if has_constant else "Remember the $+ C$: every antiderivative differs by a constant."
        return Reading(parsed.expr, parsed.latex + (" + C" if has_constant else ""), note=note)
    parsed = parse_answer(raw, answer_symbols(built))
    return Reading(parsed.expr, parsed.latex)


def preview(kind: str, text: str, symbols: tuple[sp.Symbol, ...], *, units: bool = False) -> str:
    """LaTeX for what the student typed, read the way the grader will read it. Raises ``ParseError``.

    ``units`` matches the grader: a word problem's number may end with a unit.
    """
    if not text.strip():
        raise ParseError("Type an answer first.")
    if kind == "number":
        return _number(text, units=units)[1]
    if kind == "values":
        return _values(text)[1]
    if kind == "limit":
        return _limit(text)[1]
    if kind == "line":
        return _line(text, symbols[0] if symbols else sp.Symbol("x"))[1]
    if kind == "antiderivative":
        has_constant = bool(_CONSTANT.search(text))
        return parse_answer(_CONSTANT.sub("", text), symbols).latex + (" + C" if has_constant else "")
    return parse_answer(text, symbols).latex


# --- comparing ---------------------------------------------------------------------------------


def _same_number(student: sp.Expr, key: sp.Expr, places: int) -> str | None:
    eq = equivalent(student, key, ())
    if eq.equal is True:
        return eq.method
    if eq.equal is None:
        return "numeric_agreement"
    if places and _rounded_match(student, key, places):
        return "rounded_decimal"
    return None


def matches(built, reading: Reading) -> str | None:
    """How ``reading`` was shown to equal the key, or ``None`` if it doesn't."""
    kind = answer_kind(built)
    key = built.key
    if kind == "number":
        return _same_number(reading.value, key, reading.places)
    if kind == "values":
        wanted = list(key)
        given = list(reading.value)
        if len(given) != len(wanted):
            return None
        unused = list(given)
        for value in wanted:
            hit = next((g for g in unused if _same_number(g, value, reading.places)), None)
            if hit is None:
                return None
            unused.remove(hit)
        return "same_values"
    if kind == "limit":
        if key in (sp.oo, -sp.oo, DNE) or reading.value in (sp.oo, -sp.oo, DNE):
            return "same_limit" if reading.value == key else None
        return _same_number(reading.value, key, reading.places)
    if kind == "antiderivative":
        derivative = sp.diff(reading.value, built.var)
        eq = equivalent(derivative, built.expr, (built.var,))
        return None if eq.equal is False else f"derivative_matches:{eq.method}"
    symbols = answer_symbols(built)
    eq = equivalent(reading.value, key, symbols)
    if eq.equal is False:
        return None
    return eq.method if eq.equal else "numeric_agreement"


# --- mistakes --------------------------------------------------------------------------------


def _mistake(tag: str, note: str, evidence: str) -> MistakeResult:
    kind = mistake_type(tag)
    return MistakeResult(tag=tag, label=kind.label, category=kind.category, step_id="answer", step_title="Answer",
                         where_to_look=note, evidence=evidence)


_UNCLASSIFIED = ("That isn't the answer, and it doesn't match a common mistake. "
                 "Open the first hint, then work through it again.")


def _tangent_x0(built) -> sp.Expr | None:
    spec = built.params.get("spec", {})
    text = str(spec.get("at") or "")
    if not text:
        return None
    part = next((p for p in re.split(r"[,;]", text) if p.strip().startswith(built.var.name)), text)
    try:
        return parse_answer(_strip_lhs(part), ()).expr
    except ParseError:
        return None


def classify(built, reading: Reading) -> MistakeResult:
    """The likeliest mistake behind a wrong answer to a material problem."""
    kind = answer_kind(built)
    key = built.key
    if kind == "values":
        given, wanted = list(reading.value), list(key)

        def contains(big: list, small: list) -> bool:
            return all(any(_same_number(s, b, reading.places) for b in big) for s in small)

        if len(given) < len(wanted) and contains(wanted, given):
            return _mistake("missed_value", "Some of your values are right, but there are more. "
                            "Check for factors you divided away and the whole interval.", "values:subset")
        if len(given) > len(wanted) and contains(given, wanted):
            return _mistake("extra_value", "All the right values are there, plus at least one that isn't an answer. "
                            "Check each one against the domain and the interval.", "values:superset")
        if given and len(given) == len(wanted) and contains(wanted, [-g for g in given]):
            return _mistake("sign_error", "Your values have the right size but the wrong signs.", "values:negated")
        return _mistake("unclassified", _UNCLASSIFIED, "none")
    if kind == "limit":
        value = reading.value
        if key == DNE and value not in (DNE,):
            return _mistake("one_sided_limit", "Compare the limit from the left with the limit from the right. "
                            "When they differ, the limit doesn't exist.", "limit:dne")
        if (key, value) in ((sp.oo, -sp.oo), (-sp.oo, sp.oo)) or (
                isinstance(value, sp.Expr) and finite_real(key) and value not in (sp.oo, -sp.oo, DNE)
                and key != 0 and _same_number(-value, key, reading.places)):
            return _mistake("sign_error", "Right size, wrong sign. Check the sign of each piece as you approach.",
                            "generic:sign")
        return _mistake("unclassified", _UNCLASSIFIED, "none")
    if kind == "number":
        if key != 0 and _same_number(-reading.value, key, reading.places):
            return _mistake("sign_error", "Right size, wrong sign. Check the direction: is that quantity "
                            "increasing or decreasing?", "generic:sign")
        return _mistake("unclassified", _UNCLASSIFIED, "none")
    if kind == "antiderivative":
        derivative = sp.diff(reading.value, built.var)
        symbols = (built.var,)
        if equivalent(derivative, -built.expr, symbols).equal is not False:
            return _mistake("sign_error", "Differentiate your answer: it gives the negative of the integrand.",
                            "generic:sign")
        ratio = constant_ratio(derivative, built.expr, symbols)
        if ratio is not None and ratio not in (1, -1):
            return _mistake("coefficient_slip", f"Differentiate your answer: it gives ${tex(ratio)}$ times the "
                            "integrand. Check the constant you divided or multiplied by.", "generic:ratio")
        if equivalent(reading.value, sp.diff(built.expr, built.var), symbols).equal is not False:
            return _mistake("unclassified", "That's the derivative of the integrand. An antiderivative goes the "
                            "other way: its derivative is the integrand.", "antiderivative:derivative")
        return _mistake("unclassified", "Differentiate your answer and compare it with the integrand.", "none")
    if kind == "line":
        symbols = (built.var,)
        slope = sp.diff(reading.value, built.var)
        right_slope = equivalent(slope, sp.diff(key, built.var), symbols).equal is not False
        x0 = _tangent_x0(built)
        through_point = x0 is not None and _same_number(reading.value.subs(built.var, x0), key.subs(built.var, x0), 0)
        if right_slope and not through_point:
            return _mistake("tangent_wrong_point", "The slope is right. Now make the line pass through the point on "
                            "the curve: find its $y$-value and use point-slope form.", "line:slope")
        if through_point and not right_slope:
            return _mistake("tangent_wrong_slope", "The line goes through the right point, but its slope should be "
                            "the derivative evaluated there.", "line:point")
        return _mistake("unclassified", _UNCLASSIFIED, "none")
    return _mistake("unclassified", _UNCLASSIFIED, "none")


# --- grading ---------------------------------------------------------------------------------


def grade_material(problem, raw: str) -> Grade:
    """Grade ``raw`` against a verified material problem whose answer isn't a plain derivative."""
    built = problem.built
    try:
        reading = read_answer(built, raw)
    except ParseError as exc:
        return Grade(status="invalid", message=str(exc))
    except (TypeError, ValueError, NotImplementedError):
        return Grade(status="invalid", message="I couldn't read that answer. Check it for typos.")
    method = matches(built, reading)
    normalized = sp.srepr(sp.sympify(reading.value) if not isinstance(reading.value, list)
                          else sp.FiniteSet(*reading.value))
    if method is not None:
        return Grade(status="correct", latex=reading.latex, method=method, normalized=normalized,
                     message=reading.note)
    return Grade(status="incorrect", latex=reading.latex, method="material", mistake=classify(built, reading),
                 normalized=normalized)
