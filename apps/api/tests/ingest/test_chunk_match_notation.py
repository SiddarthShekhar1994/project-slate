import json
from pathlib import Path

from slate_api.services.ingest.chunk import chunk_pages
from slate_api.services.ingest.match import match_skills, top_skill
from slate_api.services.ingest.notation import NotationProfile, apply_notation, detect_notation, notation_profile
from slate_api.services.ingest.types import Page

CHAIN = "calc1.derivatives.chain_rule"
PRODUCT = "calc1.derivatives.product_rule"
LONG = " ".join(["The chain rule handles a composite function by differentiating the outer function."] * 3)


def test_slides_group_by_title_and_keep_topics_apart():
    pages = [
        Page(1, "slide 1", "The chain rule", LONG),
        Page(2, "slide 2", "The chain rule (cont.)", LONG),
        Page(3, "slide 3", "Product rule", "The product rule: (fg)' = f'g + fg'."),
    ]
    chunks = chunk_pages(pages, "slides")
    assert [c.locator for c in chunks] == ["slides 1-2", "slide 3"]
    assert chunks[1].heading == "Product rule"


def test_skill_matching():
    chain = match_skills(LONG, "The chain rule")
    assert top_skill(chain)[0] == CHAIN and chain[CHAIN] > 0.8
    assert top_skill(match_skills("Use the product rule: derivative of a product of two functions."))[0] == PRODUCT
    syllabus = match_skills("Topics: power rule, product rule, quotient rule, chain rule, implicit differentiation.")
    assert len(syllabus) >= 4
    assert match_skills("Whisk the eggs and fold in the flour.") == {}


def test_notation_detection_and_professor_precedence():
    counts = detect_notation("Let u = x^2 + 1. Then dy/dx = dy/du * du/dx. Also ln x. Don't panic.")
    assert counts["derivative"]["leibniz"] == 3 and counts["inner"] == {"u": 1} and counts["log"] == {"ln": 1}
    profile = notation_profile([
        ("slides", "c1", {"derivative": {"operator": 2}}),
        ("textbook", "c2", {"derivative": {"prime": 10}}),
    ])
    assert profile.derivative == "operator" and profile.differs_from_textbook["derivative"]
    assert profile.evidence["derivative"] == ["c1"]


def test_apply_notation_keeps_latex_intact():
    script = json.loads((Path(__file__).resolve().parents[2] / "slate_api/lessons/builtin/"
                         "calc1.derivatives.chain_rule.json").read_text())
    profile = NotationProfile(derivative="leibniz", log="log", inner="w")
    for step in script["steps"]:
        for action in step["actions"]:
            if action["type"] != "write":
                continue
            out = apply_notation(action["latex"], profile)
            assert out.count("{") == out.count("}")
            assert "htmlClass{slate-" in out or "htmlClass" not in action["latex"]
            assert "\\cos" not in action["latex"] or "\\cos" in out
    assert apply_notation(r"f'(x) = \ln(u)", profile) == r"\frac{df}{dx} = \log(w)"
    assert apply_notation(r"f'(x)", None) == r"f'(x)"
