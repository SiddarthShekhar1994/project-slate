"""Tests for the quotient rule skill (calc1.derivatives.quotient_rule).

The skill is loaded straight from its module so a broken sibling skill file
cannot break these tests.
"""

from __future__ import annotations

import json
from random import Random

import pytest
import sympy as sp
from slate_api.services.grading.grade import classify_mistake
from slate_api.services.verify import equivalent, verify_built
from slate_skills import load_skill_module
from slate_skills.core.mistakes import mistake_type
from slate_skills.core.text import render

SKILL = load_skill_module("calc1.derivatives.quotient_rule")

x, t = sp.symbols("x t")
S, C, E, L = sp.sin(x), sp.cos(x), sp.exp(x), sp.log(x)
R = sp.sqrt(x)


def build(family_id: str, params: dict):
    return SKILL.family(family_id).build(params)


def same(a: sp.Expr, b: sp.Expr, symbols=(x,)) -> bool:
    return equivalent(a, b, symbols).equal is True


def pattern(tag: str, note_contains: str = ""):
    """The one mistake pattern with ``tag`` whose note contains ``note_contains``."""
    found = [m for m in SKILL.mistakes if m.tag == tag and note_contains in m.note]
    assert len(found) == 1, f"expected one {tag} pattern matching {note_contains!r}, found {len(found)}"
    return found[0]


SWAPPED = pattern("quotient_numerator_swapped")
NOT_SQUARED = pattern("quotient_denominator_not_squared")
RATIO = pattern("quotient_as_derivative_ratio")
PLUS = pattern("quotient_plus_instead_of_minus")
TOP_ONLY = pattern("dropped_term")
PRODUCT = pattern("product_of_derivatives")
TRIG_SIGN = pattern("trig_derivative_sign")
LN_AS_ONE = pattern("exp_log_derivative_error", "ln")
EXP_AS_POWER = pattern("exp_log_derivative_error", "not a power")
SQRT_COEFFICIENT = pattern("power_coefficient_dropped")
CORE = (SWAPPED, NOT_SQUARED, RATIO, PLUS, TOP_ONLY)


# --- hand-checked keys ----------------------------------------------------------

SYMBOLIC_EXAMPLES = [
    # d1: (2x + 1)/(3x - 4): 2(3x - 4) - 3(2x + 1) = -11
    ("linear_over_linear", {"top": [2, 1], "bottom": [3, -4]}, -11 / (3 * x - 4) ** 2),
    # (3 - x)/(x + 2): -(x + 2) - (3 - x) = -5
    ("linear_over_linear", {"top": [-1, 3], "bottom": [1, 2]}, -5 / (x + 2) ** 2),
    # x^2/(x + 3): 2x(x + 3) - x^2
    ("power_over_linear", {"k": 1, "n": 2, "bottom": [1, 3]}, (x**2 + 6 * x) / (x + 3) ** 2),
    # 2x^3/(x - 2): 6x^2(x - 2) - 2x^3
    ("power_over_linear", {"k": 2, "n": 3, "bottom": [1, -2]}, (4 * x**3 - 12 * x**2) / (x - 2) ** 2),
    # d2: (2x + 3)/(x^2 + 1): 2(x^2 + 1) - (2x + 3)(2x)
    ("poly_over_quadratic", {"top": ["poly", [2, 3]], "bottom": ["poly", [1, 0, 1]]},
     (-2 * x**2 - 6 * x + 2) / (x**2 + 1) ** 2),
    # x^2/(x^2 + 4): 2x(x^2 + 4) - x^2(2x) = 8x
    ("poly_over_quadratic", {"top": ["mono", 1, 2], "bottom": ["poly", [1, 0, 4]]}, 8 * x / (x**2 + 4) ** 2),
    # sin x / x
    ("trig_over_x", {"top": ["fn", 0, 1, "sin"], "bottom": ["mono", 1, 1]}, (x * C - S) / x**2),
    # 2 cos x / x^2: (-2 sin x x^2 - 2 cos x 2x)/x^4, cancel an x
    ("trig_over_x", {"top": ["fn", 0, 2, "cos"], "bottom": ["mono", 1, 2]}, (-2 * x * S - 4 * C) / x**3),
    # cos x / (x + 2)
    ("trig_over_x", {"top": ["fn", 0, 1, "cos"], "bottom": ["poly", [1, 2]]}, (-(x + 2) * S - C) / (x + 2) ** 2),
    # e^x/(2x + 1): e^x(2x + 1) - 2e^x
    ("exp_over_linear", {"k": 1, "bottom": [2, 1]}, (2 * x - 1) * E / (2 * x + 1) ** 2),
    # d3: ln x / x
    ("ln_over_power", {"c": 0, "a": 1, "n": 1}, (1 - L) / x**2),
    # (ln x + 2)/x^3: (x^2 - 3x^2(ln x + 2))/x^6 = (1 - 3 ln x - 6)/x^4
    ("ln_over_power", {"c": 2, "a": 1, "n": 3}, (-5 - 3 * L) / x**4),
    # sin x / cos x = tan x
    ("trig_ratio", {"top": ["fn", 0, 1, "sin"], "bottom": ["fn", 0, 1, "cos"]}, 1 / C**2),
    # sin x/(1 + cos x): cos x + cos^2 x + sin^2 x = 1 + cos x on top
    ("trig_ratio", {"top": ["fn", 0, 1, "sin"], "bottom": ["fn", 1, 1, "cos"]}, 1 / (1 + C)),
    # cos x/(2 + sin x): -sin x(2 + sin x) - cos^2 x = -2 sin x - 1
    ("trig_ratio", {"top": ["fn", 0, 1, "cos"], "bottom": ["fn", 2, 1, "sin"]}, -(2 * S + 1) / (2 + S) ** 2),
    # (x^2 - 1)/(x^2 + 1): 2x(x^2 + 1) - (x^2 - 1)2x = 4x
    ("quadratic_over_quadratic", {"top": [1, 0, -1], "bottom": [1, 0, 1]}, 4 * x / (x**2 + 1) ** 2),
    ("quadratic_over_quadratic", {"top": [2, 1, -5], "bottom": [1, 4, 2]},
     (7 * x**2 + 18 * x + 22) / (x**2 + 4 * x + 2) ** 2),
    # d4: x e^x/(x + 1): (x + 1)^2 e^x - x e^x
    ("product_over_poly", {"top": ["prod", 1, 1, "exp"], "bottom": ["poly", [1, 1]]},
     (x**2 + x + 1) * E / (x + 1) ** 2),
    # x sin x/(x + 2): (sin x + x cos x)(x + 2) - x sin x
    ("product_over_poly", {"top": ["prod", 1, 1, "sin"], "bottom": ["poly", [1, 2]]},
     (2 * S + (x**2 + 2 * x) * C) / (x + 2) ** 2),
    # x^2 ln x/(x^2 + 1): (2x ln x + x)(x^2 + 1) - 2x^3 ln x
    ("product_over_poly", {"top": ["prod", 1, 2, "ln"], "bottom": ["poly", [1, 0, 1]]},
     (2 * x * L + x**3 + x) / (x**2 + 1) ** 2),
    # sqrt x/(x + 4): (x + 4)/(2 sqrt x) - sqrt x = (4 - x)/(2 sqrt x)
    ("sqrt_quotient", {"top": ["root", 1, 0], "bottom": ["poly", [1, 4]]}, (4 - x) / (2 * R * (x + 4) ** 2)),
    # sqrt x/(x^2 + 3): (x^2 + 3)/(2 sqrt x) - 2x sqrt x = (3 - 3x^2)/(2 sqrt x)
    ("sqrt_quotient", {"top": ["root", 1, 0], "bottom": ["poly", [1, 0, 3]]},
     (3 - 3 * x**2) / (2 * R * (x**2 + 3) ** 2)),
    # (x + 1)/(sqrt x + 1): (sqrt x + 1) - (x + 1)/(2 sqrt x) = (x + 2 sqrt x - 1)/(2 sqrt x)
    ("sqrt_quotient", {"top": ["poly", [1, 1]], "bottom": ["root", 1, 1]},
     (x + 2 * R - 1) / (2 * R * (R + 1) ** 2)),
]


@pytest.mark.parametrize("family_id,params,expected", SYMBOLIC_EXAMPLES)
def test_symbolic_keys(family_id, params, expected):
    built = build(family_id, params)
    assert built.at is None and built.word is None
    assert same(built.key, expected), f"{family_id}: key {built.key} != {expected}"
    assert verify_built(SKILL, built).ok


POINT_EXAMPLES = [
    # c = 5t/(t^2 + 4) at t = 1: (5 * 5 - 5 * 2)/25
    ("word_concentration", {"a": 5, "b": 4, "t0": 1}, t, 1, sp.Rational(3, 5)),
    # c = 6t/(t^2 + 2) at t = 2: (6 * 6 - 12 * 4)/36, past the peak so falling
    ("word_concentration", {"a": 6, "b": 2, "t0": 2}, t, 2, sp.Rational(-1, 3)),
    # A = (2x^2 + 40x + 800)/x at x = 10: (80 * 10 - 1400)/100
    ("word_average_cost", {"cost": [2, 40, 800], "x0": 10}, x, 10, -6),
    # A = (x^2 + 50x + 1500)/x at x = 50: (150 * 50 - 5500)/2500
    ("word_average_cost", {"cost": [1, 50, 1500], "x0": 50}, x, 50, sp.Rational(2, 5)),
    # P = 800 e^t/(3 + e^t) at t = 0: (800 * 4 - 800 * 1)/16
    ("word_population", {"a": 800, "b": 3, "when": "zero"}, t, 0, 150),
    # at t = ln 3: (2400 * 6 - 2400 * 3)/36
    ("word_population", {"a": 800, "b": 3, "when": "ln"}, t, sp.log(3), 200),
]


@pytest.mark.parametrize("family_id,params,var,point,expected", POINT_EXAMPLES)
def test_point_keys(family_id, params, var, point, expected):
    built = build(family_id, params)
    assert built.word is not None and built.var == var
    assert built.at == {var: point}
    assert built.key == expected
    assert built.steps[-1].id == "evaluate" and built.steps[-1].expr == expected
    assert verify_built(SKILL, built).ok


def test_population_point_reads_as_ln():
    built = build("word_population", {"a": 800, "b": 3, "when": "ln"})
    assert r"t = \ln 3" in built.word.question
    assert built.steps[-1].title == r"Evaluate at $t = \ln 3$"


def test_difficulty_coverage():
    for d in (1, 2, 3, 4):
        assert len(SKILL.families_at(d, word=False)) >= 2, d
    assert {f.id for f in SKILL.families if f.word} == {"word_concentration", "word_average_cost",
                                                          "word_population"}


# --- what the student sees ---------------------------------------------------------


def test_prompt_is_a_single_fraction():
    built = build("linear_over_linear", {"top": [2, 1], "bottom": [3, -4]})
    assert built.prompt == r"Differentiate $y = \frac{2 x + 1}{3 x - 4}$."
    built = build("product_over_poly", {"top": ["prod", 1, 1, "exp"], "bottom": ["poly", [1, 1]]})
    assert built.prompt == r"Differentiate $y = \frac{x e^{x}}{x + 1}$."
    assert built.parts["f"] == x * E and built.parts["g"] == x + 1


@pytest.mark.parametrize("family_id,params", [
    # 2x + 4 over x + 2 cancels to 2.
    ("linear_over_linear", {"top": [2, 4], "bottom": [1, 2]}),
    # 2x + 4 over 4x + 6 shares the factor 2.
    ("linear_over_linear", {"top": [2, 4], "bottom": [4, 6]}),
    # x over x^2 + 3x shares the factor x.
    ("poly_over_quadratic", {"top": ["mono", 1, 1], "bottom": ["poly", [1, 3, 0]]}),
    # 2 e^x over 2x + 4 shares the factor 2.
    ("exp_over_linear", {"k": 2, "bottom": [2, 4]}),
])
def test_common_factors_are_rejected(family_id, params):
    with pytest.raises(ValueError):
        build(family_id, params)


def test_zero_rate_is_rejected():
    # c = 5t/(t^2 + 4) peaks at t = 2.
    with pytest.raises(ValueError):
        build("word_concentration", {"a": 5, "b": 4, "t0": 2})


def test_point_problems_with_coinciding_mistakes_are_rejected():
    # c = 5t/(t^2 + 2) at t = 1: f'/g = 5/3 and (f'g - fg')/g = 5/3 as well.
    with pytest.raises(ValueError):
        build("word_concentration", {"a": 5, "b": 2, "t0": 1})
    # P = 4 m e^t/(1 + e^t): f'/g and (f'g - fg')/g are the same function.
    with pytest.raises(ValueError):
        build("word_population", {"a": 40, "b": 1, "when": "zero"})


def test_steps_walk_the_rule():
    built = build("poly_over_quadratic", {"top": ["poly", [2, 3]], "bottom": ["poly", [1, 0, 1]]})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "assemble", "simplify"]
    identify, differentiate, assemble, simplify = built.steps
    assert r"f(x) = \htmlClass{slate-yellow}{2 x + 3}" in identify.latex
    assert r"g(x) = \htmlClass{slate-mint}{x^{2} + 1}" in identify.latex
    assert r"f'(x) = \htmlClass{slate-yellow}{2}" in differentiate.latex
    assert r"g'(x) = \htmlClass{slate-mint}{2 x}" in differentiate.latex
    assert assemble.latex.startswith(r"\frac{dy}{dx} = \frac{f' g - f g'}{g^{2}} = ")
    assert r"\left(\htmlClass{slate-mint}{x^{2} + 1}\right)^{2}" in assemble.latex
    assert same(assemble.expr, built.key) and simplify.expr == built.key

    built = build("word_concentration", {"a": 5, "b": 4, "t0": 1})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "assemble", "simplify", "evaluate"]
    assert built.steps[2].latex.startswith("c'(t) = ")
    assert built.steps[-1].latex.endswith(r"= \frac{3}{5}")


def test_step_titles_follow_the_family():
    def titles(b):
        return [s.title for s in b.steps]

    product = build("product_over_poly", {"top": ["prod", 1, 1, "exp"], "bottom": ["poly", [1, 1]]})
    assert "product rule" in titles(product)[1]
    ratio = build("trig_ratio", {"top": ["fn", 0, 1, "sin"], "bottom": ["fn", 0, 1, "cos"]})
    assert r"\sin^2 x + \cos^2 x = 1" in titles(ratio)[3]
    power = build("ln_over_power", {"c": 2, "a": 1, "n": 3})
    assert titles(power)[3] == "Cancel the common power of $x$"


def test_hints():
    built = build("product_over_poly", {"top": ["prod", 1, 1, "sin"], "bottom": ["poly", [1, 2]]})
    ladder = SKILL.hint_ladder(built)
    assert ladder.nudge.endswith("?") and "$" not in ladder.nudge
    bigger = render(ladder.bigger, built)
    assert r"\htmlClass{slate-yellow}{x \sin{\left(x \right)}}" in bigger and "product rule" in bigger
    assert render(ladder.full_step, built) == f"${built.steps[2].latex}$"

    word = build("word_average_cost", {"cost": [2, 40, 800], "x0": 10})
    ladder = SKILL.hint_ladder(word)
    assert "average cost" in ladder.nudge
    assert ladder.bigger.endswith("Then evaluate at $x = 10$.")


# --- mistake patterns -------------------------------------------------------------


def test_mistake_tags_exist_and_notes_render():
    signature = {m.tag for m in SKILL.mistakes if m.signature}
    assert signature == {"quotient_numerator_swapped", "quotient_denominator_not_squared"}
    for family_id, params, _ in SYMBOLIC_EXAMPLES[:1] + SYMBOLIC_EXAMPLES[-1:]:
        built = build(family_id, params)
        for m in SKILL.mistakes:
            mistake_type(m.tag)
            assert m.step in {s.id for s in built.steps}
            text = render(m.note, built)
            assert "[[" not in text and "—" not in text  # no em dashes


def test_core_mistakes_on_linear_over_linear():
    # (2x + 1)/(3x - 4), key -11/(3x - 4)^2
    built = build("linear_over_linear", {"top": [2, 1], "bottom": [3, -4]})
    g = 3 * x - 4
    assert same(SWAPPED.buggy(built), 11 / g**2)
    assert same(NOT_SQUARED.buggy(built), -11 / g)
    assert same(RATIO.buggy(built), sp.Rational(2, 3))
    assert same(PLUS.buggy(built), (12 * x - 5) / g**2)  # 2(3x - 4) + (2x + 1) 3
    assert same(TOP_ONLY.buggy(built), 2 / g)
    for m in (PRODUCT, TRIG_SIGN, LN_AS_ONE, EXP_AS_POWER, SQRT_COEFFICIENT):
        assert m.buggy(built) is None, m.tag


def test_swapped_numerator_is_the_negative_of_the_key():
    for family_id, params, _ in SYMBOLIC_EXAMPLES:
        built = build(family_id, params)
        assert same(SWAPPED.buggy(built), -built.key), family_id


def test_core_mistakes_on_a_quadratic_bottom():
    # (2x + 3)/(x^2 + 1)
    built = build("poly_over_quadratic", {"top": ["poly", [2, 3]], "bottom": ["poly", [1, 0, 1]]})
    g = x**2 + 1
    assert same(NOT_SQUARED.buggy(built), (-2 * x**2 - 6 * x + 2) / g)
    assert same(RATIO.buggy(built), 1 / x)  # 2 / (2x)
    assert same(PLUS.buggy(built), (6 * x**2 + 6 * x + 2) / g**2)  # 2(x^2 + 1) + (2x + 3) 2x
    assert same(TOP_ONLY.buggy(built), 2 / g)


def test_trig_derivative_sign():
    # cos x / x with (cos x)' taken as sin x.
    built = build("trig_over_x", {"top": ["fn", 0, 1, "cos"], "bottom": ["mono", 1, 1]})
    assert same(built.key, (-x * S - C) / x**2)
    assert same(TRIG_SIGN.buggy(built), (x * S - C) / x**2)
    # sin x / x with (sin x)' taken as -cos x.
    built = build("trig_over_x", {"top": ["fn", 0, 1, "sin"], "bottom": ["mono", 1, 1]})
    assert same(TRIG_SIGN.buggy(built), (-x * C - S) / x**2)
    # cos x/(2 + sin x): only the top has a cos.
    built = build("trig_ratio", {"top": ["fn", 0, 1, "cos"], "bottom": ["fn", 2, 1, "sin"]})
    assert same(TRIG_SIGN.buggy(built), (2 * S + S**2 - C**2) / (2 + S) ** 2)
    assert TRIG_SIGN.buggy(build("exp_over_linear", {"k": 1, "bottom": [2, 1]})) is None


def test_plus_defers_to_the_trig_slip_when_they_agree():
    # sin x / cos x: adding the terms and flipping (cos x)' both give (cos^2 x - sin^2 x)/cos^2 x.
    built = build("trig_ratio", {"top": ["fn", 0, 1, "sin"], "bottom": ["fn", 0, 1, "cos"]})
    assert PLUS.buggy(built) is None
    assert same(TRIG_SIGN.buggy(built), (C**2 - S**2) / C**2)
    assert same(SWAPPED.buggy(built), -1 / C**2)
    assert same(RATIO.buggy(built), -C / S)
    assert same(TOP_ONLY.buggy(built), sp.Integer(1))
    # With the cos on top the two slips differ, so both patterns apply.
    built = build("trig_ratio", {"top": ["fn", 0, 1, "cos"], "bottom": ["fn", 2, 1, "sin"]})
    assert same(PLUS.buggy(built), (-S * (2 + S) + C**2) / (2 + S) ** 2)


def test_exp_and_log_derivative_errors():
    # ln x / x^2 with (ln x)' taken as 1: (x^2 - 2x ln x)/x^4
    built = build("ln_over_power", {"c": 0, "a": 1, "n": 2})
    assert same(LN_AS_ONE.buggy(built), (x - 2 * L) / x**3)
    assert EXP_AS_POWER.buggy(built) is None
    # e^x/(2x + 1) with (e^x)' taken as x e^(x - 1)
    built = build("exp_over_linear", {"k": 1, "bottom": [2, 1]})
    assert same(EXP_AS_POWER.buggy(built), (x * sp.exp(x - 1) * (2 * x + 1) - 2 * E) / (2 * x + 1) ** 2)
    assert LN_AS_ONE.buggy(built) is None


def test_product_of_derivatives_in_the_top():
    # x e^x/(x + 1) with (x e^x)' taken as 1 * e^x
    built = build("product_over_poly", {"top": ["prod", 1, 1, "exp"], "bottom": ["poly", [1, 1]]})
    assert same(PRODUCT.buggy(built), E / (x + 1) ** 2)
    # x sin x/(x + 2) with (x sin x)' taken as cos x
    built = build("product_over_poly", {"top": ["prod", 1, 1, "sin"], "bottom": ["poly", [1, 2]]})
    assert same(PRODUCT.buggy(built), (C * (x + 2) - x * S) / (x + 2) ** 2)
    assert same(TRIG_SIGN.buggy(built), ((S - x * C) * (x + 2) - x * S) / (x + 2) ** 2)
    assert PRODUCT.buggy(build("trig_over_x", {"top": ["fn", 0, 1, "sin"], "bottom": ["mono", 1, 1]})) is None


def test_sqrt_coefficient_dropped():
    # sqrt x/(x + 4) with (sqrt x)' taken as 1/sqrt x: (x + 4)/sqrt x - sqrt x = 4/sqrt x
    built = build("sqrt_quotient", {"top": ["root", 1, 0], "bottom": ["poly", [1, 4]]})
    assert same(SQRT_COEFFICIENT.buggy(built), 4 / (R * (x + 4) ** 2))
    # (x + 1)/(sqrt x + 1) with the slip on the bottom
    built = build("sqrt_quotient", {"top": ["poly", [1, 1]], "bottom": ["root", 1, 1]})
    assert same(SQRT_COEFFICIENT.buggy(built), (R + 1 - (x + 1) / R) / (R + 1) ** 2)
    assert SQRT_COEFFICIENT.buggy(build("trig_over_x", {"top": ["fn", 0, 1, "sin"], "bottom": ["mono", 1, 1]})) is None


def test_point_problem_mistakes_are_numbers():
    # c = 5t/(t^2 + 4) at t = 1: f = 5, f' = 5, g = 5, g' = 2.
    built = build("word_concentration", {"a": 5, "b": 4, "t0": 1})
    expected = {SWAPPED: sp.Rational(-3, 5), NOT_SQUARED: 3, RATIO: sp.Rational(5, 2), PLUS: sp.Rational(7, 5),
                TOP_ONLY: 1}
    for m, value in expected.items():
        assert m.buggy(built) == value, m.tag

    # A = (2x^2 + 40x + 800)/x at x = 10: f = 1400, f' = 80, g = 10, g' = 1.
    built = build("word_average_cost", {"cost": [2, 40, 800], "x0": 10})
    expected = {SWAPPED: 6, NOT_SQUARED: -60, RATIO: 80, PLUS: 22, TOP_ONLY: 8}
    for m, value in expected.items():
        assert m.buggy(built) == value, m.tag

    # P = 800 e^t/(3 + e^t) at t = 0: f = f' = 800, g = 4, g' = 1.
    built = build("word_population", {"a": 800, "b": 3, "when": "zero"})
    expected = {SWAPPED: -150, NOT_SQUARED: 600, RATIO: 800, PLUS: 250, TOP_ONLY: 200}
    for m, value in expected.items():
        assert m.buggy(built) == value, m.tag
    # The e^t slip makes both derivatives zero at t = 0; a zero answer is not blamed on it.
    assert EXP_AS_POWER.buggy(built) is None
    # At t = ln 3 it gives (2400 ln 3/e * 6 - 2400 * 3 ln 3/e)/36.
    built = build("word_population", {"a": 800, "b": 3, "when": "ln"})
    assert same(EXP_AS_POWER.buggy(built), 200 * sp.log(3) / sp.E, ())


def test_grader_names_each_mistake():
    problems = [
        build("linear_over_linear", {"top": [2, 1], "bottom": [3, -4]}),
        build("trig_ratio", {"top": ["fn", 0, 1, "cos"], "bottom": ["fn", 2, 1, "sin"]}),
        build("product_over_poly", {"top": ["prod", 1, 1, "sin"], "bottom": ["poly", [1, 2]]}),
        build("sqrt_quotient", {"top": ["root", 1, 0], "bottom": ["poly", [1, 4]]}),
        build("word_average_cost", {"cost": [2, 40, 800], "x0": 10}),
    ]
    for built in problems:
        for m in SKILL.mistakes:
            wrong = m.buggy(built)
            if wrong is None:
                continue
            result = classify_mistake(SKILL, built, wrong)
            assert result.evidence == f"pattern:{m.tag}@{m.step}", (built.family, m.tag, result.evidence)


# --- sweep ------------------------------------------------------------------------


@pytest.mark.parametrize("family", SKILL.families, ids=lambda f: f.id)
def test_family_sweep(family):
    for seed in range(40):
        params = family.sample(Random(seed))
        # Parameters are stored with the problem, so they must survive JSON.
        stored = json.loads(json.dumps(params))
        built = family.build(stored)
        assert built.family == family.id and built.difficulty == family.difficulty
        report = verify_built(SKILL, built)
        assert report.ok, f"{family.id} seed {seed}: {[(c.name, c.detail) for c in report.failures]}"
        # build is a pure function of the stored params.
        again = family.build(json.loads(json.dumps(built.params)))
        assert again.key == built.key and again.prompt == built.prompt
