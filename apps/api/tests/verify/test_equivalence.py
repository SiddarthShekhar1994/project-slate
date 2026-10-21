import time

import pytest
import sympy as sp

from slate_api.services.verify import constant_ratio, equivalent

x, y = sp.symbols("x y")


@pytest.mark.parametrize(
    "a, b",
    [
        (3 * x**2 * sp.cos(x**3 + 1), sp.cos(x**3 + 1) * 3 * x**2),
        (2 * x * (x**2 + 1) ** 3 * 4, 8 * x * (x**2 + 1) ** 3),
        (4 * (4 * x + 1) * (2 * x**2 + x - 5) ** 3, sp.expand(4 * (4 * x + 1) * (2 * x**2 + x - 5) ** 3)),
        (6 * x * sp.sec(3 * x**2 + 1) ** 2, 6 * x * (sp.tan(3 * x**2 + 1) ** 2 + 1)),
        (6 * x * sp.sec(3 * x**2 + 1) ** 2, 6 * x / sp.cos(3 * x**2 + 1) ** 2),
        (4 * sp.sin(2 * x) * sp.cos(2 * x), 2 * sp.sin(4 * x)),
        (1 / (2 * sp.sqrt(x)), sp.sqrt(x) / (2 * x)),
        (x ** sp.Rational(-1, 2), 1 / sp.sqrt(x)),
        ((x**2 - 1) / (x - 1), x + 1),
        (sp.exp(2 * x) * sp.exp(x), sp.exp(3 * x)),
        (sp.cos(x) ** 2 - sp.sin(x) ** 2, sp.cos(2 * x)),
        (sp.sec(x) * sp.tan(x), sp.sin(x) / sp.cos(x) ** 2),
        (sp.csc(x) ** 2 - sp.cot(x) ** 2, sp.Integer(1)),
        (2 * x / (x**2 + 1), sp.diff(sp.log(x**2 + 1), x)),
        # Equal on the key's real domain (x > 0), not under SymPy's complex branches.
        ((x**2) ** sp.Rational(1, 3), x ** sp.Rational(2, 3)),
        (sp.sqrt(1 / x), 1 / sp.sqrt(x)),
        (x * sp.log(x**2) / 2 + x, x * sp.log(x) + x),
        (2 / (3 * sp.cbrt(x)), sp.Rational(2, 3) * x ** sp.Rational(-1, 3)),
    ],
)
def test_equal_forms_are_proven(a, b):
    result = equivalent(a, b, (x,))
    assert result.equal is True, result


@pytest.mark.parametrize(
    "a, b",
    [
        (3 * x**2 * sp.cos(x**3 + 1), sp.cos(x**3 + 1)),
        (3 * x**2 * sp.cos(x**3 + 1), -3 * x**2 * sp.cos(x**3 + 1)),
        (2 * x, 2 * x + 1),
        (sp.sqrt(x**2), x),
        # x is real everywhere, so |x| must match it at negative points too.
        (sp.Abs(x), x),
        (sp.sec(x) ** 2, sp.tan(x) ** 2),
        (sp.sin(x) / x, sp.Integer(1)),
        (x**3 - x, sp.Integer(0)),
        # Agree at x = 0 and x = 1 and x = -1 only.
        (x**3, x),
    ],
)
def test_different_expressions_are_rejected(a, b):
    result = equivalent(a, b, (x,))
    assert result.equal is False, result


def test_most_wrong_answers_are_rejected_numerically():
    result = equivalent(sp.cos(x**3 + 1), 3 * x**2 * sp.cos(x**3 + 1), (x,))
    assert result.method == "numeric_counterexample"


def test_constants_compare_without_symbols():
    assert equivalent(sp.Rational(1, 2), sp.Float("0.5"), ()).equal is True
    assert equivalent(sp.sqrt(8), 2 * sp.sqrt(2), ()).equal is True
    assert equivalent(sp.Integer(54), sp.Integer(55), ()).equal is False


CIRCLE = x**2 + y**2 - 25
FOLIUM = x**3 + y**3 - 6 * x * y


def test_implicit_answers_compare_on_the_curve():
    key = -x / y
    assert equivalent(-x / y, key, (x, y), constraint=CIRCLE).equal is True
    # x/y differs from -x/y everywhere on the circle except y-axis crossings.
    assert equivalent(x / y, key, (x, y), constraint=CIRCLE).equal is False


def test_forms_equal_only_on_the_curve_are_accepted():
    key = -sp.diff(FOLIUM, x) / sp.diff(FOLIUM, y)
    student = (2 * y - x**2) / (y**2 - 2 * x)
    assert equivalent(student, key, (x, y), constraint=FOLIUM).equal is True
    # On the circle, x^2/y^2 = (25 - y^2)/y^2, so these agree only on the curve.
    a = x**2 / y**2
    b = (25 - y**2) / y**2
    assert equivalent(a, b, (x, y)).equal is False
    result = equivalent(a, b, (x, y), constraint=CIRCLE)
    assert result.equal is True
    assert result.method == "constraint_reduction"


def test_wrong_implicit_answer_is_rejected_on_the_curve():
    key = -sp.diff(FOLIUM, x) / sp.diff(FOLIUM, y)
    wrong = (2 * y + x**2) / (y**2 - 2 * x)
    assert equivalent(wrong, key, (x, y), constraint=FOLIUM).equal is False


def test_constant_ratio():
    assert constant_ratio(6 * x * sp.cos(x**2), 3 * x * sp.cos(x**2), (x,)) == 2
    assert constant_ratio(2 * x * (sp.tan(x**2) ** 2 + 1), 8 * x * sp.sec(x**2) ** 2, (x,)) == sp.Rational(1, 4)
    assert constant_ratio(x**2, x, (x,)) is None


def test_typical_comparisons_are_fast():
    start = time.perf_counter()
    for _ in range(20):
        equivalent(3 * x**2 * sp.cos(x**3 + 1), sp.cos(x**3 + 1), (x,))
    assert (time.perf_counter() - start) / 20 < 0.05
