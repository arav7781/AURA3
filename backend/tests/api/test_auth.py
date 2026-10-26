from tests.conftest import register


def test_register_investor_sets_secure_cookie_and_welcome_credit(client):
    body, user = register(client, role="investor")
    assert user["role"] == "investor"
    me = client.get("/api/me").json()
    assert me["plan"]["id"] == "scout"
    assert me["balances"]["available"] == 500 * 100
    assert "vote" not in me["entitlements"]["features"]
    assert me["entitlements"]["quotas"]["copilot"]["limit"] == 30


def test_session_cookie_flags(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "flags@example.com", "password": "correct-horse-battery", "name": "F", "role": "investor"},
    )
    cookie = response.headers["set-cookie"].lower()
    assert "aura_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie


def test_register_startup_creates_draft_startup(client):
    register(client, role="startup", startup_name="KrishiMitra AI")
    me = client.get("/api/me").json()
    assert me["user"]["role"] == "startup"
    assert me["startup"]["name"] == "KrishiMitra AI" and me["startup"]["status"] == "draft"
    assert me["startup"]["slug"] == "krishimitra-ai"
    assert me["plan"] is None


def test_duplicate_email_is_rejected(client):
    body, _ = register(client)
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_writes_need_the_csrf_header_and_an_allowed_origin(client):
    body = {"email": "c@example.com", "password": "correct-horse-battery", "name": "C", "role": "investor"}
    no_header = client.post("/api/auth/register", json=body, headers={"X-Aura-CSRF": ""})
    assert no_header.status_code == 403 and no_header.json()["error"]["code"] == "CSRF_FAILED"
    bad_origin = client.post("/api/auth/register", json=body, headers={"Origin": "https://evil.example"})
    assert bad_origin.status_code == 403
    good_origin = client.post("/api/auth/register", json=body, headers={"Origin": "http://localhost:3000"})
    assert good_origin.status_code == 201


def test_login_logout_and_revocation(client):
    body, _ = register(client)
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401
    wrong = client.post("/api/auth/login", json={"email": body["email"], "password": "nope-nope-nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    ok = client.post("/api/auth/login", json={"email": body["email"].upper(), "password": body["password"]})
    assert ok.status_code == 200
    token = client.cookies.get("aura_session")
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    # The old token no longer works even if a client kept it: the session row is revoked.
    client.cookies.set("aura_session", token)
    assert client.get("/api/me").status_code == 401


def test_role_guard(client):
    register(client, role="startup")
    response = client.post("/api/me/plan", json={"plan": "angel"}, headers={"Idempotency-Key": "abcdefgh1"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_public_plans_catalogue(client):
    plans = client.get("/api/plans").json()
    assert [p["id"] for p in plans["plans"]] == ["scout", "angel", "syndicate"]
    assert [p["price_inr_month"] for p in plans["plans"]] == [0, 4999, 24999]
    assert plans["startup"]["success_fee_bps"] == 200
    assert plans["auracoin"]["redeemable"] is False


def test_logout_clears_a_stale_cookie(client):
    client.cookies.set("aura_session", "not-a-valid-token")
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert 'aura_session=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]
