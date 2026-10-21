import re

import sympy as sp

from sqlalchemy.orm import Session

from slate_api.db import get_engine
from slate_api.models import Problem
from slate_api.services.practice import load_problem

CHAIN = "calc1.derivatives.chain_rule"


def typed(expr):
    return re.sub(r"\bE\b", "e", sp.sstr(expr).replace("**", "^"))


def key_for(problem_id):
    with Session(get_engine()) as db:
        return load_problem(db.get(Problem, problem_id)).built


def test_catalog(client):
    data = client.get("/api/catalog").json()
    skills = [s["id"] for c in data["courses"] for u in c["units"] for s in u["skills"]]
    assert CHAIN in skills
    assert data["difficulties"]["1"] == "Easy"


def test_preview(client):
    r = client.post("/api/math/preview", json={"text": "3x²cos(x³+1)", "variables": ["x"]}).json()
    assert r["ok"] and "\\cos" in r["latex"]
    r = client.post("/api/math/preview", json={"text": "3z", "variables": ["x"]}).json()
    assert not r["ok"] and r["error"]


def test_worksheet_flow(signed_in):
    client = signed_in
    r = client.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 4, "seed": 11})
    assert r.status_code == 201, r.text
    sheet = r.json()
    assert [i["difficulty"] for i in sheet["items"]] == sorted(i["difficulty"] for i in sheet["items"])
    assert all(i["status"] == "up_next" for i in sheet["items"])
    # Keys and worked steps stay on the server until a problem is cleared.
    assert all(i["problem"]["answer_latex"] is None and i["problem"]["solution"] is None for i in sheet["items"])
    first = sheet["items"][0]

    # Unreadable input is not a miss.
    r = client.post(f"/api/practice/items/{first['id']}/answer", json={"answer": "sin("}).json()
    assert r["grade"]["status"] == "invalid" and r["item"]["misses"] == 0

    # Hints open in order.
    assert client.post(f"/api/practice/items/{first['id']}/hint", json={"level": 2}).status_code == 422
    r = client.post(f"/api/practice/items/{first['id']}/hint", json={"level": 1}).json()
    assert len(r["item"]["problem"]["hints"]) == 1

    # A wrong answer is tagged and locks the item until a similar problem is served.
    built = key_for(first["problem"]["id"])
    r = client.post(f"/api/practice/items/{first['id']}/answer",
                    json={"answer": typed(built.parts["outer_prime_at_inside"]), "duration_ms": 4200}).json()
    assert r["grade"]["status"] == "incorrect"
    assert r["grade"]["mistake"]["tag"] == "dropped_inner_derivative"
    assert r["grade"]["latex"]
    assert r["item"]["status"] == "retrying" and r["item"]["misses"] == 1 and r["item"]["needs_new_problem"]
    again = client.post(f"/api/practice/items/{first['id']}/answer", json={"answer": "1"})
    assert again.status_code == 409

    r = client.post(f"/api/practice/items/{first['id']}/similar").json()
    item = r["item"]
    assert item["problem"]["id"] != first["problem"]["id"]
    assert item["difficulty"] == first["difficulty"] and item["skill"]["id"] == CHAIN
    assert item["hint_level"] == 0 and not item["needs_new_problem"]

    # Right on the retry: cleared after retry, solution revealed.
    built = key_for(item["problem"]["id"])
    r = client.post(f"/api/practice/items/{first['id']}/answer", json={"answer": typed(built.key)}).json()
    assert r["grade"]["status"] == "correct"
    assert r["item"]["status"] == "cleared_after_retry"
    assert r["item"]["problem"]["solution"]
    assert r["stats"]["after_retry"] == 1 and r["stats"]["misses"] == 1

    # Clear the rest first try and the worksheet completes.
    for it in client.get(f"/api/practice/worksheets/{sheet['id']}").json()["items"][1:]:
        built = key_for(it["problem"]["id"])
        r = client.post(f"/api/practice/items/{it['id']}/answer", json={"answer": typed(built.key)}).json()
        assert r["grade"]["status"] == "correct", (built.prompt, typed(built.key), r)
    final = client.get(f"/api/practice/worksheets/{sheet['id']}").json()
    assert final["completed_at"]
    assert final["stats"] == {"total": 4, "first_try": 3, "after_retry": 1, "retrying": 0, "up_next": 0,
                              "misses": 1, "completed": True}

    listing = client.get("/api/practice/worksheets").json()["worksheets"]
    assert listing[0]["id"] == sheet["id"]


def test_worksheets_are_private(client):
    client.post("/api/auth/signup", json={"email": "one@x.co", "password": "longenough"})
    sheet = client.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 2}).json()
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"email": "two@x.co", "password": "longenough"})
    assert client.get(f"/api/practice/worksheets/{sheet['id']}").status_code == 404
    item = sheet["items"][0]["id"]
    assert client.post(f"/api/practice/items/{item}/answer", json={"answer": "1"}).status_code == 404


def test_unknown_skill(signed_in):
    r = signed_in.post("/api/practice/worksheets", json={"skill_ids": ["calc1.derivatives.nope"]})
    assert r.status_code == 422


def test_database_rejects_unverified_problems(signed_in):
    import pytest
    from sqlalchemy.exc import IntegrityError

    sheet = signed_in.post("/api/practice/worksheets", json={"skill_ids": [CHAIN], "count": 1}).json()
    with Session(get_engine()) as db:
        row = db.get(Problem, sheet["items"][0]["problem"]["id"])
        row.verification = {**row.verification, "ok": False}
        with pytest.raises(IntegrityError):
            db.commit()
