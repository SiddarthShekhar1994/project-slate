import re
from datetime import datetime, timedelta, timezone

import pytest
import sympy as sp
from slate_skills import get_skill
from sqlalchemy import select
from sqlalchemy.orm import Session

from slate_api.db import get_engine
from slate_api.models import Problem, SkillCard, Source, SourceChunk, User, Worksheet
from slate_api.services import review
from slate_api.services.practice import load_problem

CHAIN = "calc1.derivatives.chain_rule"
POWER = "calc1.derivatives.power_rule"
PRODUCT = "calc1.derivatives.product_rule"
IMPLICIT = "calc1.derivatives.implicit_differentiation"


def typed(expr):
    return re.sub(r"\bE\b", "e", sp.sstr(expr).replace("**", "^"))


def built_for(problem_id):
    with Session(get_engine()) as db:
        return load_problem(db.get(Problem, problem_id)).built


def right(problem_id):
    return typed(built_for(problem_id).key)


def wrong(problem_id, tag=None):
    """A wrong answer: the given mistake pattern's answer, or the key plus one."""
    built = built_for(problem_id)
    if tag:
        with Session(get_engine()) as db:
            skill = get_skill(db.get(Problem, problem_id).skill_id)
        pattern = next(p for p in skill.mistakes if p.tag == tag)
        answer = pattern.buggy(built)
        if answer is not None:
            return typed(answer)
    return typed(built.key + 1)


def user_id(email="ada@example.com"):
    with Session(get_engine()) as db:
        return db.scalars(select(User.id).where(User.email == email)).one()


def answer(client, item_id, text):
    return client.post(f"/api/practice/items/{item_id}/answer", json={"answer": text}).json()


# --- review queue -------------------------------------------------------------------------


def test_clearing_a_problem_schedules_a_review(signed_in):
    client = signed_in
    sheet = client.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 1, "seed": 3}).json()
    item = sheet["items"][0]
    assert answer(client, item["id"], right(item["problem"]["id"]))["grade"]["status"] == "correct"

    data = client.get("/api/progress").json()
    chain = next(s for c in data["courses"] for u in c["units"] for s in u["skills"] if s["id"] == CHAIN)
    due = datetime.fromisoformat(chain["due_at"])
    assert timedelta(hours=23) < due - datetime.now(timezone.utc) <= timedelta(days=1)
    assert chain["attempts"] == 1 and chain["first_try_rate"] == 1.0
    assert data["review"]["due"] == [] and data["review"]["upcoming"][0]["skill"]["id"] == CHAIN

    # Nothing is due yet, so there is nothing to start.
    assert client.post("/api/progress/review", json={}).status_code == 409

    with Session(get_engine()) as db:
        card = db.scalars(select(SkillCard)).one()
        card.due_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
    queue = client.get("/api/progress/review").json()
    assert queue["due"][0]["skill"]["id"] == CHAIN and queue["due"][0]["overdue_days"] == 2

    r = client.post("/api/progress/review", json={})
    assert r.status_code == 201, r.text
    sheet = r.json()
    assert sheet["mode"] == "review" and len(sheet["items"]) == 2
    assert sheet["title"] == "Review: Chain rule"


def test_one_sitting_counts_as_one_review(signed_in):
    uid = user_id()
    start = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    with Session(get_engine()) as db:
        card = review.record(db, uid, CHAIN, 5, start)
        assert (card.repetitions, card.interval_days) == (1, 1)
        # Same sitting: the mean of 5 and 2 is 3, still a pass, still the first repetition.
        card = review.record(db, uid, CHAIN, 2, start + timedelta(hours=1))
        assert (card.repetitions, card.interval_days, card.lapses) == (1, 1, 0)
        assert card.due_at == start + timedelta(days=1)
        # A third poor item drags the sitting below 3: a lapse, back tomorrow.
        card = review.record(db, uid, CHAIN, 1, start + timedelta(hours=2))
        assert (card.repetitions, card.lapses) == (0, 1)
        # A new sitting builds on the lapsed card.
        card = review.record(db, uid, CHAIN, 5, start + timedelta(days=1))
        assert (card.repetitions, card.interval_days) == (1, 1)
        card = review.record(db, uid, CHAIN, 5, start + timedelta(days=2))
        assert (card.repetitions, card.interval_days) == (2, 6)
        db.commit()


# --- progress page ------------------------------------------------------------------------


def test_mistakes_are_ranked(signed_in):
    client = signed_in
    sheet = client.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 2, "seed": 11}).json()
    first, second = sheet["items"]
    r = answer(client, first["id"], wrong(first["problem"]["id"], "dropped_inner_derivative"))
    assert r["grade"]["mistake"]["tag"] == "dropped_inner_derivative"
    item = client.post(f"/api/practice/items/{first['id']}/similar").json()["item"]
    r = answer(client, item["id"], wrong(item["problem"]["id"], "dropped_inner_derivative"))
    assert r["grade"]["mistake"]["tag"] == "dropped_inner_derivative"
    r = answer(client, second["id"], wrong(second["problem"]["id"]))
    other = r["grade"]["mistake"]["tag"]
    assert other != "dropped_inner_derivative"

    data = client.get("/api/progress").json()
    top = data["mistakes"][0]
    assert top["tag"] == "dropped_inner_derivative" and top["count"] == 2 and top["recent"] == 2
    assert top["skills"] == [{"id": CHAIN, "title": "Chain rule", "count": 2}]
    assert top["label"] and top["description"] and top["category_label"]
    assert top["example"]
    assert data["mistakes"][1]["tag"] == other
    assert data["summary"] == {"answers": 3, "problems_cleared": 0, "first_try_rate": 0.0}


def test_formula_sheet(signed_in):
    data = signed_in.get(f"/api/progress/formula-sheet?skills={CHAIN},{POWER},nope").json()
    [unit] = data["units"]
    assert unit["title"] == "Derivatives"
    assert [e["skill"]["id"] for e in unit["entries"]] == [POWER, CHAIN]
    assert all(e["latex"] and e["title"] for e in unit["entries"])
    assert data["notation"] is None
    everything = signed_in.get("/api/progress/formula-sheet").json()
    assert len(everything["units"][0]["entries"]) == 5


def test_progress_needs_sign_in(client):
    assert client.get("/api/progress").status_code == 401


# --- exams --------------------------------------------------------------------------------------


def test_exam_flow(signed_in):
    client = signed_in
    weights = client.get(f"/api/exam/weights?skills={CHAIN},{POWER}").json()["weights"]
    assert [(w["skill_id"], w["weight"], w["source"]) for w in weights] == [(CHAIN, 50.0, None), (POWER, 50.0, None)]

    r = client.post("/api/exam", json={"weights": {CHAIN: 1, POWER: 1}, "count": 4, "pace": "exam", "seed": 5})
    assert r.status_code == 201, r.text
    exam = r.json()["exam"]
    items = exam["items"]
    assert len(items) == 4 and not exam["finished"]
    assert sorted(i["skill"]["id"] for i in items).count(CHAIN) == 2
    assert exam["time_limit_s"] == 60 * sum({1: 2, 2: 3, 3: 5, 4: 7}[i["difficulty"]] for i in items)
    assert all(i["result"] is None for i in items)

    # No feedback loop on an exam: practice answers, hints and retries are refused.
    first = items[0]
    assert client.post(f"/api/practice/items/{first['id']}/answer", json={"answer": "1"}).status_code == 409
    assert client.post(f"/api/practice/items/{first['id']}/hint", json={"level": 1}).status_code == 409

    # Unreadable input is refused while there is time to fix it.
    assert client.put(f"/api/exam/items/{first['id']}/answer", json={"answer": "sin("}).status_code == 422
    assert client.put(f"/api/exam/items/{first['id']}/answer",
                      json={"answer": right(first["problem"]["id"])}).status_code == 200
    second = items[1]
    client.put(f"/api/exam/items/{second['id']}/answer", json={"answer": wrong(second["problem"]["id"])})

    pending = client.get(f"/api/exam/{exam['id']}").json()
    assert pending["stats"]["answered"] == 2 and pending["stats"]["correct"] is None
    assert pending["items"][0]["answer"] and pending["items"][0]["result"] is None

    done = client.post(f"/api/exam/{exam['id']}/finish").json()
    assert done["finished"] and done["time_used_s"] is not None
    assert (done["stats"]["correct"], done["stats"]["incorrect"], done["stats"]["blank"]) == (1, 1, 2)
    results = [i["result"] for i in done["items"]]
    assert results[0]["status"] == "correct" and results[0]["solution"]
    assert results[1]["status"] == "incorrect" and results[1]["attempt"]["mistake"]["tag"]
    assert results[2]["status"] == "blank" and results[2]["answer_latex"]

    # Every topic on the exam is now on the review schedule; misses come back tomorrow.
    with Session(get_engine()) as db:
        cards = {c.skill_id: c for c in db.scalars(select(SkillCard))}
    assert set(cards) == {CHAIN, POWER}
    assert all(c.interval_days == 1 for c in cards.values())

    assert client.put(f"/api/exam/items/{first['id']}/answer", json={"answer": "1"}).status_code == 409
    # Finishing twice is harmless.
    assert client.post(f"/api/exam/{exam['id']}/finish").json()["stats"]["correct"] == 1


def test_exam_hands_itself_in_when_time_runs_out(signed_in):
    client = signed_in
    exam = client.post("/api/exam", json={"weights": {POWER: 1}, "count": 2, "pace": "exam", "seed": 1}).json()["exam"]
    item = exam["items"][0]
    client.put(f"/api/exam/items/{item['id']}/answer", json={"answer": right(item["problem"]["id"])})
    with Session(get_engine()) as db:
        sheet = db.get(Worksheet, exam["id"])
        sheet.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    r = client.put(f"/api/exam/items/{exam['items'][1]['id']}/answer", json={"answer": "1"})
    assert r.status_code == 409 and "Time is up" in r.json()["detail"]
    data = client.get(f"/api/exam/{exam['id']}").json()
    assert data["finished"] and data["stats"]["correct"] == 1 and data["stats"]["blank"] == 1


def test_study_pace_uses_the_practice_loop(signed_in):
    client = signed_in
    r = client.post("/api/exam", json={"weights": {CHAIN: 3, POWER: 1}, "count": 4, "pace": "study", "seed": 2})
    assert r.status_code == 201
    sheet = r.json()["worksheet"]
    assert sheet["mode"] == "exam" and len(sheet["items"]) == 4
    assert [i["skill"]["id"] for i in sheet["items"]].count(CHAIN) == 3
    item = sheet["items"][0]
    assert answer(client, item["id"], wrong(item["problem"]["id"]))["item"]["status"] == "retrying"
    # A study-pace set isn't an exam-pace one.
    assert client.get(f"/api/exam/{sheet['id']}").status_code == 404


def test_exam_validation(signed_in):
    client = signed_in
    assert client.post("/api/exam", json={"weights": {CHAIN: 0}}).status_code == 422
    assert client.post("/api/exam", json={"weights": {"calc1.nope": 1}}).status_code == 422
    assert client.post("/api/exam", json={"weights": {CHAIN: 1}, "pace": "relaxed"}).status_code == 422


def test_weights_come_from_the_syllabus(signed_in):
    uid = user_id()
    with Session(get_engine()) as db:
        source = Source(user_id=uid, title="MATH 30 syllabus", filename="syllabus.pdf", kind="syllabus",
                        mime="application/pdf", size_bytes=100, storage_key="x", status="ready")
        db.add(source)
        db.flush()
        db.add(SourceChunk(source_id=source.id, ordinal=0, heading="Grading", locator="p. 2", skills={},
                           notation={}, top_score=0.0,
                           text="Midterm topics\nChain rule and implicit differentiation: 30%\nPower rule 10%\n"))
        db.commit()
    weights = signed_in.get(f"/api/exam/weights?skills={CHAIN},{IMPLICIT},{POWER},{PRODUCT}").json()["weights"]
    by_id = {w["skill_id"]: w for w in weights}
    # 15, 15 and 10 from the syllabus; the product rule gets their average, 13.3.
    assert by_id[CHAIN]["weight"] == pytest.approx(28.1, abs=0.1)
    assert by_id[POWER]["weight"] == pytest.approx(18.8, abs=0.1)
    assert by_id[PRODUCT]["weight"] == pytest.approx(25.0, abs=0.1)
    assert by_id[CHAIN]["source"]["locator"] == "p. 2" and "30%" in by_id[CHAIN]["source"]["line"]
    assert by_id[PRODUCT]["source"] is None


# --- stage 6: voice and photo input ------------------------------------------------------------


def test_voice_endpoints(signed_in, monkeypatch):
    from slate_api.services import stt

    for key in ("STT_PROVIDER", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    stt.get_transcriber.cache_clear()
    assert signed_in.get("/api/voice").json() == {"available": False, "provider": None}
    r = signed_in.post("/api/voice/transcribe", files={"audio": ("q.webm", b"audio", "audio/webm")})
    assert r.status_code == 503

    monkeypatch.setenv("STT_PROVIDER", "fake")
    stt.get_transcriber.cache_clear()
    assert signed_in.get("/api/voice").json()["available"] is True
    r = signed_in.post("/api/voice/transcribe", files={"audio": ("q.webm", b"audio", "audio/webm;codecs=opus")})
    assert r.status_code == 200 and r.json()["text"] == stt.FAKE_TRANSCRIPT
    r = signed_in.post("/api/voice/transcribe", files={"audio": ("q.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    stt.get_transcriber.cache_clear()


def test_photo_endpoint(signed_in, client, monkeypatch):
    import io as _io

    from PIL import Image as _Image

    from slate_api.services import photo

    class Fake:
        available = True

        def structured(self, **kwargs):
            return photo.PhotoAnswer(found=True, answer="2x*cos(x^2)", confidence=0.8)

    monkeypatch.setattr(photo, "get_llm", lambda: Fake())
    buf = _io.BytesIO()
    _Image.new("RGB", (200, 80), "white").save(buf, format="JPEG")
    image = ("work.jpg", buf.getvalue(), "image/jpeg")
    r = signed_in.post("/api/math/photo", files={"image": image}, data={"variables": "x", "prompt": "Differentiate."})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "2x*cos(x^2)" and "\\cos" in body["latex"] and body["method"] == "claude"
    assert signed_in.post("/api/math/photo", files={"image": image}, data={"variables": "z"}).status_code == 422
    r = signed_in.post("/api/math/photo", files={"image": ("a.txt", b"not an image", "text/plain")})
    assert r.status_code == 422
    signed_in.post("/api/auth/logout")
    assert client.post("/api/math/photo", files={"image": image}).status_code == 401
