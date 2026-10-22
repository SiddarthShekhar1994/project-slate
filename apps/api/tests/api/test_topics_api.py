"""Topics on the dashboard: from uploads, typed in by name, or built in, each with a lesson, problems and worksheets."""

import pytest

from .test_materials_api import FakeClaude, review_pdf, upload, use

CHAIN = "calc1.derivatives.chain_rule"
PRODUCT = "calc1.derivatives.product_rule"
IMPLICIT = "calc1.derivatives.implicit_differentiation"


@pytest.fixture
def claude(monkeypatch):
    return use(monkeypatch, FakeClaude())


def dashboard(client) -> dict:
    r = client.get("/api/topics")
    assert r.status_code == 200, r.text
    return r.json()


def by_title(client) -> dict:
    return {t["title"]: t for t in dashboard(client)["topics"]}


def test_a_new_dashboard_suggests_topics(signed_in):
    data = dashboard(signed_in)
    assert data["topics"] == [] and data["claude"] is False
    suggestions = {s["title"]: s for s in data["suggestions"]}
    assert suggestions["Chain rule"]["builtin"] and not suggestions["Related rates"]["builtin"]
    assert {"L'Hôpital's rule", "Optimization", "Definite integrals"} <= set(suggestions)


def test_built_in_topics_are_added_by_name_without_a_key(signed_in):
    r = signed_in.post("/api/topics", json={"name": "the Chain Rule"})
    assert r.status_code == 201, r.text
    chain = r.json()
    assert (chain["id"], chain["builtin"], chain["lesson"], chain["practice"]) == (CHAIN, True, "done", "done")

    # The product rule has no hand-written lesson: the composer writes one in the background.
    product = signed_in.post("/api/topics", json={"name": "product rule"}).json()
    assert product["id"] == PRODUCT
    view = signed_in.get(f"/api/topics/{PRODUCT}").json()
    assert view["lesson"] == "done" and len(view["lessons"]) == 1 and view["lessons"][0]["kind"] == "generated"
    assert view["on_dashboard"] and view["formula"]["latex"]

    assert [t["id"] for t in dashboard(signed_in)["topics"]] == [CHAIN, PRODUCT]
    suggested = {s["title"] for s in dashboard(signed_in)["suggestions"]}
    assert "Chain rule" not in suggested and "Product rule" not in suggested

    # The lesson player's sidebar lists the student's topics.
    lesson = view["lessons"][0]
    outline = signed_in.get(f"/api/lessons/{lesson['id']}").json()["outline"]
    assert outline["unit"] == "Your topics" and [s["id"] for s in outline["skills"]] == [CHAIN, PRODUCT]


def test_other_topics_need_claude(signed_in):
    r = signed_in.post("/api/topics", json={"name": "related rates"})
    assert r.status_code == 409 and "Claude API key" in r.json()["detail"]
    assert signed_in.post("/api/topics", json={"name": "   "}).status_code == 422


def test_a_typed_topic_gets_checked_problems_a_lesson_and_worksheets(signed_in, claude):
    r = signed_in.post("/api/topics", json={"name": "lhopital"})
    assert r.status_code == 201, r.text
    topic_id = r.json()["id"]
    view = signed_in.get(f"/api/topics/{topic_id}").json()
    # Claude named it properly and wrote four problems; SymPy kept the three whose answers check out.
    assert view["title"] == "L'Hôpital's rule" and view["summary"].startswith("Limits of the form")
    assert (view["problems"], view["practice"], view["lesson"]) == (3, "done", "done")
    assert [p["difficulty"] for p in view["problem_list"]] == [1, 2, 3]
    assert {p["origin"] for p in view["problem_list"]} == {"variant"}
    assert view["origin"] == "added" and view["sources"] == []
    # The lesson taught toward those problems, and its worked example was checked.
    lesson_request = next(content for name, content in claude.calls if name == "Lesson")
    assert "Topic: L'Hôpital's rule" in lesson_request and "e^x - 1" in lesson_request
    lesson = signed_in.get(f"/api/lessons/{view['lessons'][0]['id']}").json()
    assert lesson["skill"]["title"] == "L'Hôpital's rule" and lesson["script"]["steps"]

    # One problem on its own, then a worksheet easy to hard.
    first = view["problem_list"][0]
    r = signed_in.post(f"/api/topics/{topic_id}/practice", json={"problem_ids": [first["id"]]})
    assert r.status_code == 201, r.text
    single = signed_in.get(f"/api/practice/worksheets/{r.json()['id']}").json()
    assert len(single["items"]) == 1 and single["items"][0]["problem"]["answer_kind"] == "limit"
    item = single["items"][0]
    graded = signed_in.post(f"/api/practice/items/{item['id']}/answer", json={"answer": "1"}).json()
    assert graded["grade"]["status"] == "correct"
    r = signed_in.post(f"/api/topics/{topic_id}/practice", json={"count": 3})
    assert r.status_code == 201, r.text
    view = signed_in.get(f"/api/topics/{topic_id}").json()
    assert [p["result"] for p in view["problem_list"]][0] == "solved"
    assert len(view["worksheets"]) == 2 and view["mastery"] is not None

    # A new lesson: while it's written the topic says so (even though it has one), then it's there.
    r = signed_in.post(f"/api/topics/{topic_id}/lesson")
    assert r.status_code == 202, r.text
    assert r.json()["lesson"] == "writing"
    view = signed_in.get(f"/api/topics/{topic_id}").json()
    assert view["lesson"] == "done" and len(view["lessons"]) == 2

    # Typing the same topic again finds it instead of making a second one.
    again = signed_in.post("/api/topics", json={"name": "L'Hopital's Rule"}).json()
    assert again["id"] == topic_id and len(dashboard(signed_in)["topics"]) == 1


def test_something_that_isnt_math_fails_gently_and_can_be_removed(signed_in, claude):
    topic_id = signed_in.post("/api/topics", json={"name": "pizza"}).json()["id"]
    card = by_title(signed_in)["pizza"]
    assert card["practice"] == "failed" and "math topic" in card["practice_error"]
    assert card["lesson"] == "failed"
    assert not any(name == "Lesson" for name, _ in claude.calls)
    assert signed_in.delete(f"/api/topics/{topic_id}").status_code == 204
    assert dashboard(signed_in)["topics"] == []
    # Its page still opens (its history is still there), offering to put it back.
    view = signed_in.get(f"/api/topics/{topic_id}").json()
    assert view["on_dashboard"] is False
    assert signed_in.delete(f"/api/topics/{topic_id}").status_code == 404


def test_an_uploaded_review_sheet_fills_the_dashboard(signed_in, claude):
    source = upload(signed_in, review_pdf()).json()
    topics = by_title(signed_in)
    assert {"Chain rule", "Implicit differentiation", "Product rule", "Limits", "Related rates",
            "Curve sketching"} <= set(topics)
    rates = topics["Related rates"]
    assert rates["sources"] == [{"id": source["id"], "title": source["title"]}]
    assert rates["origin"] == "upload" and rates["builtin"] is False
    # Every topic on the sheet has a lesson: built in, or written for it and checked.
    assert {t["lesson"] for t in topics.values()} == {"done"}
    assert topics["Chain rule"]["lessons"] == 1  # the hand-written one; no need to write another

    view = signed_in.get(f"/api/topics/{rates['id']}").json()
    sheet = [p for p in view["problem_list"] if p["origin"] == "sheet"]
    assert [(p["label"], p["result"], p["source"]["title"]) for p in sheet] == [("4", "new", source["title"])]
    sketch = signed_in.get(f"/api/topics/{topics['Curve sketching']['id']}").json()
    assert sketch["problem_list"][0]["status"] == "unsupported" and "sketch" in sketch["problem_list"][0]["reason"]

    # Removing a built-in topic unpins it; it comes back when added again.
    assert signed_in.delete(f"/api/topics/{PRODUCT}").status_code == 204
    assert "Product rule" not in by_title(signed_in)
    signed_in.post("/api/topics", json={"name": "Product rule"})
    assert "Product rule" in by_title(signed_in)


def test_an_exam_can_cover_topics_from_materials(signed_in, claude):
    upload(signed_in, review_pdf())
    topics = by_title(signed_in)
    limits, rates = topics["Limits"]["id"], topics["Related rates"]["id"]
    r = signed_in.post("/api/exam", json={"weights": {limits: 1, rates: 1, CHAIN: 1}, "count": 3, "pace": "exam"})
    assert r.status_code == 201, r.text
    items = r.json()["exam"]["items"]
    kinds = {i["skill"]["id"]: i["problem"]["answer_kind"] for i in items}
    assert kinds[limits] == "limit" and kinds[rates] == "number"
    limit_item = next(i for i in items if i["skill"]["id"] == limits)
    # "DNE" is a fine answer to a limit, even though it isn't an expression.
    r = signed_in.put(f"/api/exam/items/{limit_item['id']}/answer", json={"answer": "DNE"})
    assert r.status_code == 200, r.text


def test_work_left_unfinished_is_picked_up_again(signed_in, claude):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.orm import Session

    from slate_api.db import get_engine
    from slate_api.models import Topic

    topic_id = signed_in.post("/api/topics", json={"name": "lhopital"}).json()["id"]
    lessons = len(signed_in.get(f"/api/topics/{topic_id}").json()["lessons"])
    # The app was closed while a new lesson was being written.
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with Session(get_engine()) as db:
        topic = db.get(Topic, topic_id)
        topic.build = {**topic.build, "lesson": {"status": "pending", "at": long_ago}}
        db.commit()
    dashboard(signed_in)  # notices, and writes it now
    view = signed_in.get(f"/api/topics/{topic_id}").json()
    assert view["lesson"] == "done" and len(view["lessons"]) == lessons


def test_topics_from_before_lessons_were_written_get_one_now(signed_in, claude):
    """A sheet read by an older Slate has topics with no lessons and no record of trying: the dashboard starts them."""
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from slate_api.db import get_engine
    from slate_api.models import Lesson, Topic, TopicPin

    upload(signed_in, review_pdf())
    with Session(get_engine()) as db:
        db.execute(delete(Lesson).where(Lesson.user_id.is_not(None)))
        for row in [*db.query(Topic).all(), *db.query(TopicPin).all()]:
            row.build = None
        db.commit()
    before = sum(name == "Lesson" for name, _ in claude.calls)
    dashboard(signed_in)
    topics = by_title(signed_in)
    assert {t["lesson"] for t in topics.values()} == {"done"}
    assert sum(name == "Lesson" for name, _ in claude.calls) > before
    # Once tried, it isn't tried again on every visit.
    calls = len(claude.calls)
    dashboard(signed_in)
    assert len(claude.calls) == calls
