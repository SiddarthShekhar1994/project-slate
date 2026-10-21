def test_signup_login_logout(client):
    r = client.post("/api/auth/signup", json={"email": "Ada@Example.com", "password": "correct horse"})
    assert r.status_code == 201
    assert r.json()["email"] == "ada@example.com"
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong password"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "ADA@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["display_name"] == "ada"


def test_signup_validation(client):
    assert client.post("/api/auth/signup", json={"email": "nope", "password": "longenough"}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422
    client.post("/api/auth/signup", json={"email": "a@b.co", "password": "longenough"})
    r = client.post("/api/auth/signup", json={"email": "a@b.co", "password": "longenough"})
    assert r.status_code == 422 and "already exists" in r.json()["detail"]


def test_session_cookie_is_http_only(client):
    r = client.post("/api/auth/signup", json={"email": "c@d.co", "password": "longenough"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_practice_requires_sign_in(client):
    assert client.get("/api/practice/worksheets").status_code == 401


def test_session_endpoint_is_quiet_when_signed_out(client):
    assert client.get("/api/auth/session").json() == {"user": None, "desktop": False}
    client.post("/api/auth/signup", json={"email": "e@f.co", "password": "longenough"})
    assert client.get("/api/auth/session").json()["user"]["email"] == "e@f.co"
