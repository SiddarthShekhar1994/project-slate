"""Tests for the implicit differentiation skill (calc1.derivatives.implicit_differentiation).

The skill is loaded straight from its module so a broken sibling skill file
cannot break these tests. Symbolic keys are compared on the curve, the way the
verifier and the grader compare them.
"""

from __future__ import annotations

import json
from random import Random

import pytest
import sympy as sp
from slate_api.services.verify import equivalent, verify_built
from slate_skills import load_skill_module
from slate_skills.core.mistakes import mistake_type
from slate_skills.core.text import render, tex

SKILL = load_skill_module("calc1.derivatives.implicit_differentiation")

x, y = sp.symbols("x y")
R = sp.Rational


def build(family_id: str, params: dict):
    return SKILL.family(family_id).build(params)


def on_curve(a: sp.Expr, b: sp.Expr, curve: sp.Expr) -> bool | None:
    """``a == b`` on the curve ``curve = 0``, as the verifier decides it."""
    return equivalent(a, b, (x, y), constraint=curve).equal


def pattern(tag: str, note_contains: str = ""):
    """The one mistake pattern with ``tag`` whose note contains ``note_contains``."""
    found = [m for m in SKILL.mistakes if m.tag == tag and note_contains in m.note]
    assert len(found) == 1, f"expected one {tag} pattern matching {note_contains!r}, found {len(found)}"
    return found[0]


MISSING_DYDX = pattern("implicit_missing_dydx", "chain rule")
Y_CONSTANT = pattern("implicit_missing_dydx", "treated $y$ as a constant")
X_CONSTANT = pattern("implicit_product_rule_missed", "only the $y$ factor")
PRODUCT_OF_DERIVATIVES = pattern("implicit_product_rule_missed", "multiplied the derivatives")
SIGN_SLIP = pattern("implicit_isolation_error", "signs")
DIVIDED_WRONG_WAY = pattern("implicit_isolation_error", "wrong way round")
CONSTANT_KEPT = pattern("constant_term_kept")
SWAPPED_POINT = pattern("algebra_slip")


# --- hand-checked keys ----------------------------------------------------------

SYMBOLIC_EXAMPLES = [
    # d1: x^2 + y^2 = 25; x^2 + y^2 = 6x + 16; x^2 + 2x + y^2 = 48
    ("circle", {"r": 5, "d": 0, "side": "lhs"}, -x / y),
    ("circle", {"r": 5, "d": -6, "side": "rhs"}, (3 - x) / y),
    ("circle", {"r": 7, "d": 2, "side": "lhs"}, -(x + 1) / y),
    # 4x^2 + 9y^2 = 72; 2x^2 - 5y^2 = 3; 3y^2 - x^2 = 13
    ("ellipse", {"a": 4, "b": 9, "p": 3, "q": 2}, -4 * x / (9 * y)),
    ("hyperbola", {"a": 2, "b": 5, "c": 3, "opens": "x"}, 2 * x / (5 * y)),
    ("hyperbola", {"a": 1, "b": 3, "c": 13, "opens": "y"}, x / (3 * y)),
    # y^2 = x^3 - 4x + 1; y^3 = 2x^2 + 5
    ("power_curve", {"n": 2, "poly": [[1, 3, 0], [-4, 1, 0], [1, 0, 0]]}, (3 * x**2 - 4) / (2 * y)),
    ("power_curve", {"n": 3, "poly": [[2, 2, 0], [5, 0, 0]]}, 4 * x / (3 * y**2)),
    # d2: x^2 + xy + y^2 = 7; x^2 - 3xy + 3y^2 = 19
    ("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7}, -(2 * x + y) / (x + 2 * y)),
    ("quadratic_mixed", {"a": 1, "b": -3, "d": 3, "c": 19}, (3 * y - 2 * x) / (6 * y - 3 * x)),
    # xy + y^2 = 6; xy = 3y^2 - 3; 2xy - x + 2y^2 = 9
    ("product_term", {"a": 1, "b": 1, "e": 0, "c": 6, "layout": "same"}, -y / (x + 2 * y)),
    ("product_term", {"a": 1, "b": 3, "e": 0, "c": 3, "layout": "split"}, y / (6 * y - x)),
    ("product_term", {"a": 2, "b": 2, "e": -1, "c": 9, "layout": "same"}, (1 - 2 * y) / (2 * x + 4 * y)),
    # d3: x^3 + y^3 = 6xy; x^3 + y^3 = 4xy + 6
    ("folium", {"k": 6, "c": 0}, (2 * y - x**2) / (y**2 - 2 * x)),
    ("folium", {"k": 4, "c": 6}, (4 * y - 3 * x**2) / (3 * y**2 - 4 * x)),
    # x^2 y + y^3 = 10; x y^2 + x^3 = 5; 2x y^2 - 3y^3 = -4
    ("mixed_cubic", {"shape": "x2y_y3", "a": 1, "b": 1, "c": 10}, -2 * x * y / (x**2 + 3 * y**2)),
    ("mixed_cubic", {"shape": "xy2_x3", "a": 1, "b": 1, "c": 5}, -(y**2 + 3 * x**2) / (2 * x * y)),
    ("mixed_cubic", {"shape": "xy2_y3", "a": 2, "b": -3, "c": -4}, -2 * y / (4 * x - 9 * y)),
    # d4: x^2 y + 2xy^2 + 3y = -4; x^2 y + x y^2 = 6
    ("two_mixed", {"a": 1, "b": 2, "e": 3, "k": 1, "c": -4},
     -(2 * x * y + 2 * y**2) / (x**2 + 4 * x * y + 3)),
    ("two_mixed", {"a": 1, "b": 1, "e": 0, "k": 1, "c": 6}, -(2 * x * y + y**2) / (x**2 + 2 * x * y)),
    # x^2 y^2 + y^3 = 5; x y^3 - x^2 = 8; x^3 y + 2y^2 = 2x + 3
    ("higher_mixed", {"shape": "x2y2_y3", "a": 1, "b": 1, "c": 5, "e": 0}, -2 * x * y / (2 * x**2 + 3 * y)),
    ("higher_mixed", {"shape": "xy3_x2", "a": 1, "b": -1, "c": 8, "e": 0}, (2 * x - y**3) / (3 * x * y**2)),
    ("higher_mixed", {"shape": "x3y_y2", "a": 1, "b": 2, "c": 3, "e": 2}, (2 - 3 * x**2 * y) / (x**3 + 4 * y)),
]

POINT_EXAMPLES = [
    # 4x^2 + 9y^2 = 72 at (3, 2): -4x/(9y) = -12/18
    ("word_mirror", {"a": 4, "b": 9, "point": [3, 2]}, R(-2, 3)),
    # x^2 + xy + y^2 = 7 at (1, 2): -(2 + 2)/(1 + 4)
    ("word_track", {"a": 1, "b": 1, "d": 1, "point": [1, 2]}, R(-4, 5)),
    # x^2 y = 48 at (4, 3): -2y/x
    ("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]}, R(-3, 2)),
    # x^3 + y^3 = 9xy at (2, 4): (3y - x^2)/(y^2 - 3x) = 8/10
    ("word_pendant", {"k": 9, "point": [2, 4]}, R(4, 5)),
    # x^3 + xy - 3y^2 = -15 at (-1, 2): -(3x^2 + y)/(x - 6y) = -5/-13
    ("slope_at_point", {"shape": "x3_xy_y2", "coeffs": [1, 1, -3], "point": [-1, 2]}, R(5, 13)),
    # x^2 y + y^3 = 10 at (1, 2): -2xy/(x^2 + 3y^2) = -4/13
    ("slope_at_point", {"shape": "x2y_y3", "coeffs": [1, 1], "point": [1, 2]}, R(-4, 13)),
]


@pytest.mark.parametrize("family_id,params,expected", SYMBOLIC_EXAMPLES)
def test_symbolic_keys(family_id, params, expected):
    built = build(family_id, params)
    assert built.at is None and built.task == "implicit_differentiate"
    assert built.var == x and built.dependent == y
    assert sp.expand(built.equation.lhs - built.equation.rhs - built.expr) == 0
    assert on_curve(built.key, expected, built.expr) is True, f"{family_id}: key {built.key} != {expected}"
    assert verify_built(SKILL, built).ok


@pytest.mark.parametrize("family_id,params,expected", POINT_EXAMPLES)
def test_point_keys(family_id, params, expected):
    built = build(family_id, params)
    x0, y0 = params["point"]
    assert built.at == {x: x0, y: y0}
    assert built.expr.subs(built.at) == 0, "the point must lie on the curve"
    assert built.key == expected
    assert f"({x0}, {y0})" in built.prompt
    assert verify_built(SKILL, built).ok


def test_every_difficulty_has_two_symbolic_families_and_word_problems_exist():
    for d in (1, 2, 3, 4):
        assert len(SKILL.families_at(d, word=False)) >= 2
    word = {f.id for f in SKILL.families if f.word}
    assert word == {"word_mirror", "word_track", "word_isoquant", "word_pendant"}


# --- answers that differ in form but agree on the curve -----------------------------------


def test_circle_answers_that_agree_on_the_curve():
    built = build("circle", {"r": 5, "d": 0, "side": "lhs"})
    curve = built.expr
    assert curve == x**2 + y**2 - 25
    # y^2 = 25 - x^2 on the circle, so -x/y = -xy/y^2 = -xy/(25 - x^2).
    assert on_curve(-x * y / (25 - x**2), built.key, curve) is True
    # (x^2 + y^2)/25 is 1 on the circle.
    assert on_curve(-x * (x**2 + y**2) / (25 * y), built.key, curve) is True
    # Off the curve these are different functions, so the constraint is doing the work.
    assert equivalent(-x * y / (25 - x**2), built.key, (x, y)).equal is False
    # A sign slip is still wrong on the curve.
    assert on_curve(x / y, built.key, curve) is False


def test_mixed_term_answers_that_agree_on_the_curve():
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    # Multiply top and bottom by y, then replace y^2 with 7 - x^2 - xy.
    rewritten = -(x * y + 7 - x**2) / (14 - 2 * x**2 - x * y)
    assert on_curve(rewritten, built.key, built.expr) is True
    assert on_curve((2 * x + y) / (x + 2 * y), built.key, built.expr) is False


def test_folium_answers_that_agree_on_the_curve():
    built = build("folium", {"k": 6, "c": 0})
    # Multiply top and bottom by x, then replace x^3 with 6xy - y^3.
    rewritten = (y**3 - 4 * x * y) / (x * y**2 - 2 * x**2)
    assert on_curve(rewritten, built.key, built.expr) is True
    assert on_curve((x**2 - 2 * y) / (y**2 - 2 * x), built.key, built.expr) is False


# --- what the student sees ------------------------------------------------------------------


def test_prompts():
    built = build("circle", {"r": 5, "d": 0, "side": "lhs"})
    assert built.prompt == (r"Find $\frac{dy}{dx}$ if $x^{2} + y^{2} = 25$. "
                            r"Give your answer in terms of $x$ and $y$.")
    built = build("slope_at_point", {"shape": "x2y_y3", "coeffs": [1, 1], "point": [1, 2]})
    assert built.prompt == r"Find $\frac{dy}{dx}$ at the point $(1, 2)$ on the curve $x^{2} y + y^{3} = 10$."
    built = build("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]})
    assert built.word is not None and built.word.unit == "workers per machine"
    assert "$x^{2} y = 48$" in built.prompt and "$(4, 3)$" in built.prompt


def test_key_reads_well():
    # Common factors cancelled and the denominator leads with a positive term.
    built = build("folium", {"k": 6, "c": 0})
    assert tex(built.key) == r"\frac{x^{2} - 2 y}{2 x - y^{2}}"
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    assert tex(built.key) == r"- \frac{2 x + y}{x + 2 y}"


def test_steps_walk_the_rule():
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "collect", "solve"]
    identify, differentiate, collect, solve = built.steps
    assert identify.latex == (r"x^{2} + \htmlClass{slate-mint}{x y} + \htmlClass{slate-yellow}{y^{2}} = 7")
    assert differentiate.latex == (r"2 x + \htmlClass{slate-mint}{\left(y + x \frac{dy}{dx}\right)} + "
                                   r"\htmlClass{slate-yellow}{2 y \frac{dy}{dx}} = 0")
    assert collect.latex == (r"\htmlClass{slate-yellow}{\left(x + 2 y\right)} \frac{dy}{dx} = "
                             r"\htmlClass{slate-mint}{- 2 x - y}")
    assert solve.expr == built.key
    assert all(s.expr is None for s in (identify, differentiate, collect))

    # y' terms on both sides get collected on the left.
    built = build("folium", {"k": 6, "c": 0})
    differentiate, collect = built.steps[1], built.steps[2]
    assert differentiate.latex == (r"3 x^{2} + \htmlClass{slate-yellow}{3 y^{2} \frac{dy}{dx}} = "
                                   r"\htmlClass{slate-mint}{\left(6 y + 6 x \frac{dy}{dx}\right)}")
    assert collect.latex == (r"\htmlClass{slate-yellow}{\left(- 6 x + 3 y^{2}\right)} \frac{dy}{dx} = "
                             r"\htmlClass{slate-mint}{- 3 x^{2} + 6 y}")

    built = build("word_pendant", {"k": 9, "point": [2, 4]})
    assert [s.id for s in built.steps] == ["identify", "differentiate", "collect", "solve", "evaluate"]
    assert tex(built.parts["formula"]) == r"\frac{x^{2} - 3 y}{3 x - y^{2}}"
    evaluate = built.steps[-1]
    assert evaluate.expr == R(4, 5)
    # (4 - 12)/(6 - 16), shown before reducing.
    assert evaluate.latex == r"\left.\frac{dy}{dx}\right|_{(2, 4)} = \frac{-8}{-10} = \frac{4}{5}"


def test_bad_samples_are_rejected():
    # b^2 = 4ad: x^2 + 2xy + y^2 = 4 is the pair of lines x + y = +-2.
    with pytest.raises(ValueError):
        build("quadratic_mixed", {"a": 1, "b": 2, "d": 1, "c": 4})
    # At (3, 0) on 4x^2 + 9y^2 = 36 the tangent is vertical.
    with pytest.raises(ValueError):
        build("word_mirror", {"a": 4, "b": 9, "point": [3, 0]})
    # x^2 y + x y^2 through (1, -1) has constant 0, and the curve splits into lines.
    with pytest.raises(ValueError):
        build("slope_at_point", {"shape": "x2y_xy2", "coeffs": [1, 1], "point": [1, -1]})
    # On x^2 + xy + y^2 = 1 at (1, -1), forgetting dy/dx on y^2 still gives slope 1.
    with pytest.raises(ValueError):
        build("word_track", {"a": 1, "b": 1, "d": 1, "point": [1, -1]})


# --- mistake patterns -------------------------------------------------------------------


def test_signature_forgets_dydx_on_powers_of_y():
    assert MISSING_DYDX.signature
    assert [m for m in SKILL.mistakes if m.signature] == [MISSING_DYDX]

    # x^2 + xy + y^2 = 7 with d/dx(y^2) taken as 2y: 2x + y + x y' + 2y = 0.
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    assert on_curve(MISSING_DYDX.buggy(built), -(2 * x + 3 * y) / x, built.expr) is True
    # x^3 + y^3 = 6xy with d/dx(y^3) taken as 3y^2: 3x^2 + 3y^2 = 6y + 6x y'.
    built = build("folium", {"k": 6, "c": 0})
    assert on_curve(MISSING_DYDX.buggy(built), (x**2 + y**2 - 2 * y) / (2 * x), built.expr) is True
    # With y' only on the y^2 term there is nothing left to solve for.
    assert MISSING_DYDX.buggy(build("circle", {"r": 5, "d": 0, "side": "lhs"})) is None
    # x^2 y = 48 has no power of y on its own.
    assert MISSING_DYDX.buggy(build("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]})) is None
    # At a point the wrong answer is a number: -(2x + 3y)/x at (1, 2).
    assert MISSING_DYDX.buggy(build("word_track", {"a": 1, "b": 1, "d": 1, "point": [1, 2]})) == -8


def test_y_treated_as_constant_in_a_product():
    # d/dx(xy) taken as y: 2x + y + 2y y' = 0.
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    assert on_curve(Y_CONSTANT.buggy(built), -(2 * x + y) / (2 * y), built.expr) is True
    # x^2 y = 48 with d/dx(x^2 y) taken as 2xy leaves no y' at all.
    assert Y_CONSTANT.buggy(build("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]})) is None
    assert Y_CONSTANT.buggy(build("circle", {"r": 5, "d": 0, "side": "lhs"})) is None


def test_product_rule_missed():
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    # d/dx(xy) taken as x y': 2x + x y' + 2y y' = 0.
    assert on_curve(X_CONSTANT.buggy(built), -2 * x / (x + 2 * y), built.expr) is True
    # d/dx(xy) taken as (1)(y') = y': 2x + y' + 2y y' = 0.
    assert on_curve(PRODUCT_OF_DERIVATIVES.buggy(built), -2 * x / (1 + 2 * y), built.expr) is True

    built = build("folium", {"k": 6, "c": 0})
    # 3x^2 + 3y^2 y' = 6x y', and 3x^2 + 3y^2 y' = 6y'.
    assert on_curve(X_CONSTANT.buggy(built), x**2 / (2 * x - y**2), built.expr) is True
    assert on_curve(PRODUCT_OF_DERIVATIVES.buggy(built), x**2 / (2 - y**2), built.expr) is True

    # x^2 y = 48: x^2 y' = 0 and 2x y' = 0 both give a slope of 0.
    built = build("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]})
    assert X_CONSTANT.buggy(built) == 0
    assert PRODUCT_OF_DERIVATIVES.buggy(built) == 0

    # No product term, nothing to get wrong.
    assert X_CONSTANT.buggy(build("ellipse", {"a": 4, "b": 9, "p": 3, "q": 2})) is None
    assert PRODUCT_OF_DERIVATIVES.buggy(build("ellipse", {"a": 4, "b": 9, "p": 3, "q": 2})) is None


def test_isolation_errors():
    built = build("circle", {"r": 5, "d": 0, "side": "lhs"})
    assert on_curve(SIGN_SLIP.buggy(built), x / y, built.expr) is True
    assert on_curve(DIVIDED_WRONG_WAY.buggy(built), -y / x, built.expr) is True

    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    assert on_curve(SIGN_SLIP.buggy(built), (2 * x + y) / (x + 2 * y), built.expr) is True
    assert on_curve(DIVIDED_WRONG_WAY.buggy(built), -(x + 2 * y) / (2 * x + y), built.expr) is True

    built = build("word_mirror", {"a": 4, "b": 9, "point": [3, 2]})
    assert SIGN_SLIP.buggy(built) == R(2, 3)
    assert DIVIDED_WRONG_WAY.buggy(built) == R(-3, 2)


def test_constant_kept():
    # x^2 + y^2 = 25 differentiated as 2x + 2y y' = 25.
    built = build("circle", {"r": 5, "d": 0, "side": "lhs"})
    assert on_curve(CONSTANT_KEPT.buggy(built), (25 - 2 * x) / (2 * y), built.expr) is True
    # x^3 + y^3 = 6xy has no constant.
    assert CONSTANT_KEPT.buggy(build("folium", {"k": 6, "c": 0})) is None
    # 4x^2 + 9y^2 = 72 at (3, 2): 8x + 18y y' = 72 gives (72 - 24)/36.
    assert CONSTANT_KEPT.buggy(build("word_mirror", {"a": 4, "b": 9, "point": [3, 2]})) == R(4, 3)


def test_swapped_point():
    # -4x/(9y) at x = 2, y = 3 instead of x = 3, y = 2.
    assert SWAPPED_POINT.buggy(build("word_mirror", {"a": 4, "b": 9, "point": [3, 2]})) == R(-8, 27)
    # -2y/x at x = 3, y = 4.
    assert SWAPPED_POINT.buggy(build("word_isoquant", {"a": 2, "b": 1, "point": [4, 3]})) == R(-8, 3)
    # Only point problems, and only when swapping changes something.
    assert SWAPPED_POINT.buggy(build("circle", {"r": 5, "d": 0, "side": "lhs"})) is None
    assert SWAPPED_POINT.buggy(build("word_pendant", {"k": 6, "point": [3, 3]})) is None


def test_point_mistakes_are_numbers():
    built = build("slope_at_point", {"shape": "x3_xy_y2", "coeffs": [1, 1, -3], "point": [-1, 2]})
    answers = {m.tag + "@" + m.step: m.buggy(built) for m in SKILL.mistakes}
    assert all(v is None or (v.is_Rational and v != built.key) for v in answers.values())
    # x^3 + xy - 3y^2 = -15 with d/dx(-3y^2) taken as -6y: 3x^2 + y + x y' - 6y = 0 at (-1, 2).
    assert MISSING_DYDX.buggy(built) == -7


def test_mistake_tags_exist_and_notes_render():
    built = build("word_pendant", {"k": 9, "point": [2, 4]})
    step_ids = {s.id for s in built.steps}
    for m in SKILL.mistakes:
        mistake_type(m.tag)
        assert m.step in step_ids
        text = render(m.note, built)
        assert "[[" not in text and "—" not in text  # no em dashes
        assert text[0].isupper()


def test_hints_render_and_nudge_gives_nothing_away():
    for family_id, params, _ in SYMBOLIC_EXAMPLES[::4] + POINT_EXAMPLES:
        built = build(family_id, params)
        ladder = SKILL.hint_ladder(built)
        assert ladder.nudge.rstrip().endswith("?")
        assert "\\frac" not in ladder.nudge and "=" not in ladder.nudge
        for template in (ladder.nudge, ladder.bigger, ladder.full_step):
            assert "[[" not in render(template, built)
    built = build("quadratic_mixed", {"a": 1, "b": 1, "d": 1, "c": 7})
    bigger = render(SKILL.hint_ladder(built).bigger, built)
    assert r"\htmlClass{slate-mint}{y + x \frac{dy}{dx}}" in bigger
    assert r"\htmlClass{slate-yellow}{2 y \frac{dy}{dx}}" in bigger


def test_skill_metadata():
    assert SKILL.id == "calc1.derivatives.implicit_differentiation"
    assert SKILL.task == "implicit_differentiate"
    assert "implicit differentiation" in SKILL.keywords
    assert set(SKILL.prerequisites) == {"calc1.derivatives.chain_rule", "calc1.derivatives.product_rule"}


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
        assert (built.word is not None) == family.word
        json.dumps(built.params)
        report = verify_built(SKILL, built)
        assert report.ok, f"{family.id} seed {seed}: {[(c.name, c.detail) for c in report.failures]}"
        # build is pure: the same params give the same problem.
        again = family.build(params)
        assert again.key == built.key and again.prompt == built.prompt
    assert built_count >= 35, f"{family.id} rejected too many samples"
