import time

import pytest
import sympy as sp

from slate_api.services.verify import ParseError, parse_answer

x, y, t = sp.symbols("x y t")
E = sp.E


def parsed(text, symbols=(x,)):
    return parse_answer(text, symbols).expr


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3x^2", 3 * x**2),
        ("3x**2", 3 * x**2),
        ("2x^2 + 3x - 1", 2 * x**2 + 3 * x - 1),
        ("x^-1", 1 / x),
        ("-3x^-2", -3 / x**2),
        ("x^(1/2)", sp.sqrt(x)),
        ("x^(-1/2)", 1 / sp.sqrt(x)),
        ("sqrt(x)", sp.sqrt(x)),
        ("1/(2sqrt(x))", 1 / (2 * sp.sqrt(x))),
        ("cbrt(x^2)", (x**2) ** sp.Rational(1, 3)),
        ("x^2/3", x**2 / 3),
        ("3/(2x)", 3 / (2 * x)),
        ("1/2x", x / 2),
        ("2(x+1)", 2 * (x + 1)),
        ("(x+1)(x-1)", (x + 1) * (x - 1)),
        ("x(x+1)", x * (x + 1)),
        ("3x^2cos(x^3+1)", 3 * x**2 * sp.cos(x**3 + 1)),
        ("-3sin(3x)e^(cos(3x))", -3 * sp.sin(3 * x) * sp.exp(sp.cos(3 * x))),
        ("sin x", sp.sin(x)),
        ("sin 2x", sp.sin(2 * x)),
        ("sin x^2", sp.sin(x**2)),
        ("sin x cos x", sp.sin(x) * sp.cos(x)),
        ("2sinxcosx", 2 * sp.sin(x) * sp.cos(x)),
        ("sin^2(x)", sp.sin(x) ** 2),
        ("cos^2 x", sp.cos(x) ** 2),
        ("sin(x)^2", sp.sin(x) ** 2),
        ("sec^2(3x)", sp.sec(3 * x) ** 2),
        ("e^x", sp.exp(x)),
        ("e^-x", sp.exp(-x)),
        ("5e^(2x)", 5 * sp.exp(2 * x)),
        ("e^2x", E**2 * x),
        ("exp(x^2)", sp.exp(x**2)),
        ("ln(x^2+1)", sp.log(x**2 + 1)),
        ("log x", sp.log(x)),
        ("2pi x", 2 * sp.pi * x),
        ("0.5x", x / 2),
        ("1.25", sp.Rational(5, 4)),
        ("arctan(x)", sp.atan(x)),
        ("abs(x)", sp.Abs(x)),
        ("x^2^3", x ** (2**3)),
        ("-x^2", -(x**2)),
        ("[x+1]*{x-1}", (x + 1) * (x - 1)),
    ],
)
def test_parses_what_students_mean(text, expected):
    assert sp.simplify(parsed(text) - expected) == 0


@pytest.mark.parametrize(
    "text, expected",
    [
        ("x²", x**2),
        ("3x²+2x", 3 * x**2 + 2 * x),
        ("x⁻¹", 1 / x),
        ("x⁻²", x**-2),
        ("x³·cos(x²)", x**3 * sp.cos(x**2)),
        ("x¹⁰", x**10),
        ("sin²x", sp.sin(x) ** 2),
        ("√x", sp.sqrt(x)),
        ("√(x+1)", sp.sqrt(x + 1)),
        ("2π", 2 * sp.pi),
        ("x × 3", 3 * x),
        ("6 ÷ x", 6 / x),
        ("−x", -x),
        ("½x", x / 2),
        ("x + 1", x + 1),
    ],
)
def test_unicode_input(text, expected):
    assert sp.simplify(parsed(text) - expected) == 0


@pytest.mark.parametrize(
    "text, expected",
    [
        ("f'(x) = 6x", 6 * x),
        ("y' = -x/y", -x / y),
        ("dy/dx = -x/y", -x / y),
        ("dy/dx=(2y-x^2)/(y^2-2x)", (2 * y - x**2) / (y**2 - 2 * x)),
    ],
)
def test_leading_left_hand_side_is_ignored(text, expected):
    assert sp.simplify(parsed(text, (x, y)) - expected) == 0


def test_variables_are_limited_to_the_problem():
    assert parsed("x y", (x, y)) == x * y
    assert parsed("xy", (x, y)) == x * y
    with pytest.raises(ParseError, match="can use x"):
        parse_answer("3y", (x,))
    assert parsed("2t+1", (t,)) == 2 * t + 1


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "Type an answer"),
        ("   ", "Type an answer"),
        ("abc", "'a' isn't something I recognise"),
        ("x^", "ends with \\^"),
        ("(x+1", "never closed"),
        ("x+1)", "nothing to close"),
        ("|x|", "abs"),
        ("3x = 6", "equals sign"),
        ("1/0", "divides by zero"),
        ("2 3", "Two numbers"),
        ("3,5", "Commas"),
        ("sin", "needs something to act on"),
        ("x @ 2", "can't read the character"),
    ],
)
def test_errors_are_explained(text, message):
    with pytest.raises(ParseError, match=message):
        parse_answer(text, (x,))


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('true')",
        "x.__class__",
        "lambda: 1",
        "exec('1')",
        "x; import os",
        "eval(x)",
        "getattr(x, 'y')",
        "S('x')",
    ],
)
def test_code_injection_is_rejected(text):
    with pytest.raises(ParseError):
        parse_answer(text, (x,))


@pytest.mark.parametrize(
    "text",
    ["9^9^9^9", "2^(2^(2^10))", "x^1000", "99999999999", "(" * 60 + "x" + ")" * 60, "x+" * 200 + "x"],
)
def test_expensive_inputs_are_refused_quickly(text):
    start = time.perf_counter()
    with pytest.raises(ParseError):
        parse_answer(text, (x,))
    assert time.perf_counter() - start < 0.5


def test_display_keeps_what_was_typed():
    p = parse_answer("2*3x", (x,))
    assert p.expr == 6 * x
    assert p.latex == r"2 \cdot 3 x"
    assert parse_answer("dy/dx = -x/y", (x, y)).latex == r"- \frac{x}{y}"
    assert parse_answer("x^-1", (x,)).latex == r"\frac{1}{x}"
    assert parse_answer("e^2x", (x,)).latex == r"e^{2} x"


def test_decimal_places_are_reported():
    p = parse_answer("3.14", ())
    assert p.has_decimal and p.decimal_places == 2
    assert not parse_answer("3", ()).has_decimal
