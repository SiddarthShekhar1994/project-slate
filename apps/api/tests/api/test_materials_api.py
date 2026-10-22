"""A review sheet, read by (a stand-in for) Claude, becomes checked practice."""

import io

import pymupdf
import pytest
from slate_api.routers import sources as sources_router
from slate_api.services.materials import service as materials_service
import re

from slate_api.services import lessons as lessons_service
from slate_api.services import topics as topics_service
from slate_api.services.lesson_gen.schema import Lesson
from slate_api.services.materials.read import SPEC_FIELDS, ProblemOut, SheetReading, StepOut, TopicOut
from slate_api.services.materials.variants import TopicPlan, VariantSet

CHAIN = "calc1.derivatives.chain_rule"
IMPLICIT = "calc1.derivatives.implicit_differentiation"
PRODUCT = "calc1.derivatives.product_rule"
LADDER = ("A $5$ m ladder leans against a wall. Its foot slides away at $2$ m/s. "
          "How fast is the top moving when the foot is $3$ m from the wall?")


def problem(**fields) -> ProblemOut:
    base = {name: "" for name in SPEC_FIELDS}
    base.update(label="", chunk=1, topic="", kind="other", word=False, statement="", difficulty=2, answer="",
                hints=["Look at the outside.", "Then the inside.", "Multiply them."],
                steps=[StepOut(title="Differentiate", latex="y'")], reason="")
    base.update(fields)
    return ProblemOut(**base)


TOPICS = [
    TopicOut(name="Chain rule", summary="Derivatives of compositions.", builtin=CHAIN),
    TopicOut(name="Implicit differentiation", summary="Derivatives on curves.", builtin=IMPLICIT),
    TopicOut(name="Limits", summary="Limits by algebra and known limits.", builtin="none"),
    TopicOut(name="Related rates", summary="Rates linked by an equation.", builtin="none"),
    TopicOut(name="Curve sketching", summary="Graphs from derivatives.", builtin="none"),
    TopicOut(name="Product rule", summary="Derivatives of products.", builtin=PRODUCT),
]
SHEET = [
    problem(label="1", topic="Chain rule", kind="derivative", statement=r"Find $\frac{dy}{dx}$ for $y = \sin(x^3)$.",
            expr="sin(x^3)", var="x", name="y", answer="3x^2 cos(x^3)"),
    problem(label="2", topic="Implicit differentiation", kind="implicit_derivative",
            statement=r"Find $\frac{dy}{dx}$ at $(3, 4)$ on $x^2 + y^2 = 25$.", equation="x^2 + y^2 = 25", var="x",
            dependent="y", at="x=3, y=4", answer="-3/4"),
    problem(label="3", topic="Limits", kind="limit", statement=r"Find $\lim_{x \to 0} \frac{\sin 3x}{x}$.",
            expr="sin(3x)/x", var="x", to="0", side="both", answer="3"),
    problem(label="4", topic="Related rates", kind="related_rates", word=True, statement=LADDER,
            relation="x^2 + y^2 = 25", variables="x, y", values="x=3, y=4", rates="x=2", find="y", answer="-3/2"),
    problem(label="5", topic="Curve sketching", kind="other", statement=r"Sketch $y = x^3 - 3x$.",
            reason="It asks for a sketch."),
    # Claude's answer is wrong here, so SymPy and Claude disagree and Slate won't grade it.
    problem(label="6", topic="Product rule", kind="derivative", statement=r"Differentiate $x^2 \sin x$.",
            expr="x^2 sin(x)", var="x", answer="2x sin(x)"),
]
VARIANTS = {
    "Related rates": [
        problem(kind="related_rates", word=True, topic="Related rates",
                statement=("A $13$ ft ladder leans against a wall. Its foot slides away at $3$ ft/s. How fast is "
                           "the top moving when the foot is $5$ ft from the wall?"),
                relation="x^2 + y^2 = 169", variables="x, y", values="x=5, y=12", rates="x=3", find="y",
                answer="-5/4"),
    ],
    "Limits": [
        problem(kind="limit", topic="Limits", statement=r"Find $\lim_{x \to 2} \frac{x^2 - 4}{x - 2}$.",
                expr="(x^2 - 4)/(x - 2)", var="x", to="2", side="both", answer="4"),
        problem(kind="limit", topic="Limits", statement=r"Find $\lim_{x \to 0} \frac{\sin 5x}{x}$.",
                expr="sin(5x)/x", var="x", to="0", side="both", answer="5"),
    ],
}


CLAIM = {"kind": "equal", "of": "", "var": "x", "equals": "", "left": "", "right": "", "vars": [], "to": "",
         "side": "", "lower": "", "upper": ""}
NO_CHECKPOINT = {"prompt": "", "expect": CLAIM, "options": []}
# The worked example each fake lesson solves, and a fact it states, by topic.
LESSON_MATH = {
    "Limits": ({"kind": "limit", "statement": r"Find $\lim_{x \to 0} \frac{\sin 3x}{x}$.", "expr": "sin(3x)/x",
                "var": "x", "to": "0", "side": "both", "answer": "3"},
               {**CLAIM, "kind": "limit", "of": "sin(3x)/x", "to": "0", "side": "both", "equals": "3"}),
    "Related rates": ({"kind": "related_rates", "statement": LADDER, "word": True, "relation": "x^2 + y^2 = 25",
                       "variables": "x, y", "values": "x=3, y=4", "rates": "x=2", "find": "y", "answer": "-3/2"},
                      {**CLAIM, "left": "-(2*3*2)/(2*4)", "right": "-3/2"}),
    "L'Hôpital's rule": ({"kind": "limit", "statement": r"Find $\lim_{x \to 0} \frac{e^x - 1}{x}$.",
                          "expr": "(e^x - 1)/x", "var": "x", "to": "0", "side": "both", "answer": "1"},
                         {**CLAIM, "kind": "limit", "of": "(e^x - 1)/x", "to": "0", "side": "both", "equals": "1"}),
}


def fake_lesson(topic: str) -> Lesson:
    example, claim = LESSON_MATH.get(topic, ({"kind": "other"}, {**CLAIM, "left": "2+2", "right": "4"}))
    blank = {"statement": "", "word": False, "answer": "", **{name: "" for name in SPEC_FIELDS}}
    action = {"type": "write", "at_phrase": "", "id": "", "latex": "", "row": 0, "col": 0, "size": "md",
              "target": "", "part": "", "color": "chalk", "text": "", "side": "below"}
    return Lesson.model_validate({
        "title": topic, "summary": f"{topic}, one step at a time.", "example": {**blank, **example},
        "steps": [
            {"id": "idea", "title": "The idea", "narration": [{"text": "Here is the big idea.", "math": "", "say": ""}],
             "actions": [{**action, "at_phrase": "big idea", "id": "a", "latex": "x"}], "has_checkpoint": False,
             "checkpoint": NO_CHECKPOINT, "claims": [], "sources": []},
            {"id": "work", "title": "Work it out", "narration": [{"text": "Now work the example.", "math": "", "say": ""}],
             "actions": [], "has_checkpoint": False, "checkpoint": NO_CHECKPOINT, "claims": [claim], "sources": []},
        ],
    })


PLANS = {
    "lhopital": TopicPlan(is_math=True, title="L'Hôpital's rule",
                          summary="Limits of the form 0/0 or ∞/∞, by differentiating the top and the bottom.",
                          problems=[
        problem(kind="limit", difficulty=1, statement=r"Find $\lim_{x \to 0} \frac{e^x - 1}{x}$.",
                expr="(e^x - 1)/x", var="x", to="0", side="both", answer="1"),
        problem(kind="limit", difficulty=2, statement=r"Find $\lim_{x \to 0} \frac{1 - \cos x}{x^2}$.",
                expr="(1 - cos(x))/x^2", var="x", to="0", side="both", answer="1/2"),
        problem(kind="limit", difficulty=3, statement=r"Find $\lim_{x \to \infty} \frac{x^2}{e^x}$.",
                expr="x^2/e^x", var="x", to="oo", side="both", answer="0"),
        # Claude slips here (the limit is 1), so SymPy drops it.
        problem(kind="limit", difficulty=2, statement=r"Find $\lim_{x \to 1} \frac{\ln x}{x - 1}$.",
                expr="ln(x)/(x - 1)", var="x", to="1", side="both", answer="2"),
    ]),
    "pizza": TopicPlan(is_math=False, title="Pizza", summary="", problems=[]),
}


class FakeClaude:
    model = "fake-claude"

    def __init__(self, available: bool = True):
        self.available = available
        self.calls: list[tuple[str, object]] = []

    def structured(self, *, system, content, schema, effort="medium", max_tokens=16000):
        self.calls.append((schema.__name__, content))
        if schema is SheetReading:
            return SheetReading(topics=TOPICS, problems=SHEET)
        if schema is VariantSet:
            for topic, problems in VARIANTS.items():
                if f"Topic: {topic}." in content:
                    return VariantSet(problems=problems)
            return VariantSet(problems=[])
        if schema is TopicPlan:
            return PLANS[content.split("typed: ", 1)[1].split("\n", 1)[0].strip().lower()]
        if schema is Lesson:
            return fake_lesson(re.match(r"Topic: (.+?)\.", content).group(1))
        raise AssertionError(f"unexpected request for {schema.__name__}")


def use(monkeypatch, fake: FakeClaude) -> FakeClaude:
    for module in (materials_service, sources_router, topics_service, lessons_service):
        monkeypatch.setattr(module, "get_llm", lambda: fake)
    return fake


@pytest.fixture
def claude(monkeypatch):
    return use(monkeypatch, FakeClaude())


def review_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "MATH 30 Midterm 2 Review", fontsize=18)
    lines = ["1. Find dy/dx for y = sin(x^3).", "2. Find dy/dx at (3, 4) on x^2 + y^2 = 25.",
             "3. Find the limit of sin(3x)/x as x approaches 0.",
             "4. A 5 m ladder slides down a wall at 2 m/s. How fast is the top moving?",
             "5. Sketch y = x^3 - 3x.", "6. Differentiate x^2 sin x."]
    for i, line in enumerate(lines):
        page.insert_text((72, 120 + 24 * i), line, fontsize=11)
    return doc.tobytes()


def upload(client, data: bytes, name="MATH 30-Midterm2-Review.pdf"):
    files = {"file": (name, io.BytesIO(data), "application/pdf")}
    return client.post("/api/sources", files=files)


def answer(client, item_id: str, text: str) -> dict:
    r = client.post(f"/api/practice/items/{item_id}/answer", json={"answer": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_review_sheet_becomes_checked_practice(signed_in, claude):
    sid = upload(signed_in, review_pdf()).json()["id"]
    source = signed_in.get(f"/api/sources/{sid}").json()
    reading = source["reading"]
    assert reading["status"] == "done", reading
    assert (reading["problems"], reading["ready"]) == (6, 4)
    topics = {t["title"]: t for t in reading["topics"]}
    assert set(topics) == {"Chain rule", "Implicit differentiation", "Limits", "Related rates", "Curve sketching",
                           "Product rule"}
    assert topics["Chain rule"]["builtin"] and not topics["Related rates"]["builtin"]
    reasons = {p["label"]: p["reason"] for p in reading["not_checked"]}
    assert set(reasons) == {"5", "6"} and "sketch" in reasons["5"] and "didn't agree" in reasons["6"]
    # Found by the math, not the wording: the sheet never says "chain rule".
    assert any(s["id"] == CHAIN for s in source["skills"])

    # One request read the sheet with its page images; the rest wrote similar problems
    # for the topics Slate has no templates for.
    first_schema, first_content = claude.calls[0]
    assert first_schema == "SheetReading" and any(block["type"] == "image" for block in first_content)
    # Then lessons, for each topic the sheet covers that doesn't have one yet.
    names = [name for name, _ in claude.calls[1:]]
    assert set(names) == {"VariantSet", "Lesson"} and names.index("Lesson") > names.index("VariantSet")

    sheet = signed_in.post(f"/api/sources/{sid}/practice")
    assert sheet.status_code == 201, sheet.text
    items = sheet.json()["items"]
    assert [i["problem"]["label"] for i in items] == ["1", "2", "3", "4"]
    assert [i["problem"]["answer_kind"] for i in items] == ["expression", "number", "limit", "number"]
    assert items[3]["problem"]["is_word"] and "ladder" in items[3]["problem"]["prompt"]
    assert items[0]["problem"]["source"]["title"] == source["title"]

    # A limit is graded as a limit.
    assert answer(signed_in, items[2]["id"], "3")["grade"]["status"] == "correct"

    # Related rates: a sign slip, then a similar problem written for the topic and checked.
    r = answer(signed_in, items[3]["id"], "1.5 m/s")
    assert r["grade"]["status"] == "incorrect" and r["grade"]["mistake"]["tag"] == "sign_error"
    r = signed_in.post(f"/api/practice/items/{items[3]['id']}/similar").json()
    assert "13" in r["item"]["problem"]["prompt"]
    assert answer(signed_in, items[3]["id"], "-1.25 ft/s")["grade"]["status"] == "correct"

    # A chain rule miss gets a fresh problem from Slate's own chain rule templates.
    assert answer(signed_in, items[0]["id"], "cos(x^3)")["grade"]["status"] == "incorrect"
    r = signed_in.post(f"/api/practice/items/{items[0]['id']}/similar").json()
    assert r["item"]["skill"]["id"] == CHAIN and not r["item"]["problem"]["label"]

    # The new topics are skills of their own: practice, progress and review know them.
    topics = {t["title"]: t for t in signed_in.get("/api/materials/topics").json()["topics"]}
    assert {"Limits", "Related rates", "Curve sketching"} <= set(topics)
    assert topics["Limits"]["problems"] == 3 and topics["Limits"]["sources"] == [source["title"]]
    r = signed_in.post("/api/practice/worksheets", json={"skill_ids": [topics["Limits"]["id"]], "count": 2})
    assert r.status_code == 201, r.text
    assert [i["problem"]["answer_kind"] for i in r.json()["items"]] == ["limit", "limit"]
    assert r.json()["skills"][0]["title"] == "Limits"
    progress = signed_in.get("/api/progress").json()
    # Progress groups the student's topics by the material they came from.
    [mine] = progress["courses"]
    sheet = next(u for u in mine["units"] if u["title"] == source["title"])
    rates = next(s for s in sheet["skills"] if s["title"] == "Related rates")
    assert rates["attempts"] == 2
    queue = progress["review"]["due"] + progress["review"]["upcoming"]
    assert any(card["skill"]["title"] == "Related rates" for card in queue)


def test_practice_needs_checked_problems_and_the_owner(signed_in, client, monkeypatch):
    fake = use(monkeypatch, FakeClaude())
    sid = upload(signed_in, review_pdf()).json()["id"]
    assert signed_in.post(f"/api/sources/{sid}/practice").status_code == 201
    signed_in.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "bo@example.com", "password": "correct horse",
                                         "display_name": "Bo"})
    assert client.post(f"/api/sources/{sid}/practice").status_code == 404
    # Someone else's topic isn't a skill they can practice.
    assert client.post("/api/practice/worksheets", json={"skill_ids": ["mine.000000000000.limits"]}).status_code == 422
    assert fake.calls


def test_without_a_key_sources_wait_and_are_read_once_one_is_set(signed_in, monkeypatch):
    use(monkeypatch, FakeClaude(available=False))
    sid = upload(signed_in, review_pdf()).json()["id"]
    assert signed_in.get(f"/api/sources/{sid}").json()["reading"]["status"] == "no_key"
    r = signed_in.post(f"/api/sources/{sid}/read")
    assert r.status_code == 409 and "Claude API key" in r.json()["detail"]
    assert signed_in.post(f"/api/sources/{sid}/practice").status_code == 409

    on = use(monkeypatch, FakeClaude())
    listing = signed_in.get("/api/sources").json()
    assert listing["sources"][0]["reading"]["status"] == "pending"
    assert signed_in.get(f"/api/sources/{sid}").json()["reading"]["status"] == "done"
    assert on.calls[0][0] == "SheetReading"
    # Read once: listing again doesn't start another read.
    calls = len(on.calls)
    signed_in.get("/api/sources")
    assert len(on.calls) == calls


def test_a_failed_read_says_so_and_can_be_retried(signed_in, monkeypatch):
    from slate_api.services.llm import LLMUnavailable

    class Down(FakeClaude):
        def structured(self, **kwargs):
            raise LLMUnavailable("overloaded")

    use(monkeypatch, Down())
    sid = upload(signed_in, review_pdf()).json()["id"]
    reading = signed_in.get(f"/api/sources/{sid}").json()["reading"]
    assert reading["status"] == "failed" and "Try again" in reading["error"]
    use(monkeypatch, FakeClaude())
    assert signed_in.post(f"/api/sources/{sid}/read").status_code == 202
    assert signed_in.get(f"/api/sources/{sid}").json()["reading"]["status"] == "done"


def test_preview_by_answer_kind(signed_in):
    def preview(text, kind, variables=(), units=False):
        return signed_in.post("/api/math/preview", json={"text": text, "variables": list(variables),
                                                          "answer_kind": kind, "units": units}).json()

    assert preview("x = ±2", "values")["latex"] == "-2, 2"
    assert preview("DNE", "limit")["latex"] == r"\text{DNE}"
    assert preview("y = 3x - 2", "line", ["x"])["ok"]
    assert not preview("2 x", "number")["ok"]
    assert preview("-3/2 ft/s", "number", units=True)["latex"] == r"- \frac{3}{2}"
