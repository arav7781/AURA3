"""Reviews (anonymised for founders) and the weighted Borda ranking board."""

from aura.core.db import write_tx
from aura.models import Startup
from aura.rankings import Ballot, community_scores, ranks
from tests.conftest import register


def test_borda_weights_plans_and_reputation():
    scores = community_scores([
        Ballot("a", "angel", 1.0, ["x", "y"]),
        Ballot("b", "syndicate", 2.0, ["y"]),
        Ballot("c", "scout", 1.0, ["x"]),
    ])
    # weights 1.0, 2.0, 0.5 → max = 3.5 × 10; x = 10 + 5, y = 9 + 20
    assert scores["x"] == {"score": round(10 * 15 / 35, 2), "points": 15.0, "rankers": 2}
    assert scores["y"]["points"] == 29.0 and scores["y"]["score"] > scores["x"]["score"]
    assert ranks({"x": 4.3, "y": 8.3, "z": 4.3}) == {"y": 1, "x": 2, "z": 2}


def published_startups(client, n: int) -> list[str]:
    ids = []
    for i in range(n):
        register(client, role="startup", startup_name=f"Co {i}")
        ids.append(client.get("/api/me").json()["startup"]["id"])
    with write_tx() as s:
        for score, startup_id in enumerate(ids, start=5):
            startup = s.get(Startup, startup_id)
            startup.status, startup.ai_score_x10 = "published", score * 10
    return ids


def test_reviews_are_named_for_investors_and_anonymous_for_the_founder(client):
    founder, _ = register(client, role="startup", startup_name="Reviewed Co")
    startup_id = client.get("/api/me").json()["startup"]["id"]
    with write_tx() as s:
        s.get(Startup, startup_id).status = "published"
    register(client, plan="angel", name="Priya Investor")
    review = {"team": 4, "market": 5, "product": 3, "traction": 4, "note": "Strong distribution."}
    assert client.put(f"/api/startups/{startup_id}/review", json=review).status_code == 200
    assert client.put(f"/api/startups/{startup_id}/review", json=review | {"team": 5}).status_code == 200
    seen = client.get(f"/api/startups/{startup_id}/reviews").json()
    assert seen["summary"]["count"] == 1 and seen["summary"]["team"] == 5
    assert seen["items"][0]["reviewer"] == {"name": "Priya Investor", "plan": "angel"} and seen["mine"]
    assert client.put(f"/api/startups/{startup_id}/review", json=review | {"team": 6}).status_code == 422

    client.post("/api/auth/login", json={"email": founder["email"], "password": founder["password"]})
    own = client.get(f"/api/startups/{startup_id}/reviews").json()
    assert own["items"][0]["reviewer"] == {"name": "Investor A"} and own["items"][0]["note"] == "Strong distribution."
    assert client.put(f"/api/startups/{startup_id}/review", json=review).json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_ranking_board_and_rank_gap(client):
    a, b, c = published_startups(client, 3)  # AI scores 5.0, 6.0, 7.0
    register(client, plan="syndicate")
    assert client.put("/api/me/ranking", json={"startup_ids": [a, b]}).status_code == 200
    assert client.put("/api/me/ranking", json={"startup_ids": [a, a]}).json()["error"]["code"] == "DUPLICATE_STARTUP"
    assert client.put("/api/me/ranking", json={"startup_ids": ["nope"]}).status_code == 404
    board = client.get("/api/rankings").json()
    assert [row["id"] for row in board["mine"]] == [a, b]
    top = board["board"][0]
    assert top["id"] == a and top["community_rank"] == 1 and top["ai_rank"] == 3 and top["rank_gap"] == 2
    assert c not in [row["id"] for row in board["board"]] and board["ballots"] == 1
