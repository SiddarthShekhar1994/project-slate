import re

import pytest
import sympy as sp
from slate_skills import all_skills, get_skill

from slate_api.services.grading import grade_answer
from slate_api.services.grading.grade import _rounded_match
from slate_api.services.problem_gen import generate
from slate_api.services.verify import constraint_of, equivalent

CHAIN = "calc1.derivatives.chain_rule"
x = sp.Symbol("x")


def typed(expr: sp.Expr) -> str:
    """What a student would type for ``expr``: SymPy's string form with ^ and e."""
    text = sp.sstr(expr).replace("**", "^")
    return re.sub(r"\bE\b", "e", text)


def test_correct_answer_in_many_forms():
    p = generate(CHAIN, 2, 3, family="trig_poly")
    inside = p.built.parts["inside"]
    key = p.built.key
    forms = [
        typed(key),
        typed(sp.expand(key)),
        f"{typed(p.built.parts['inside_prime'])} * (-sin({typed(inside)}))",
        typed(key).replace("*", " "),
    ]
    for form in forms:
        grade = grade_answer(p, form)
        assert grade.status == "correct", (form, grade)
        assert grade.latex


def test_wrong_answer_shows_what_was_typed_and_where_to_look():
    p = generate(CHAIN, 2, 3, family="trig_poly")
    dropped = p.built.parts["outer_prime_at_inside"]
    grade = grade_answer(p, typed(dropped))
    assert grade.status == "incorrect"
    assert grade.latex == sp.latex(dropped, ln_notation=True, order="none") or grade.latex
    assert grade.mistake.tag == "dropped_inner_derivative"
    assert grade.mistake.step_id == "multiply"
    assert "inside" in grade.mistake.where_to_look
    assert "$" in grade.mistake.where_to_look


@pytest.mark.parametrize("family, tag", [
    ("trig_poly", "trig_derivative_sign"),
    ("poly_power", "power_exponent_not_reduced"),
    ("negative_power", "negative_exponent_slip"),
    ("fractional_power", "power_coefficient_dropped"),
    ("exp_linear", "exp_log_derivative_error"),
])
def test_chain_rule_patterns_are_tagged(family, tag):
    skill = get_skill(CHAIN)
    pattern = next(m for m in skill.mistakes if m.tag == tag)
    for seed in range(6):
        p = generate(CHAIN, skill.family(family).difficulty, seed, family=family)
        wrong = pattern.buggy(p.built)
        if wrong is None:
            continue
        grade = grade_answer(p, typed(wrong))
        assert grade.status == "incorrect"
        assert grade.mistake.tag == tag, (p.built.prompt, typed(wrong), grade.mistake)
        return
    pytest.fail(f"no {family} problem where {tag} applies")


def test_generic_tags():
    p = generate(CHAIN, 2, 11, family="exp_poly")
    key = p.built.key  # (2a x + b) * e^(a x^2 + b x)
    inside = p.built.parts["inside"]
    a, b = p.params["a"], p.params["b"]
    assert b != 0
    cases = {
        "coefficient_slip": 2 * key,
        "dropped_term": 2 * a * x * sp.exp(inside),
        "sign_error": (2 * a * x - b) * sp.exp(inside),
    }
    for tag, wrong in cases.items():
        grade = grade_answer(p, typed(wrong))
        assert grade.status == "incorrect"
        assert grade.mistake.tag == tag, (tag, typed(wrong), grade.mistake)


def test_algebra_slip_when_pieces_are_right():
    p = generate(CHAIN, 2, 3, family="trig_poly")
    inside = p.built.parts["inside"]
    wrong = -7 * x**5 * sp.sin(inside)
    grade = grade_answer(p, typed(wrong))
    assert grade.mistake.tag == "algebra_slip"


def test_unclassified_when_nothing_fits():
    p = generate(CHAIN, 2, 3, family="trig_poly")
    grade = grade_answer(p, "x^7 + 3")
    assert grade.status == "incorrect"
    assert grade.mistake.tag == "unclassified"
    assert grade.mistake.where_to_look


@pytest.mark.parametrize("text", ["", "sin(", "abc", "x = 3", "|x|"])
def test_invalid_input_is_not_a_miss(text):
    p = generate(CHAIN, 1, 1)
    grade = grade_answer(p, text)
    assert grade.status == "invalid"
    assert grade.mistake is None
    assert grade.message


def test_point_problems_want_a_number():
    p = generate(CHAIN, 2, 4, family="word_particle")
    assert grade_answer(p, typed(p.built.key)).status == "correct"
    grade = grade_answer(p, "3(2t+1)^2")
    assert grade.status == "invalid"
    assert "number" in grade.message
    assert grade_answer(p, typed(-p.built.key)).mistake.tag in {"sign_error", "trig_derivative_sign"}


def test_rounded_decimals():
    third = sp.Rational(1, 3)
    assert _rounded_match(sp.Rational("0.33"), third, 2)
    assert _rounded_match(sp.Rational("0.333"), third, 3)
    assert not _rounded_match(sp.Rational("0.34"), third, 2)
    assert not _rounded_match(sp.Rational("0.3"), third, 1)  # one place is too coarse to accept


# --- every skill, every pattern ------------------------------------------------------


def _expected_tag(skill, built, wrong):
    """The first pattern whose answer equals ``wrong``: the grader checks in order."""
    symbols = () if built.at else built.symbols
    constraint = None if built.at else constraint_of(built)
    for pattern in skill.mistakes:
        candidate = pattern.buggy(built)
        if candidate is None:
            continue
        if equivalent(wrong, candidate, symbols, constraint=constraint).equal is not False:
            return pattern.tag
    return None


@pytest.mark.parametrize("skill_id", [s.id for s in all_skills()])
def test_round_trip_every_pattern(skill_id):
    """Type each pattern's wrong answer back in; the grader must name that mistake.

    This runs the parser, the equivalence check and the classifier together
    over every family of every skill.
    """
    skill = get_skill(skill_id)
    checked = 0
    for fam in skill.families:
        for seed in range(2):
            p = generate(skill_id, fam.difficulty, seed, family=fam.id)
            assert grade_answer(p, typed(p.built.key)).status == "correct", (fam.id, typed(p.built.key))
            symbols = () if p.built.at else p.built.symbols
            constraint = None if p.built.at else constraint_of(p.built)
            for pattern in skill.mistakes:
                wrong = pattern.buggy(p.built)
                if wrong is None:
                    continue
                if equivalent(wrong, p.built.key, symbols, constraint=constraint).equal is not False:
                    continue  # this mistake happens to be harmless on this problem
                grade = grade_answer(p, typed(wrong))
                assert grade.status == "incorrect", (fam.id, pattern.tag, typed(wrong))
                assert grade.mistake.tag == _expected_tag(skill, p.built, wrong), (
                    fam.id, pattern.tag, typed(wrong), grade.mistake)
                checked += 1
    assert checked > 0
