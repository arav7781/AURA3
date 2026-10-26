import json

from sqlalchemy import update

from aura.core.db import write_tx
from aura.models import User
from tests.conftest import register


def make_admin(client) -> dict:
    body, user = register(client, name="Admin")
    with write_tx() as s:
        s.execute(update(User).where(User.id == user["id"]).values(is_admin=True))
    return user


def read_events(response) -> list[dict]:
    events, current = [], {}
    for line in response.iter_lines():
        if line.startswith("event: "):
            current["event"] = line.removeprefix("event: ")
        elif line.startswith("id: "):
            current["id"] = int(line.removeprefix("id: "))
        elif line.startswith("data: "):
            current["data"] = json.loads(line.removeprefix("data: "))
        elif line == "" and current:
            events.append(current)
            current = {}
    return events


def test_job_progress_streams_in_order_with_sse_headers(client):
    make_admin(client)
    job_id = client.post("/api/admin/jobs/echo", json={"steps": 3, "delay_ms": 20}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "no-transform" in response.headers["cache-control"]
        assert response.headers["x-accel-buffering"] == "no"
        events = read_events(response)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "job_queued" and kinds[-1] == "job_done"
    assert [e["data"]["data"]["stage"] for e in events if e["event"] == "job_progress"] == ["step 1", "step 2", "step 3"]
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    assert all(e["data"]["job_id"] == job_id for e in events)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done" and job["progress"] == 100 and job["result"] == {"steps": 3}


def test_reconnect_with_last_event_id_replays_only_the_tail(client):
    make_admin(client)
    job_id = client.post("/api/admin/jobs/echo", json={"steps": 4, "delay_ms": 10}).json()["job_id"]
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        full = read_events(response)
    cut = full[2]["id"]
    with client.stream("GET", f"/api/jobs/{job_id}/events", headers={"Last-Event-ID": str(cut)}) as response:
        tail = read_events(response)
    assert [e["id"] for e in tail] == [e["id"] for e in full if e["id"] > cut]


def test_other_users_cannot_see_a_job(client):
    make_admin(client)
    job_id = client.post("/api/admin/jobs/echo", json={"steps": 1, "delay_ms": 0}).json()["job_id"]
    client.cookies.clear()
    register(client)
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/events").status_code == 404


def test_admin_tools_require_an_admin(client):
    register(client)
    assert client.post("/api/admin/jobs/echo", json={}).status_code == 403
    assert client.get("/api/admin/audit").status_code == 403
