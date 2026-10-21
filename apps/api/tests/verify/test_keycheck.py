from dataclasses import replace

import sympy as sp
from slate_skills import get_skill
from slate_skills.core.types import Built, FormulaEntry, HintLadder, MistakePattern, SkillSpec, Step
from slate_skills.courses.calc1.derivatives.chain_rule import build_chain

from slate_api.services.verify import oracle_answer, verify_built

x, y = sp.symbols("x y")
CHAIN = get_skill("calc1.derivatives.chain_rule")


def chain(layers, inner, **kw):
    return build_chain(family="test", difficulty=2, var=x, layers=layers, inner=inner, params={}, **kw)


def failed(report):
    return {c.name for c in report.failures}


def test_a_sound_problem_passes_every_check():
    report = verify_built(CHAIN, chain(["sin"], x**3 + 1))
    assert report.ok, report.failures
    assert report.oracle == "sympy.diff"
    names = {c.name for c in report.checks}
    assert {"oracle", "finite", "well_formed", "domain", "steps", "mistakes", "signature", "text", "size"} <= names


def test_a_wrong_key_is_rejected():
    built = chain(["sin"], x**3 + 1)
    wrong = replace(built, key=sp.cos(x**3 + 1))  # dropped the inner derivative
    report = verify_built(CHAIN, wrong)
    assert not report.ok
    assert "oracle" in failed(report)


def test_a_key_that_is_only_numerically_close_is_rejected():
    built = chain(["sin"], x**3 + 1)
    nearly = replace(built, key=built.key + sp.Rational(1, 10**9) * x)
    assert "oracle" in failed(verify_built(CHAIN, nearly))


def test_signature_mistake_must_differ_from_the_key():
    # The inside's derivative is 1, so dropping it changes nothing: useless for practice.
    report = verify_built(CHAIN, chain([["pow", 5, 1]], x + 3))
    assert "signature" in failed(report)


def test_function_must_be_real_somewhere():
    report = verify_built(CHAIN, chain(["ln"], -(x**2) - 1))
    assert "domain" in failed(report)


def test_huge_coefficients_are_rejected():
    report = verify_built(CHAIN, chain([["pow", 2, 1]], 999 * x + 1))
    assert "size" in failed(report)


def test_unbalanced_math_in_prompt_is_rejected():
    built = replace(chain(["sin"], x**3 + 1), prompt="Differentiate $f(x) = \\sin(x^3+1).")
    assert "text" in failed(verify_built(CHAIN, built))


def test_point_problems_need_a_number():
    built = chain([["pow", 3, 1]], 2 * x + 1, at={"value": 1})
    assert verify_built(CHAIN, built).ok
    still_symbolic = replace(built, key=built.key + x)
    assert not verify_built(CHAIN, still_symbolic).ok


def test_broken_mistake_pattern_is_caught():
    def explode(_built):
        raise ZeroDivisionError("boom")

    broken = replace(CHAIN, mistakes=(*CHAIN.mistakes, MistakePattern("sign_error", "multiply", explode, "note")))
    report = verify_built(broken, chain(["sin"], x**3 + 1))
    assert "mistakes" in failed(report)


def test_task_mismatch_is_rejected():
    built = replace(chain(["sin"], x**3 + 1), task="implicit_differentiate")
    assert not verify_built(CHAIN, built).ok


def _implicit_skill() -> SkillSpec:
    return SkillSpec(
        id="test.implicit", slug="implicit", title="Implicit", summary="", task="implicit_differentiate",
        families=(), mistakes=(), hints=HintLadder("n", "b", "f"), formula=FormulaEntry("t", "l"),
    )


def _circle(key):
    return Built(
        family="circle", difficulty=1, task="implicit_differentiate", var=x, dependent=y,
        expr=x**2 + y**2 - 25, equation=sp.Eq(x**2 + y**2, 25), key=key,
        steps=(Step("solve", r"Solve for $\frac{dy}{dx}$", r"\frac{dy}{dx} = -\frac{x}{y}", expr=key),),
        parts={}, params={}, prompt=r"Find $\frac{dy}{dx}$ if $x^2 + y^2 = 25$.",
    )


def test_implicit_oracle_and_curve_comparison():
    name, answer = oracle_answer(_circle(-x / y))
    assert name == "implicit_function_theorem"
    assert sp.simplify(answer + x / y) == 0
    assert verify_built(_implicit_skill(), _circle(-x / y)).ok
    assert "oracle" in failed(verify_built(_implicit_skill(), _circle(x / y)))


def test_report_serialises():
    data = verify_built(CHAIN, chain(["sin"], x**3 + 1)).as_dict()
    assert data["ok"] is True
    assert all({"name", "passed", "detail"} <= set(c) for c in data["checks"])


def test_math_outside_dollar_signs_is_rejected():
    from slate_api.services.verify.keycheck import plain_text_math

    assert plain_text_math("Differentiate $f(x) = x^2 + \\sqrt{x}$.") is None
    assert plain_text_math("It costs $5 and $6.") is None
    for bad in ["Use x^2 here", "the rule d/dx of", "take sqrt(x)", "write \\frac{a}{b}", "so 3*x", "then f'(x) is"]:
        assert plain_text_math(bad), bad
    built = replace(chain(["sin"], x**3 + 1), prompt="Differentiate f(x) = sin(x^3 + 1).")
    assert "text" in failed(verify_built(CHAIN, built))
