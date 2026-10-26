from datetime import timedelta

from aura.core import clock
from aura.core.db import read_session
from aura.ledger.audit import run_audit
from tests.conftest import idem, register

AC = 100


def _available(client) -> int:
    return client.get("/api/me").json()["balances"]["available"]


def _activate(client, plan: str, headers=None):
    return client.post("/api/me/plan", json={"plan": plan}, headers=headers or idem())


def test_activating_angel_grants_monthly_coins(client):
    register(client)
    result = _activate(client, "angel").json()
    assert result["plan"] == "angel" and result["granted_minor"] == 5000 * AC
    assert _available(client) == (500 + 5000) * AC
    me = client.get("/api/me").json()
    assert {"vote", "pledge", "deck_access"} <= set(me["entitlements"]["features"])


def test_upgrade_tops_up_only_the_difference(client):
    register(client)
    _activate(client, "angel")
    result = _activate(client, "syndicate").json()
    assert result["granted_minor"] == 20000 * AC
    assert _available(client) == (500 + 25000) * AC


def test_plan_toggling_never_mints_more_than_the_top_plan(client):
    register(client)
    for plan in ("angel", "syndicate", "angel", "syndicate", "angel", "syndicate"):
        assert _activate(client, plan).status_code == 200
    assert _available(client) == (500 + 25000) * AC
    with read_session() as s:
        assert {k: v for k, v in run_audit(s).items() if v} == {}


def _sign_in_again(client, body) -> None:
    # Sessions last 7 days on the application clock, so moving the clock a month ahead signs users out.
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": body["email"], "password": body["password"]}).status_code == 200


def test_downgrade_waits_for_period_end_then_renews_on_the_lower_plan(client):
    clock.freeze(clock.now())
    body, _ = register(client)
    _activate(client, "syndicate")
    result = _activate(client, "angel").json()
    assert result["effective"] == "period_end" and result["pending_plan"] == "angel"
    assert client.get("/api/me").json()["plan"]["id"] == "syndicate"
    clock.advance(timedelta(days=30, seconds=1))
    _sign_in_again(client, body)
    me = client.get("/api/me").json()
    assert me["plan"]["id"] == "angel" and me["plan"]["period_index"] == 2
    assert me["balances"]["available"] == (500 + 25000 + 5000) * AC


def test_scout_downgrade_stops_grants(client):
    clock.freeze(clock.now())
    body, _ = register(client)
    _activate(client, "angel")
    _activate(client, "scout")
    clock.advance(timedelta(days=61))
    _sign_in_again(client, body)
    me = client.get("/api/me").json()
    assert me["plan"]["id"] == "scout" and me["plan"]["next_grant_at"] is None
    assert me["balances"]["available"] == (500 + 5000) * AC


def test_idempotency_key_replays_the_same_response(client):
    register(client)
    headers = idem()
    first = _activate(client, "angel", headers)
    second = _activate(client, "angel", headers)
    assert first.json() == second.json()
    assert _available(client) == (500 + 5000) * AC
    conflict = client.post("/api/me/plan", json={"plan": "syndicate"}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotency_key_is_required(client):
    register(client)
    assert client.post("/api/me/plan", json={"plan": "angel"}).status_code == 422


def test_ledger_history_lists_grants(client):
    register(client)
    _activate(client, "angel")
    items = client.get("/api/me/ledger").json()["items"]
    assert [i["kind"] for i in items] == ["plan_grant", "welcome_grant"]
    assert all(i["account"] == "wallet" for i in items)
