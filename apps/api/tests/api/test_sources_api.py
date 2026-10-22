import io

import pymupdf
import pytest

from slate_api.services import sources as sources_service

CHAIN = "calc1.derivatives.chain_rule"


def chain_rule_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Lecture 7: The chain rule", fontsize=20)
    body = [
        "The chain rule differentiates a composite function, a function of a function.",
        "If y = f(u) and u = g(x), then dy/dx = dy/du * du/dx.",
        "Example: d/dx sin(x^3 + 1) = cos(x^3 + 1) * 3x^2. The inner function is x^3 + 1.",
        "Differentiate the outer function, keep the inner function, multiply by the inner derivative.",
    ]
    for i, line in enumerate(body):
        page.insert_text((72, 120 + 22 * i), line, fontsize=11)
    page = doc.new_page()
    page.insert_text((72, 72), "Product rule", fontsize=20)
    page.insert_text((72, 120), "The product rule: (fg)' = f'g + fg'. Differentiate a product of two functions.", fontsize=11)
    return doc.tobytes()


def upload(client, data: bytes, name="lecture7_chain_rule.pdf", kind=None):
    files = {"file": (name, io.BytesIO(data), "application/octet-stream")}
    return client.post("/api/sources", files=files, data={"kind": kind} if kind else {})


def test_upload_is_processed_and_matched_to_skills(signed_in):
    r = upload(signed_in, chain_rule_pdf())
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "processing"
    assert r.json()["kind"] == "slides"
    source = signed_in.get(f"/api/sources/{r.json()['id']}").json()
    assert source["status"] == "ready", source
    assert source["chunks"] >= 1 and source["pages"] == 2
    assert source["skills"][0]["id"] in {CHAIN, "calc1.derivatives.product_rule"}
    assert any(s["id"] == CHAIN for s in source["skills"])
    assert all(c["locator"] for c in source["chunk_list"])
    assert signed_in.get(source["file_url"]).status_code == 200


def test_unsupported_and_empty_files_are_refused(signed_in):
    assert upload(signed_in, b"just some text", name="notes.txt").status_code == 415
    assert upload(signed_in, b"", name="empty.pdf").status_code == 422


def test_size_limit(signed_in, monkeypatch):
    monkeypatch.setattr(sources_service, "MAX_UPLOAD_BYTES", 1000)
    assert upload(signed_in, chain_rule_pdf()).status_code == 413


def test_corrupt_file_fails_with_a_message(signed_in):
    r = upload(signed_in, b"%PDF-1.7\nthis is not really a pdf", name="broken.pdf")
    assert r.status_code == 202
    source = signed_in.get(f"/api/sources/{r.json()['id']}").json()
    assert source["status"] == "failed" and source["error"]


def test_sources_are_private_and_deletable(client):
    client.post("/api/auth/signup", json={"email": "own@x.co", "password": "longenough"})
    source = upload(client, chain_rule_pdf()).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "other@x.co", "password": "longenough"})
    assert client.get(f"/api/sources/{source['id']}").status_code == 404
    assert client.delete(f"/api/sources/{source['id']}").status_code == 404
    assert client.get(source["file_url"]).status_code == 404
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "own@x.co", "password": "longenough"})
    assert client.delete(f"/api/sources/{source['id']}").status_code == 204
    assert client.get("/api/sources").json()["sources"] == []


def test_practice_problems_cite_the_best_source(signed_in):
    source = upload(signed_in, chain_rule_pdf()).json()
    sheet = signed_in.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 2}).json()
    cited = sheet["items"][0]["problem"]["source"]
    assert cited["source_id"] == source["id"] and cited["locator"]
    used = signed_in.get(f"/api/sources/{source['id']}").json()["used_for"]
    assert used["problems"] >= 2


def test_generated_lesson_is_cited_and_verified(signed_in):
    source = upload(signed_in, chain_rule_pdf()).json()
    r = signed_in.post("/api/lessons/generate", json={"skill_id": CHAIN})
    assert r.status_code == 201, r.text
    summary = r.json()
    assert summary["kind"] == "generated" and summary["sources"] >= 1
    view = signed_in.get(f"/api/lessons/{summary['id']}").json()
    assert view["sources"] and view["sources"][0]["locator"]
    used = signed_in.get(f"/api/sources/{source['id']}").json()["used_for"]
    assert [l["id"] for l in used["lessons"]] == [summary["id"]]


def test_a_built_in_skill_gets_a_lesson_without_sources(signed_in):
    # No Claude key and no uploads: the composer writes it from a verified template problem.
    r = signed_in.post("/api/lessons/generate", json={"skill_id": CHAIN})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "generated" and r.json()["sources"] == 0


@pytest.mark.parametrize("name, mime, expected", [
    ("Math30_Syllabus.pdf", "application/pdf", "syllabus"),
    ("midterm2_2024.pdf", "application/pdf", "exam"),
    ("Stewart_chapter3.pdf", "application/pdf", "textbook"),
    ("IMG_2041.jpg", "image/jpeg", "notes"),
    ("week5.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "slides"),
    ("latest_handout.pdf", "application/pdf", "other"),
    ("worked_example.pdf", "application/pdf", "other"),
])
def test_kind_guess(name, mime, expected):
    assert sources_service.guess_kind(name, mime) == expected
