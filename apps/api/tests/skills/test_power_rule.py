"""Tests for the power rule skill (calc1.derivatives.power_rule).

The skill is loaded straight from its module so a broken sibling skill file
cannot break these tests.
"""

from __future__ import annotations

import json
from random import Random

import pytest
import sympy as sp
from slate_api.services.verify import equivalent, verify_built
from slate_skills import load_skill_module
from slate_skills.core.mistakes import mistake_type

SKILL = load_skill_module("calc1.derivatives.power_rule")

x, t, r, s, q = sp.symbols("x t r s q")
half = sp.Rational(1, 2)


def build(family_id: str, params: dict):
    return SKILL.family(family_id).build(params)


def same(a: sp.Expr, b: sp.Expr, symbols=(x,)) -> bool:
    return equivalent(a, b, symbols).equal is True


def wrong_answers(built, tag: str) -> list[sp.Expr]:
    """Answers from every pattern with ``tag`` that applies to this problem."""
    return [w for m in SKILL.mistakes if m.tag == tag and (w := m.buggy(built)) is not None]


# --- hand-checked keys ----------------------------------------------------------

SYMBOLIC_EXAMPLES = [
    # d1
    ("single_power", {"terms": [[5, 3]]}, 15 * x**2),
    ("polynomial", {"terms": [[3, 4], [-5, 2], [7, 0]]}, 12 * x**3 - 10 * x),
    # d2: 2x^3 - 5x^-2 + 4 and 4x^(1/2) + 3x^2
    ("negative_powers", {"terms": [[2, 3], [-5, -2], [4, 0]]}, 6 * x**2 + 10 / x**3),
    ("square_root", {"terms": [[4, "1/2"], [3, 2]]}, 2 / sp.sqrt(x) + 6 * x),
    # d3
    ("fractional_exponents", {"terms": [[4, "3/2"], [6, "2/3"]]}, 6 * sp.sqrt(x) + 4 / sp.cbrt(x)),
    ("root_reciprocals", {"terms": [[8, "-1/2"], [3, "1/3"], [-2, -1]]},
     -4 / x ** sp.Rational(3, 2) + 1 / x ** sp.Rational(2, 3) + 2 / x**2),
    ("rational_coefficients", {"terms": [["1/3", 6], ["-5/2", -2], ["3/4", "4/3"]]},
     2 * x**5 + 5 / x**3 + sp.cbrt(x)),
    # d4: (3x^4 - 2x + 5)/x^2 = 3x^2 - 2x^-1 + 5x^-2
    ("split_fraction", {"den": 2, "num": [[3, 4], [-2, 1], [5, 0]]}, 6 * x + 2 / x**2 - 10 / x**3),
    # (4x^2 - 6x + 2)/sqrt(x) = 4x^(3/2) - 6x^(1/2) + 2x^(-1/2)
    ("split_root_fraction", {"root": "1/2", "num": [[4, 2], [-6, 1], [2, 0]]},
     6 * sp.sqrt(x) - 3 / sp.sqrt(x) - 1 / x ** sp.Rational(3, 2)),
    # (3x^2 + 6x)/cbrt(x) = 3x^(5/3) + 6x^(2/3)
    ("split_root_fraction", {"root": "1/3", "num": [[3, 2], [6, 1]]}, 5 * x ** sp.Rational(2, 3) + 4 / sp.cbrt(x)),
    # sqrt(x)(x + 1/x) = x^(3/2) + x^(-1/2)
    ("distribute_power", {"factor": "1/2", "bracket": [[1, 1], [1, -1]]},
     sp.Rational(3, 2) * sp.sqrt(x) - half / x ** sp.Rational(3, 2)),
    # x^2(3x - 1/x) = 3x^3 - x
    ("distribute_power", {"factor": 2, "bracket": [[3, 1], [-1, -1]]}, 9 * x**2 - 1),
]


@pytest.mark.parametrize("family_id,params,expected", SYMBOLIC_EXAMPLES)
def test_hand_checked_keys(family_id, params, expected):
    built = build(family_id, params)
    assert same(built.key, expected), f"{family_id}: key {built.key}, expected {expected}"
    assert verify_built(SKILL, built).ok


POINT_EXAMPLES = [
    # s = t^3 - 6t^2 + 9t + 2, s'(4) = 48 - 48 + 9
    ("word_velocity", {"story": "particle", "terms": [[1, 3], [-6, 2], [9, 1], [2, 0]], "t0": 4}, 9),
    # h = -5t^2 + 20t + 10, h'(3) = -30 + 20
    ("word_velocity", {"story": "ball", "terms": [[-5, 2], [20, 1], [10, 0]], "t0": 3}, -10),
    # V = 4/3 pi r^3, V'(3) = 4 pi 9
    ("word_geometry", {"shape": "sphere_volume", "x0": 3}, 36 * sp.pi),
    ("word_geometry", {"shape": "circle_area", "x0": 5}, 10 * sp.pi),
    ("word_geometry", {"shape": "cube_volume", "x0": 4}, 48),
    # h = 6 sqrt(t) + 3, h'(9) = 3 / sqrt(9)
    ("word_growth", {"a": 6, "b": 3, "t0": 9}, 1),
    # A = 3q + 40 + 500/q, A'(10) = 3 - 500/100
    ("word_average_cost", {"a": 3, "b": 40, "c": 500, "q0": 10}, -2),
]


@pytest.mark.parametrize("family_id,params,expected", POINT_EXAMPLES)
def test_hand_checked_point_answers(family_id, params, expected):
    built = build(family_id, params)
    assert built.at is not None and built.word is not None
    assert same(built.key, sp.sympify(expected), ())
    assert built.steps[-1].id == "evaluate"
    assert verify_built(SKILL, built).ok


def test_steps_walk_the_rule():
    built = build("negative_powers", {"terms": [[2, 3], [-5, -2]]})
    assert [st.id for st in built.steps] == ["rewrite", "power_rule", "simplify"]
    rewrite, power_rule, simplify = built.steps
    assert "x^{\\htmlClass{slate-yellow}{-2}}" in rewrite.latex
    assert "\\htmlClass{slate-mint}{-2 - 1}" in power_rule.latex
    assert same(simplify.expr, built.key)


def test_rewrite_keeps_the_visible_form():
    quotient = build("split_fraction", {"den": 2, "num": [[3, 4], [-2, 1], [5, 0]]})
    assert "\\frac{3 x^{4} - 2 x + 5}{x^{2}}" in quotient.prompt
    product = build("distribute_power", {"factor": "1/2", "bracket": [[1, 1], [1, -1]]})
    assert "\\sqrt{x} \\left(x + \\frac{1}{x}\\right)" in product.prompt


# --- mistakes -------------------------------------------------------------------


def test_mistake_tags_are_in_the_taxonomy():
    for pattern in SKILL.mistakes:
        mistake_type(pattern.tag)
    signature = {m.tag for m in SKILL.mistakes if m.signature}
    assert signature == {"power_exponent_not_reduced", "power_coefficient_dropped"}


def test_core_mistakes_on_a_polynomial():
    # 3x^4 - 5x^2 + 7, key 12x^3 - 10x
    built = build("polynomial", {"terms": [[3, 4], [-5, 2], [7, 0]]})
    (not_reduced,) = wrong_answers(built, "power_exponent_not_reduced")
    assert same(not_reduced, 12 * x**4 - 10 * x**2)
    (dropped,) = wrong_answers(built, "power_coefficient_dropped")
    assert same(dropped, 3 * x**3 - 5 * x)
    (kept,) = wrong_answers(built, "constant_term_kept")
    assert same(kept, 12 * x**3 - 10 * x + 7)
    for tag in ("negative_exponent_slip", "quotient_as_derivative_ratio", "product_of_derivatives",
                "product_rule_missing_term"):
        assert wrong_answers(built, tag) == []


def test_no_constant_means_no_constant_mistake():
    built = build("single_power", {"terms": [[5, 3]]})
    assert wrong_answers(built, "constant_term_kept") == []


def test_negative_exponent_slip():
    # 2x^3 - 5x^-2: the slip takes -2 to -1 instead of -3.
    built = build("negative_powers", {"terms": [[2, 3], [-5, -2]]})
    (slip,) = wrong_answers(built, "negative_exponent_slip")
    assert same(slip, 6 * x**2 + 10 / x)


def test_fractional_exponent_slip():
    # 4x^(3/2) + 6x^(2/3): one taken off the numerator gives exponents 2/2 and 1/3.
    built = build("fractional_exponents", {"terms": [[4, "3/2"], [6, "2/3"]]})
    (slip,) = wrong_answers(built, "negative_exponent_slip")
    assert same(slip, 6 * x + 4 * sp.cbrt(x))


def test_negative_fraction_gets_both_slips():
    # 8x^(-1/2): toward zero gives -4x^(1/2), numerator only gives -4x^(-1).
    built = build("root_reciprocals", {"terms": [[8, "-1/2"], [3, -1]]})
    slips = wrong_answers(built, "negative_exponent_slip")
    assert len(slips) == 2
    assert same(slips[0], -4 * sp.sqrt(x) - 3)
    assert same(slips[1], -4 / x - 3 / x**2)


def test_quotient_as_derivative_ratio():
    # (3x^4 - 2x + 5)/x^2 differentiated top over bottom.
    built = build("split_fraction", {"den": 2, "num": [[3, 4], [-2, 1], [5, 0]]})
    (ratio,) = wrong_answers(built, "quotient_as_derivative_ratio")
    assert same(ratio, (12 * x**3 - 2) / (2 * x))
    # The rewrite turns +5 into 5x^-2, so there is no constant to keep.
    assert wrong_answers(built, "constant_term_kept") == []


def test_product_mistakes():
    # sqrt(x)(x + 1/x)
    built = build("distribute_power", {"factor": "1/2", "bracket": [[1, 1], [1, -1]]})
    (product,) = wrong_answers(built, "product_of_derivatives")
    assert same(product, (1 - 1 / x**2) / (2 * sp.sqrt(x)))
    (missing,) = wrong_answers(built, "product_rule_missing_term")
    assert same(missing, sp.sqrt(x) * (1 - 1 / x**2))


def test_constant_that_appears_after_rewriting():
    # x(-x^2 + 4/x) = -x^3 + 4, so a kept constant adds 4.
    built = build("distribute_power", {"factor": 1, "bracket": [[-1, 2], [4, -1]]})
    assert same(built.key, -3 * x**2)
    (kept,) = wrong_answers(built, "constant_term_kept")
    assert same(kept, -3 * x**2 + 4)


def test_point_mistakes_are_numbers():
    sphere = build("word_geometry", {"shape": "sphere_volume", "x0": 3})
    (not_reduced,) = wrong_answers(sphere, "power_exponent_not_reduced")
    assert same(not_reduced, 108 * sp.pi, ())
    (dropped,) = wrong_answers(sphere, "power_coefficient_dropped")
    assert same(dropped, 12 * sp.pi, ())

    plant = build("word_growth", {"a": 6, "b": 3, "t0": 9})
    (kept,) = wrong_answers(plant, "constant_term_kept")
    assert same(kept, sp.Integer(4), ())
    (slip,) = wrong_answers(plant, "negative_exponent_slip")  # 6t^(1/2) -> 3t^0
    assert same(slip, sp.Integer(3), ())

    # A = 3q + 40 + 500/q at q = 10
    cost = build("word_average_cost", {"a": 3, "b": 40, "c": 500, "q0": 10})
    expected = {
        "power_exponent_not_reduced": 3 * 10 - sp.Rational(500, 10),
        "power_coefficient_dropped": 3 + sp.Rational(500, 100),
        "constant_term_kept": -2 + 40,
        "negative_exponent_slip": 3 - 500,
        "quotient_as_derivative_ratio": 6 * 10 + 40,
    }
    for tag, value in expected.items():
        (wrong,) = wrong_answers(cost, tag)
        assert not wrong.free_symbols, tag
        assert same(wrong, sp.sympify(value), ()), f"{tag}: {wrong} != {value}"


def test_point_problems_reject_invisible_signature_mistakes():
    # s = t^3 - 4t^2 + t at t = 2: dropping the brought-down exponent gives
    # 4 - 8 + 1 = -3, the same as the key 12 - 16 + 1.
    with pytest.raises(ValueError):
        build("word_velocity", {"story": "particle", "terms": [[1, 3], [-4, 2], [1, 1]], "t0": 2})


# --- every family, many seeds ------------------------------------------------------


def test_difficulty_coverage():
    for difficulty in (1, 2, 3, 4):
        assert len(SKILL.families_at(difficulty, word=False)) >= 2, difficulty
    assert len(SKILL.families_at(2, word=True)) >= 1
    assert sum(len(SKILL.families_at(d, word=True)) for d in (1, 2, 3, 4)) >= 3


@pytest.mark.parametrize("family", SKILL.families, ids=lambda f: f.id)
def test_family_sweep(family):
    for seed in range(40):
        params = family.sample(Random(seed))
        stored = json.loads(json.dumps(params))
        built = family.build(stored)
        report = verify_built(SKILL, built)
        assert report.ok, f"{family.id} seed {seed}: {[(c.name, c.detail) for c in report.failures]}"
        # build is a pure function of the stored params
        again = family.build(json.loads(json.dumps(built.params)))
        assert again.key == built.key and again.prompt == built.prompt
        assert built.family == family.id and built.difficulty == family.difficulty
