import pytest
from slate_skills import all_skills, register_extra
from slate_skills.core.types import FormulaEntry, HintLadder, SkillSpec

from slate_api.services.ingest.notation import NotationProfile
from slate_api.services.lesson_gen import ChunkRef, generate_lesson_script
from slate_api.services.lesson_gen.compose import compose_script
from slate_api.services.lesson_gen.generate import check
from slate_api.services.lesson_gen.prompt import build_request
from slate_api.services.lesson_gen.schema import Lesson, find_phrase, to_script

CHUNKS = [ChunkRef("c1", "Week 3 slides", "slides", "slides 4-6", "The chain rule",
                   "Example: d/dx sin(x^3+1) = cos(x^3+1) * 3x^2")]
CHAIN = "calc1.derivatives.chain_rule"


def test_phrase_anchors():
    words = "Let u equal x cubed plus one, the inside.".split()
    assert find_phrase(words, "x cubed") == 3
    assert find_phrase(words, "plus ONE") == 5
    assert find_phrase(words, "not there") is None


def _seg(text="", math="", say=""):
    return {"text": text, "math": math, "say": say}


CLAIM = {"kind": "equal", "of": "", "var": "x", "equals": "", "left": "", "right": "", "vars": [], "to": "",
         "side": "", "lower": "", "upper": ""}
EXAMPLE_FIELDS = ("expr", "var", "name", "at", "equation", "dependent", "to", "side", "lower", "upper", "interval",
                  "goal", "report", "estimate", "relation", "variables", "values", "rates", "find")


def _empty_claim():
    return dict(CLAIM)


def _claim(**kw):
    return {**CLAIM, **kw}


def _example(**kw):
    base = {"kind": "other", "statement": "", "word": False, "answer": "", **{f: "" for f in EXAMPLE_FIELDS}}
    return {**base, **kw}


def _action(**kw):
    base = {"type": "write", "at_phrase": "", "id": "", "latex": "", "row": 0, "col": 0, "size": "md", "target": "",
            "part": "", "color": "chalk", "text": "", "side": "below"}
    return {**base, **kw}


def lesson(equals="cos(x^3+1)*3x^2", example=None):
    return Lesson.model_validate({
        "title": "The chain rule", "summary": "Inside and outside.",
        "example": example or _example(kind="derivative", statement="Differentiate $\\sin(x^3+1)$.",
                                       expr="sin(x^3+1)", var="x", name="f", answer="3x^2 cos(x^3+1)"),
        "steps": [
            {"id": "a", "title": "Start", "narration": [_seg(text="Here is "), _seg(math="f(x)=\\sin(x^3+1)",
                                                                                   say="f of x equals sine of x cubed plus one")],
             "actions": [_action(at_phrase="f of x", id="f", latex="f(x)=\\sin(x^3+1)")],
             "has_checkpoint": False, "checkpoint": {"prompt": "", "expect": _empty_claim(), "options": []},
             "claims": [], "sources": ["c1"]},
            {"id": "b", "title": "Answer", "narration": [_seg(text="So we get "), _seg(math="3x^2\\cos(x^3+1)",
                                                                                    say="three x squared cosine")],
             "actions": [_action(at_phrase="three x squared", id="ans", latex="3x^2\\cos(x^3+1)", row=1),
                         _action(type="box", at_phrase="cosine", target="ans", color="mint")],
             "has_checkpoint": False, "checkpoint": {"prompt": "", "expect": _empty_claim(), "options": []},
             "claims": [_claim(kind="derivative", of="sin(x^3+1)", equals=equals, vars=["x"])], "sources": []},
        ],
    })


def test_to_script_resolves_anchors_and_sources():
    script, problems = to_script(lesson(), CHUNKS, CHAIN)
    assert problems == []
    assert script["steps"][1]["actions"][1]["at"] == {"word": 6}
    assert [s["id"] for s in script["sources"]] == ["c1"]
    problems, record = check(script, CHUNKS)
    assert problems == [] and record["ok"]


class FakeLLM:
    available = True

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def structured(self, *, system, content, schema, effort, max_tokens):
        self.requests.append(content)
        return self.answers.pop(0)


def test_false_claim_is_sent_back_and_fixed():
    llm = FakeLLM([lesson(equals="cos(x^3+1)"), lesson()])
    result = generate_lesson_script(CHAIN, CHUNKS, None, llm=llm)
    assert result.method == "claude" and result.attempts == 2
    assert "false" in llm.requests[1]


def test_never_sound_falls_back_to_the_composer():
    llm = FakeLLM([lesson(equals="cos(x^3+1)")] * 3)
    result = generate_lesson_script(CHAIN, CHUNKS, None, llm=llm)
    assert result.method == "composer" and result.attempts == 3


@pytest.mark.parametrize("skill_id", [s.id for s in all_skills()])
def test_composer_is_sound_for_every_skill(skill_id):
    for seed in range(3):
        for notation in (None, NotationProfile("operator", "log", "w")):
            script = compose_script(skill_id, CHUNKS, notation, seed)
            assert check(script, CHUNKS)[0] == []
            assert script["sources"][0]["locator"] == "slides 4-6"
            assert any("checkpoint" in s for s in script["steps"])


def test_a_worked_example_sympy_disagrees_with_is_sent_back():
    wrong = _example(kind="derivative", statement="Differentiate $\\sin(x^3+1)$.", expr="sin(x^3+1)", var="x",
                     name="f", answer="cos(x^3+1)")
    llm = FakeLLM([lesson(example=wrong), lesson()])
    result = generate_lesson_script(CHAIN, CHUNKS, None, llm=llm)
    assert result.method == "claude" and result.attempts == 2
    assert "worked example" in llm.requests[1]
    assert result.record["ok"] and result.record["example"]["ok"]


LHOPITAL = "mine.test.lhopital"


def _register_topic():
    register_extra(SkillSpec(id=LHOPITAL, slug="lhopital", title="L'Hopital's rule", summary="0/0 limits.",
                             task="differentiate", families=(), mistakes=(), hints=HintLadder("", "", ""),
                             formula=FormulaEntry(title="L'Hopital's rule", latex="")))


def limit_lesson(equals="1"):
    say = "the limit of e to the x minus one over x"
    return Lesson.model_validate({
        "title": "L'Hopital's rule", "summary": "Zero over zero.",
        "example": _example(kind="limit", statement="Find $\\lim_{x \\to 0} \\frac{e^x - 1}{x}$.",
                            expr="(e^x - 1)/x", var="x", to="0", side="both", answer=equals),
        "steps": [
            {"id": "a", "title": "Zero over zero",
             "narration": [{"text": "Look at ", "math": "", "say": ""},
                           {"text": "", "math": "\\lim_{x \\to 0} \\frac{e^x-1}{x}", "say": say}],
             "actions": [_action(at_phrase="the limit", id="l", latex="\\lim_{x \\to 0} \\frac{e^x-1}{x}")],
             "has_checkpoint": True,
             "checkpoint": {"prompt": "What is the limit?",
                            "expect": _claim(kind="limit", of="(e^x-1)/x", to="0", side="both", equals=equals),
                            "options": [{"latex": "1", "value": "1", "say": "one", "correct": True, "why": "$e^0$."},
                                        {"latex": "0", "value": "0", "say": "zero", "correct": False, "why": "No."},
                                        {"latex": "\\text{DNE}", "value": "DNE", "say": "does not exist",
                                         "correct": False, "why": "It does."}]},
             "claims": [_claim(kind="limit", of="(e^x-1)/x", to="0", side="both", equals=equals),
                        _claim(kind="derivative", of="e^x - 1", equals="e^x", vars=["x"])],
             "sources": []},
        ],
    })


def test_a_topic_without_templates_gets_a_checked_lesson_on_limits():
    _register_topic()
    llm = FakeLLM([limit_lesson(equals="2"), limit_lesson()])
    result = generate_lesson_script(LHOPITAL, [], None, llm=llm,
                                    examples=[{"statement": "Find the limit of sin(x)/x at 0.", "answer": "1"}])
    assert result.method == "claude" and result.attempts == 2
    assert "claim is false" in llm.requests[1]
    assert "Topic: L'Hopital's rule" in llm.requests[0] and "sin(x)/x" in llm.requests[0]
    assert "no sources to cite" in llm.requests[0]


def test_a_topic_without_templates_has_no_composer_to_fall_back_on():
    _register_topic()
    llm = FakeLLM([limit_lesson(equals="2")] * 3)
    with pytest.raises(ValueError):
        generate_lesson_script(LHOPITAL, [], None, llm=llm)


def test_the_request_names_a_built_in_skills_formula_and_mistakes():
    text = build_request(CHAIN, CHUNKS, None)
    assert "Formula:" in text and "Common mistakes" in text and "[c1]" in text
