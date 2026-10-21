"""Tests for the product rule skill (calc1.derivatives.product_rule).

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
from slate_skills.core.text import render

SKILL = load_skill_module("calc1.derivatives.product_rule")

x, t = sp.symbols("x t")
S, C, E, L = sp.sin(x), sp.cos(x), sp.exp(x), sp.log(x)


def build(family_id: str, params: dict):
    return SKILL.family(family_id).build(params)


def same(a: sp.Expr, b: sp.Expr, symbols=(x,)) -> bool:
    return equivalent(a, b, symbols).equal is True


def pattern(tag: str, note_contains: str = ""):
    """The one mistake pattern with ``tag`` whose note contains ``note_contains``."""
    found = [m for m in SKILL.mistakes if m.tag == tag and note_contains in m.note]
    assert len(found) == 1, f"expected one {tag} pattern matching {note_contains!r}, found {len(found)}"
    return found[0]


SIGNATURE = pattern("product_of_derivatives", "Multiplying them")
DROP_LAST = pattern("product_rule_missing_term", "[[last_colored]]")
DROP_FIRST = pattern("product_rule_missing_term", "[[f:yellow]]")
GROUPED = pattern("product_of_derivatives", "Treating")
SUBTRACTED = pattern("sign_error")
TRIG_SIGN = pattern("trig_derivative_sign")
LN_AS_ONE = pattern("exp_log_derivative_error", "ln x")
EXP_AS_POWER = pattern("exp_log_derivative_error", "e^x$ is not")
COEFFICIENT_DROPPED = pattern("power_coefficient_dropped")
EXPONENT_SLIP = pattern("negative_exponent_slip")


# --- hand-checked keys ----------------------------------------------------------

SYMBOLIC_EXAMPLES = [
    # d1: 3x^2 sin x, 2x^3 e^x, (2x + 1)(3x - 4)
    ("mono_trig", {"a": 3, "n": 2, "trig": "sin"}, 6 * x * S + 3 * x**2 * C),
    ("mono_trig", {"a": -1, "n": 1, "trig": "cos"}, -C + x * S),
    ("mono_exp", {"a": 2, "n": 3}, (6 * x**2 + 2 * x**3) * E),
    ("two_linear", {"f": [2, 1], "g": [3, -4]}, 12 * x - 5),
    # d2: (x^2 - 3x + 1) cos x, (x^2 - 3x + 1) e^x, (x^2 - 3x) ln x
    ("poly_trig", {"poly": [1, -3, 1], "trig": "cos"}, (2 * x - 3) * C - (x**2 - 3 * x + 1) * S),
    ("poly_exp", {"poly": [1, -3, 1]}, (x**2 - x - 2) * E),
    ("poly_ln", {"poly": [1, -3, 0]}, (2 * x - 3) * L + x - 3),
    ("poly_ln", {"poly": [2, 0, 5, 0]}, (6 * x**2 + 5) * L + 2 * x**2 + 5),
    # d3: (x^2 + 1) ln x, (2x + 3) sqrt(x), sqrt(x) e^x, 2 sqrt(x) ln x, e^x sin x, sin x cos x
    ("poly_ln_const", {"poly": [1, 0, 1]}, 2 * x * L + x + 1 / x),
    ("linear_sqrt", {"a": 2, "b": 3}, (6 * x + 3) / (2 * sp.sqrt(x))),
    ("sqrt_transcendental", {"k": 1, "other": "exp"}, (2 * x + 1) * E / (2 * sp.sqrt(x))),
    ("sqrt_transcendental", {"k": 2, "other": "ln"}, (L + 2) / sp.sqrt(x)),
    ("transcendental_pair", {"pair": ["exp", "sin"]}, E * (S + C)),
    ("transcendental_pair", {"pair": ["sin", "cos"]}, C**2 - S**2),
    # d4: x^2 e^x sin x, x^(-2) e^x, 2x^(3/2) ln x, x^(2/3) cos x
    ("triple", {"a": 1, "n": 2, "pair": ["exp", "sin"]}, 2 * x * E * S + x**2 * E * S + x**2 * E * C),
    ("triple", {"a": 2, "n": 1, "pair": ["sin", "cos"]}, 2 * S * C + 2 * x * C**2 - 2 * x * S**2),
    ("power_transcendental", {"a": 1, "r": [-2, 1], "other": "exp"}, (x - 2) * E / x**3),
    ("power_transcendental", {"a": 2, "r": [3, 2], "other": "ln"}, 3 * sp.sqrt(x) * L + 2 * sp.sqrt(x)),
    ("power_transcendental", {"a": 3, "r": [2, 3], "other": "cos"},
     2 * C / sp.cbrt(x) - 3 * x ** sp.Rational(2, 3) * S),
]

POINT_EXAMPLES = [
    # w = 3t + 2, h = t^2 + 4 at t = 2: 3 * 8 + 8 * 4
    ("word_rectangle", {"w": [3, 2], "h": [1, 0, 4], "t0": 2}, 56),
    # w = t + 4, h = 10 - 2t at t = 3: 1 * 4 + 7 * (-2)
    ("word_rectangle", {"w": [1, 4], "h": [-2, 10], "t0": 3}, -10),
    # p = 30 - 2t, q = 8 sqrt(t) + 50 at t = 4: -2 * 66 + 22 * 2
    ("word_revenue", {"price": [-2, 30], "sales": [8, 50], "t0": 4}, -88),
    # l = t + 2, w = 2t + 1, h = t + 3 at t = 1: 1*3*4 + 3*2*4 + 3*3*1
    ("word_box", {"dims": [[1, 2], [2, 1], [1, 3]], "t0": 1}, 45),
]


@pytest.mark.parametrize("family_id,params,expected", SYMBOLIC_EXAMPLES)
def test_symbolic_keys(family_id, params, expected):
    built = build(family_id, params)
    assert built.at is None
    assert same(built.key, expected), f"{family_id}: key {built.key} != {expected}"
    assert verify_built(SKILL, built).ok


@pytest.mark.parametrize("family_id,params,expected", POINT_EXAMPLES)
def test_point_keys(family_id, params, expected):
    built = build(family_id, params)
    assert built.var == t and built.at == {t: params["t0"]}
    assert built.key == expected
    assert built.word is not None and f"t = {params['t0']}" in built.word.question
    assert verify_built(SKILL, built).ok


def test_every_difficulty_has_two_symbolic_families_and_word_problems_exist():
    for d in (1, 2, 3, 4):
        assert len(SKILL.families_at(d, word=False)) >= 2
    assert {f.id for f in SKILL.families if f.word} == {"word_rectangle", "word_revenue", "word_box"}


def test_factors_named_in_the_order_the_student_sees_them():
    built = build("linear_sqrt", {"a": 2, "b": 3})
    # SymPy prints sqrt(x) (2x + 3), so f is the square root.
    assert built.prompt == r"Differentiate $y = \sqrt{x} \left(2 x + 3\right)$."
    assert built.parts["f"] == sp.sqrt(x) and built.parts["g"] == 2 * x + 3

    built = build("transcendental_pair", {"pair": ["sin", "exp"]})
    assert built.parts["f"] == E and built.parts["g"] == S


def test_negative_power_is_written_as_a_power():
    built = build("power_transcendental", {"a": 3, "r": [-2, 1], "other": "sin"})
    assert "3 x^{-2}" in built.prompt and r"\frac" not in built.prompt
    assert built.snippets["f"] == "3 x^{-2}" and built.snippets["f_prime"] == "-6 x^{-3}"


def test_merged_powers_are_rejected():
    # Two powers of x would merge into one, so the student would not see two factors.
    with pytest.raises(ValueError):
        SKILL.family("linear_sqrt").build({"a": 2, "b": 0})


def test_steps_walk_the_rule():
    built = build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "assemble", "simplify"]
    assert "slate-yellow" in built.steps[0].latex and "slate-mint" in built.steps[0].latex
    assemble = built.steps[2]
    assert assemble.latex.startswith(r"\frac{dy}{dx} = f' g + f g' = ")
    assert same(assemble.expr, built.key)

    built = build("word_box", {"dims": [[1, 2], [2, 1], [1, 3]], "t0": 1})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "assemble", "evaluate"]
    assert r"\ell' w h + \ell w' h + \ell w h'" in built.steps[2].latex
    assert built.steps[-1].expr == 45


# --- mistake patterns -------------------------------------------------------------

def test_signature_multiplies_the_derivatives():
    built = build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})
    assert SIGNATURE.signature
    assert same(SIGNATURE.buggy(built), 6 * x * C)
    triple = build("triple", {"a": 1, "n": 2, "pair": ["exp", "sin"]})
    assert same(SIGNATURE.buggy(triple), 2 * x * E * C)


def test_missing_term_patterns():
    built = build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})
    assert same(DROP_LAST.buggy(built), 6 * x * S)  # kept only f'g
    assert same(DROP_FIRST.buggy(built), 3 * x**2 * C)  # kept only fg'

    # With g = e^x, keeping only f'g is the same answer as f'g', so the signature pattern owns it.
    built = build("mono_exp", {"a": 2, "n": 3})
    assert DROP_LAST.buggy(built) is None
    assert same(DROP_FIRST.buggy(built), 2 * x**3 * E)

    # Three factors: forgot the h' term, or the f' term.
    triple = build("triple", {"a": 1, "n": 2, "pair": ["exp", "sin"]})
    assert same(DROP_LAST.buggy(triple), 2 * x * E * S + x**2 * E * S)
    assert same(DROP_FIRST.buggy(triple), x**2 * E * S + x**2 * E * C)


def test_grouped_product_of_derivatives():
    # (x^2 (e^x sin x))' with (e^x sin x)' taken as e^x cos x.
    triple = build("triple", {"a": 1, "n": 2, "pair": ["exp", "sin"]})
    assert same(GROUPED.buggy(triple), 2 * x * E * S + x**2 * E * C)
    assert GROUPED.buggy(build("two_linear", {"f": [2, 1], "g": [3, -4]})) is None


def test_subtracted_terms():
    # 2(3x - 4) - (2x + 1) 3 = -11
    built = build("two_linear", {"f": [2, 1], "g": [3, -4]})
    assert same(SUBTRACTED.buggy(built), sp.Integer(-11))
    # When the trig factor comes second, subtracting is the trig sign slip; that pattern explains it.
    assert SUBTRACTED.buggy(build("poly_trig", {"poly": [1, -3, 1], "trig": "cos"})) is None
    assert SUBTRACTED.buggy(build("triple", {"a": 1, "n": 2, "pair": ["exp", "ln"]})) is None


def test_trig_derivative_sign():
    built = build("poly_trig", {"poly": [1, -3, 1], "trig": "cos"})
    assert same(TRIG_SIGN.buggy(built), (2 * x - 3) * C + (x**2 - 3 * x + 1) * S)
    built = build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})
    assert same(TRIG_SIGN.buggy(built), 6 * x * S - 3 * x**2 * C)
    # sin x cos x with (cos x)' = sin x gives cos^2 x + sin^2 x.
    built = build("transcendental_pair", {"pair": ["sin", "cos"]})
    assert same(TRIG_SIGN.buggy(built), sp.Integer(1))
    assert TRIG_SIGN.buggy(build("poly_exp", {"poly": [1, -3, 1]})) is None


def test_exp_and_log_derivative_errors():
    built = build("poly_ln", {"poly": [1, -3, 0]})
    assert same(LN_AS_ONE.buggy(built), (2 * x - 3) * L + x**2 - 3 * x)
    built = build("mono_exp", {"a": 2, "n": 3})
    assert same(EXP_AS_POWER.buggy(built), 6 * x**2 * E + 2 * x**4 * sp.exp(x - 1))
    assert LN_AS_ONE.buggy(built) is None
    assert EXP_AS_POWER.buggy(build("poly_ln", {"poly": [1, -3, 0]})) is None


def test_power_rule_slips_on_power_factors():
    # (sqrt(x))' taken as 1/sqrt(x).
    built = build("sqrt_transcendental", {"k": 1, "other": "exp"})
    assert same(COEFFICIENT_DROPPED.buggy(built), E / sp.sqrt(x) + sp.sqrt(x) * E)
    # (3x^2)' taken as 3x.
    built = build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})
    assert same(COEFFICIENT_DROPPED.buggy(built), 3 * x * S + 3 * x**2 * C)
    # (x^-2)' taken as -2x^-1, and (2x^(3/2))' as 3x^(2/2).
    built = build("power_transcendental", {"a": 1, "r": [-2, 1], "other": "exp"})
    assert same(EXPONENT_SLIP.buggy(built), -2 * E / x + E / x**2)
    built = build("power_transcendental", {"a": 2, "r": [3, 2], "other": "ln"})
    assert same(EXPONENT_SLIP.buggy(built), 3 * x * L + 2 * sp.sqrt(x))
    assert EXPONENT_SLIP.buggy(build("mono_trig", {"a": 3, "n": 2, "trig": "sin"})) is None


def test_point_problem_mistakes_are_numbers():
    # w = 3t + 2, h = t^2 + 4 at t = 2: w' = 3, h' = 4, w = 8, h = 8.
    built = build("word_rectangle", {"w": [3, 2], "h": [1, 0, 4], "t0": 2})
    assert SIGNATURE.buggy(built) == 12
    assert DROP_LAST.buggy(built) == 24
    assert DROP_FIRST.buggy(built) == 32
    assert SUBTRACTED.buggy(built) == -8
    # p = 30 - 2t, q = 8 sqrt(t) + 50 at t = 4 with q' taken as 8/sqrt(t): -2 * 66 + 22 * 4
    built = build("word_revenue", {"price": [-2, 30], "sales": [8, 50], "t0": 4})
    assert COEFFICIENT_DROPPED.buggy(built) == -44
    # l = t + 2, w = 2t + 1, h = t + 3 at t = 1: 1 * 3 * 4 + 3 * (2 * 1)
    built = build("word_box", {"dims": [[1, 2], [2, 1], [1, 3]], "t0": 1})
    assert GROUPED.buggy(built) == 18


def test_mistake_tags_exist_and_notes_render():
    built = build("triple", {"a": 1, "n": 2, "pair": ["exp", "sin"]})
    for m in SKILL.mistakes:
        mistake_type(m.tag)
        assert m.step in {s.id for s in built.steps}
        text = render(m.note, built)
        assert "[[" not in text and "\u2014" not in text  # no em dashes


# --- sweep ------------------------------------------------------------------------

@pytest.mark.parametrize("family", SKILL.families, ids=lambda f: f.id)
def test_family_sweep_verifies(family):
    built_count = 0
    for seed in range(40):
        params = family.sample(Random(seed))
        # Parameters are stored with the problem, so they must survive JSON.
        params = json.loads(json.dumps(params))
        try:
            built = family.build(params)
        except ValueError:
            continue
        built_count += 1
        assert built.difficulty == family.difficulty and built.family == family.id
        json.dumps(built.params)
        report = verify_built(SKILL, built)
        assert report.ok, f"{family.id} seed {seed}: {[(c.name, c.detail) for c in report.failures]}"
        # build is pure: the same params give the same problem.
        again = family.build(params)
        assert again.key == built.key and again.prompt == built.prompt
    assert built_count >= 35, f"{family.id} rejected too many samples"
