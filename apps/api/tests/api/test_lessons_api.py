import copy
import json

from sqlalchemy.orm import Session

from slate_api.db import get_engine
from slate_api.services.lessons import BUILTIN_DIR, sync_builtin_lessons

CHAIN = "calc1.derivatives.chain_rule"


def chain_lesson(client):
    lessons = client.get("/api/lessons").json()["lessons"]
    return next(l for l in lessons if l["skill"]["id"] == CHAIN)


def test_builtin_chain_rule_lesson_is_listed_and_viewable(signed_in):
    summary = chain_lesson(signed_in)
    assert summary["kind"] == "builtin" and summary["steps"] >= 8 and summary["resume_step"] == 0
    view = signed_in.get(f"/api/lessons/{summary['id']}").json()
    assert view["script"]["skillId"] == CHAIN
    assert [s["status"] for s in view["outline"]["skills"]] == ["new"] * 5
    assert view["outline"]["unit"] == "Derivatives"
    assert view["tts"]["available"] is False  # no provider configured in tests


def test_progress_and_resume(signed_in):
    lesson = chain_lesson(signed_in)
    assert signed_in.post(f"/api/lessons/{lesson['id']}/progress", json={"step": 4}).status_code == 204
    assert chain_lesson(signed_in)["resume_step"] == 4
    assert signed_in.post(f"/api/lessons/{lesson['id']}/progress", json={"step": 99}).status_code == 422


def test_checkpoint_answers_feed_mastery(signed_in):
    lesson = chain_lesson(signed_in)
    view = signed_in.get(f"/api/lessons/{lesson['id']}").json()
    step = next(i for i, s in enumerate(view["script"]["steps"]) if s.get("checkpoint"))
    right = next(o["id"] for o in view["script"]["steps"][step]["checkpoint"]["options"] if o["correct"])
    r = signed_in.post(f"/api/lessons/{lesson['id']}/checkpoint", json={"step": step, "option": right})
    assert r.json() == {"correct": True}
    outline = signed_in.get(f"/api/lessons/{lesson['id']}").json()["outline"]["skills"]
    chain = next(s for s in outline if s["id"] == CHAIN)
    assert chain["mastery"] == 1.0 and chain["status"] == "practiced"
    assert signed_in.post(f"/api/lessons/{lesson['id']}/checkpoint", json={"step": 0, "option": "a"}).status_code == 422


def test_ask_without_an_api_key_returns_the_step(signed_in):
    lesson = chain_lesson(signed_in)
    r = signed_in.post(f"/api/lessons/{lesson['id']}/ask", json={"step": 2, "question": "Why call it u?"}).json()
    assert r["verified"] is True
    assert "$" in r["answer"]
    assert r["notes"]


def test_audio_reports_unavailable_without_a_provider(signed_in):
    lesson = chain_lesson(signed_in)
    r = signed_in.get(f"/api/lessons/{lesson['id']}/steps/0/audio", params={"voice": "nova"}).json()
    assert r["status"] == "unavailable"


def test_unverified_builtin_is_not_loaded(tmp_path):
    script = json.loads((BUILTIN_DIR / "calc1.derivatives.chain_rule.json").read_text())
    bad = copy.deepcopy(script)
    bad["id"] = "broken-lesson"
    bad["steps"][4]["claims"] = [{"kind": "derivative", "of": "sin(u)", "var": "u", "equals": "-cos(u)"}]
    (tmp_path / "broken.json").write_text(json.dumps(bad))
    with Session(get_engine()) as db:
        assert sync_builtin_lessons(db, tmp_path) == []


def test_media_is_limited_to_audio_and_own_uploads(signed_in):
    assert signed_in.get("/api/media/uploads/someone-else/file.pdf").status_code == 404
    assert signed_in.get("/api/media/../etc/passwd").status_code == 404
    assert signed_in.get("/api/media/tts/missing.mp3").status_code == 404


def test_lessons_need_sign_in(client):
    assert client.get("/api/lessons").status_code == 401
