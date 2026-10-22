"""Reading and grading the answers to problems from course materials."""

import pytest
from slate_api.services.grading import grade_answer
from slate_api.services.materials.answers import preview
from slate_api.services.materials.problems import verified
from slate_api.services.materials.verify import check, usable_hints
from slate_api.services.verify import ParseError

RATES = {"kind": "related_rates", "relation": "x^2 + y^2 = 25", "variables": "x, y", "values": "x=3, y=4",
         "rates": "x=2", "find": "y"}
LADDER = ("A $5$ m ladder leans on a wall. Its foot slides away at $2$ m/s. "
          "How fast is the top moving when the foot is $3$ m out?")


def problem(spec: dict, claimed: str, **extra):
    out = check({"spec": spec, "answer": claimed, **extra})
    assert out["ok"], out
    return verified(out["params"], out["report"], usable_hints(spec["kind"], None), out["signature"],
                    skill_id="t", origin="sheet")


def grades(p, answers: dict[str, tuple[str, str | None]]):
    for raw, (status, tag) in answers.items():
        g = grade_answer(p, raw)
        assert g.status == status, (raw, g)
        if tag is not None:
            assert g.mistake is not None and g.mistake.tag == tag, (raw, g.mistake)


def test_tangent_lines_in_any_form():
    p = problem({"kind": "tangent_line", "expr": "x^3 - 2x", "at": "1"}, "y = x - 2")
    grades(p, {"y = x - 2": ("correct", None), "y + 1 = 1(x - 1)": ("correct", None), "x - 2": ("correct", None),
               "y = x + 3": ("incorrect", "tangent_wrong_point"), "y = 3x - 4": ("incorrect", "tangent_wrong_slope"),
               "y = ": ("invalid", None)})


def test_limits_with_infinity_and_dne():
    dne = problem({"kind": "limit", "expr": "abs(x)/x", "to": "0"}, "DNE")
    grades(dne, {"DNE": ("correct", None), "does not exist": ("correct", None),
                 "1": ("incorrect", "one_sided_limit")})
    infinite = problem({"kind": "limit", "expr": "1/(x-2)^2", "to": "2"}, "oo")
    grades(infinite, {"infinity": ("correct", None), "∞": ("correct", None), "-oo": ("incorrect", "sign_error"),
                      "DNE": ("incorrect", None)})


def test_antiderivatives_need_the_right_derivative_and_mention_c():
    p = problem({"kind": "antiderivative", "expr": "3x^2 + cos(x)"}, "x^3 + sin(x) + C")
    grades(p, {"x^3 + sin x + C": ("correct", None), "x^3 + sin(x) + 7": ("correct", None),
               "3x^3 + 3 sin(x)": ("incorrect", "coefficient_slip"), "6x - sin(x)": ("incorrect", None)})
    assert "+ C" in grade_answer(p, "x^3 + sin(x)").message
    assert grade_answer(p, "x^3 + sin(x) + C").message is None


def test_lists_of_values():
    p = problem({"kind": "solve", "equation": "x^2 - 4 = 0"}, "-2, 2")
    grades(p, {"x = ±2": ("correct", None), "x = 2 or x = -2": ("correct", None), "{-2, 2}": ("correct", None),
               "2": ("incorrect", "missed_value"), "2, -2, 0": ("incorrect", "extra_value"),
               "none": ("incorrect", "missed_value")})
    nothing = problem({"kind": "solve", "equation": "x^2 + 1 = 0"}, "none")
    grades(nothing, {"no solution": ("correct", None), "0": ("incorrect", "extra_value")})


def test_numbers_rounding_and_units_in_word_problems():
    rates = problem(RATES, "-3/2", statement=LADDER, word=True)
    grades(rates, {"-1.5 m/s": ("correct", None), "dy/dt = -3/2": ("correct", None),
                   "1.5": ("incorrect", "sign_error")})
    estimate = problem({"kind": "linear_approx", "expr": "sqrt(x)", "at": "4", "estimate": "4.1"}, "2.025")
    grades(estimate, {"2.03": ("correct", None), "2.0": ("incorrect", None), "2 x": ("invalid", None)})


def test_preview_reads_like_the_grader():
    import sympy as sp

    x = (sp.Symbol("x"),)
    assert preview("values", "x = ±2", ()) == "-2, 2"
    assert preview("limit", "dne", ()) == r"\text{DNE}"
    assert preview("line", "y = 3x - 2", x) == "y = 3 x - 2"
    assert preview("antiderivative", "x^2 + C", x).endswith("+ C")
    assert preview("number", "-3/2 ft/s", (), units=True) == r"- \frac{3}{2}"
    with pytest.raises(ParseError):
        preview("number", "", ())
