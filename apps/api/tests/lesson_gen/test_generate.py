import pytest
from slate_skills import all_skills

from slate_api.services.ingest.notation import NotationProfile
from slate_api.services.lesson_gen import ChunkRef, generate_lesson_script
from slate_api.services.lesson_gen.compose import compose_script
from slate_api.services.lesson_gen.generate import check
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


def _empty_claim():
    return {"kind": "equal", "of": "", "var": "x", "equals": "", "left": "", "right": "", "vars": []}


def _action(**kw):
    base = {"type": "write", "at_phrase": "", "id": "", "latex": "", "row": 0, "col": 0, "size": "md", "target": "",
            "part": "", "color": "chalk", "text": "", "side": "below"}
    return {**base, **kw}


def lesson(equals="cos(x^3+1)*3x^2"):
    return Lesson.model_validate({
        "title": "The chain rule", "summary": "Inside and outside.",
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
             "claims": [{"kind": "derivative", "of": "sin(x^3+1)", "var": "x", "equals": equals, "left": "",
                         "right": "", "vars": ["x"]}], "sources": []},
        ],
    })


def test_to_script_resolves_anchors_and_sources():
    script, problems = to_script(lesson(), CHUNKS, CHAIN)
    assert problems == []
    assert script["steps"][1]["actions"][1]["at"] == {"word": 6}
    assert [s["id"] for s in script["sources"]] == ["c1"]
    assert check(script, CHUNKS) == []


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
            assert check(script, CHUNKS) == []
            assert script["sources"][0]["locator"] == "slides 4-6"
            assert any("checkpoint" in s for s in script["steps"])
