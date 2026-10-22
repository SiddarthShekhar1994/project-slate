"""SymPy's answer keys for problems read from course materials."""

import pytest
import sympy as sp
from slate_api.services.materials.kinds import DNE, SpecError, answer_kind, build, key_latex

x = sp.Symbol("x")
WORD = ("A $5$ m ladder leans on a wall. Its foot slides away at $2$ m/s. "
        "How fast is the top moving when the foot is $3$ m out?")


def key(spec: dict, **params):
    return build({"spec": spec, **params}).key


@pytest.mark.parametrize("spec,expected", [
    ({"kind": "derivative", "expr": "x^2 sin(x)"}, 2 * x * sp.sin(x) + x**2 * sp.cos(x)),
    ({"kind": "derivative", "expr": "sqrt(x) e^x", "at": "1"}, sp.Rational(3, 2) * sp.E),
    ({"kind": "implicit_derivative", "equation": "x^2 + y^2 = 25", "at": "x=3, y=4"}, sp.Rational(-3, 4)),
    ({"kind": "tangent_line", "expr": "x^3 - 2x", "at": "1"}, x - 2),
    ({"kind": "tangent_line", "equation": "x^2 + xy + y^2 = 7", "at": "x=1, y=2"}, sp.Rational(14, 5) - 4 * x / 5),
    ({"kind": "linear_approx", "expr": "sqrt(x)", "at": "4"}, x / 4 + 1),
    ({"kind": "linear_approx", "expr": "sqrt(x)", "at": "4", "estimate": "4.1"}, sp.Rational(81, 40)),
    ({"kind": "limit", "expr": "sin(3x)/x", "to": "0"}, 3),
    ({"kind": "limit", "expr": "abs(x)/x", "to": "0"}, DNE),
    ({"kind": "limit", "expr": "abs(x)/x", "to": "0", "side": "left"}, -1),
    ({"kind": "limit", "expr": "1/(x-2)^2", "to": "2"}, sp.oo),
    ({"kind": "limit", "expr": "(3x^2+1)/(x^2-5)", "to": "oo"}, 3),
    ({"kind": "antiderivative", "expr": "3x^2 + cos(x)"}, x**3 + sp.sin(x)),
    ({"kind": "definite_integral", "expr": "x^2", "lower": "0", "upper": "3"}, 9),
    ({"kind": "solve", "equation": "x^2 - 4 = 0"}, sp.FiniteSet(-2, 2)),
    ({"kind": "solve", "equation": "2 sin(x) = 1", "interval": "[0, 2pi]"}, sp.FiniteSet(sp.pi / 6, 5 * sp.pi / 6)),
    ({"kind": "solve", "equation": "x^(1/3) = -2"}, sp.FiniteSet(-8)),
    ({"kind": "critical_points", "expr": "x^3 - 3x"}, sp.FiniteSet(-1, 1)),
    ({"kind": "critical_points", "expr": "x^(1/3) (x - 4)"}, sp.FiniteSet(0, 1)),
    ({"kind": "extremum", "expr": "x^3 - 3x", "interval": "[0, 2]", "goal": "min"}, -2),
    ({"kind": "extremum", "expr": "x^(2/3)", "interval": "[-1, 8]", "goal": "max"}, 4),
    ({"kind": "extremum", "expr": "2x + 50/x", "interval": "(0, oo)", "goal": "min", "report": "location"},
     sp.FiniteSet(5)),
])
def test_keys(spec, expected):
    got = key(spec)
    if isinstance(expected, sp.FiniteSet) or expected in (DNE, sp.oo, -sp.oo):
        assert got == expected
    else:
        assert sp.simplify(got - expected) == 0


def test_related_rates_uses_the_statement():
    spec = {"kind": "related_rates", "relation": "x^2 + y^2 = 25", "variables": "x, y", "values": "x=3, y=4",
            "rates": "x=2", "find": "y"}
    built = build({"spec": spec, "statement": WORD})
    assert built.key == sp.Rational(-3, 2) and built.prompt == WORD and answer_kind(built) == "number"
    with pytest.raises(SpecError, match="statement"):
        build({"spec": spec})


@pytest.mark.parametrize("spec,message", [
    ({"kind": "derivative"}, "no expr"),
    ({"kind": "derivative", "expr": "3"}, "doesn't depend"),
    ({"kind": "derivative", "expr": "q^2", "var": "q"}, "isn't one Slate can use"),
    ({"kind": "implicit_derivative", "equation": "x^2 + y^2 = 25", "at": "x=1, y=1"}, "isn't on the curve"),
    ({"kind": "tangent_line", "equation": "x^2 + y^2 = 25", "at": "x=5, y=0"}, "vertical"),
    ({"kind": "solve", "equation": "sin(x) = 0"}, "infinitely many"),
    ({"kind": "extremum", "expr": "x^2", "interval": "(0, 1)", "goal": "max"}, "nothing to compare"),
    ({"kind": "related_rates", "relation": "x^2 + y^2 = 25", "variables": "x, y", "values": "x=3, y=3",
      "rates": "x=2", "find": "y"}, "don't satisfy"),
    ({"kind": "proof"}, "can't check"),
    ({"kind": "derivative", "expr": "__import__('os')"}, "couldn't read"),
])
def test_specs_that_cannot_be_checked(spec, message):
    with pytest.raises(SpecError, match=message):
        key(spec, statement=WORD)


def test_prompts_and_key_latex():
    built = build({"spec": {"kind": "limit", "expr": "abs(x)/x", "to": "0", "side": "right"}})
    assert built.prompt == r"Find $\lim\limits_{x \to 0^{+}} \frac{\left|{x}\right|}{x}$." and built.key == 1
    assert key_latex(DNE) == r"\text{DNE}" and key_latex(sp.FiniteSet()) == r"\text{none}"
    estimate = build({"spec": {"kind": "linear_approx", "expr": "sqrt(x)", "at": "4", "estimate": "4.1"}})
    assert "f(4.1)" in estimate.prompt  # the decimal as written, not 41/10


def test_a_stored_key_is_used_without_recomputing(monkeypatch):
    built = build({"spec": {"kind": "antiderivative", "expr": "2x"}})
    stored = dict(built.params)
    monkeypatch.setattr(sp, "integrate", lambda *a, **k: pytest.fail("the oracle ran again"))
    assert build(stored).key == built.key


def test_topics_registered_elsewhere_are_found_on_first_use():
    from slate_skills import get_skill, set_extra_resolver
    from slate_skills.core.types import FormulaEntry, HintLadder, SkillSpec

    spec = SkillSpec(id="mine.abc.related-rates", slug="related-rates", title="Related rates", summary="",
                     task="differentiate", families=(), mistakes=(), hints=HintLadder("", "", ""),
                     formula=FormulaEntry("Related rates", ""))
    set_extra_resolver(lambda skill_id: spec if skill_id == spec.id else None)
    try:
        assert get_skill(spec.id).title == "Related rates"
        with pytest.raises(KeyError):
            get_skill("mine.abc.nothing")
    finally:
        set_extra_resolver(None)
