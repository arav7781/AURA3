"""The copilot with a scripted chat model: tools, cards, streamed events, citation checks, plan limits."""

import asyncio
import json
import time
import uuid
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk
from sqlalchemy import update

from aura.core.db import write_tx
from aura.models import Chunk, Document, Startup, UsageCounter
from tests.api.test_jobs import read_events
from tests.conftest import register


class FakeChat:
    """Plays back one scripted reply per model call; records what it was sent."""

    def __init__(self, script: list[list[AIMessageChunk]], delay: float = 0.0) -> None:
        self.script, self.delay, self.calls = list(script), delay, []

    def bind_tools(self, specs):
        self.tools = [s["function"]["name"] for s in specs]
        return self

    async def astream(self, messages):
        self.calls.append(messages)
        if self.delay:
            await asyncio.sleep(self.delay)
        for chunk in self.script.pop(0) if self.script else [AIMessageChunk(content="Done.")]:
            yield chunk


def call(name: str, args: dict, call_id: str = "call_1") -> AIMessageChunk:
    return AIMessageChunk(content="", tool_call_chunks=[{"name": name, "args": json.dumps(args), "id": call_id, "index": 0}])


def text(*pieces: str) -> list[AIMessageChunk]:
    return [AIMessageChunk(content=p) for p in pieces]


def published_startup(client, name: str = "Test Agritech") -> str:
    register(client, role="startup", startup_name=name)
    startup_id = client.get("/api/me").json()["startup"]["id"]
    with write_tx() as s:
        st = s.get(Startup, startup_id)
        st.status, st.domain, st.one_liner = "published", "Agritech", "Soil sensors for smallholders"
        doc = Document(startup_id=startup_id, filename="Deck.pdf", mime="application/pdf", size_bytes=10, sha256="0" * 64,
                       storage_dir="x", status="ready", visibility="published", page_count=11)
        s.add(doc)
        s.flush()
        s.add(Chunk(id=str(uuid.uuid4()), cid="c:abcdefg", document_id=doc.id, startup_id=startup_id, seq=0, page_no=4,
                    slide_title="Market", text="TAM: USD 82.3M in 2025", bbox=[0.1, 0.1, 0.9, 0.3], origin="digital",
                    conf_min=1.0, conf_mean=1.0, n_tokens=8))
    return startup_id


def ask(client, thread_id: str, question: str) -> dict:
    response = client.post(f"/api/copilot/threads/{thread_id}/messages", json={"content": question})
    assert response.status_code == 202, response.text
    return response.json()


def wait(client, run_id: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{run_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_answers_with_tools_cards_and_checked_citations(client):
    published_startup(client)
    register(client, plan="angel")
    thread = client.post("/api/copilot/threads", json={}).json()
    fake = FakeChat([
        [AIMessageChunk(content="", tool_call_chunks=[
            {"name": "list_documents", "args": '{"startup": "Test Agritech"}', "id": "c1", "index": 0},
            {"name": "read_page", "args": '{"startup": "test agritech", "page": 4}', "id": "c2", "index": 1},
        ])],
        text("It submitted one deck. The TAM is USD 82.3M ", "[c:abcdefg] — not [c:zzzzzzz]."),
    ])
    with patch("aura.agent.graph.chat_model", return_value=fake):
        run = ask(client, thread["id"], "What documents has Test Agritech submitted and what is its TAM?")
        with client.stream("GET", f"/api/jobs/{run['run_id']}/events") as response:
            events = read_events(response)
    kinds = [e["event"] for e in events]
    assert kinds[:4] == ["job_queued", "job_started", "run_start", "tool_start"]
    assert kinds.count("tool_start") == 2 and kinds.count("tool_end") == 2 and "token" in kinds
    assert kinds[-2:] == ["message", "job_done"]
    assert set(fake.tools) >= {"search_startups", "list_documents", "search_documents", "web_search"}

    detail = client.get(f"/api/copilot/threads/{thread['id']}").json()
    assert detail["thread"]["title"].startswith("What documents has Test Agritech")
    user, answer = detail["messages"]
    assert user["role"] == "user" and answer["status"] == "done"
    assert "[c:abcdefg]" in answer["content"] and "zzzzzzz" not in answer["content"]
    assert answer["citations"]["c:abcdefg"]["page_no"] == 4 and answer["citations"]["c:abcdefg"]["startup_slug"]
    cards = {p["name"]: p["card"] for p in answer["parts"] if p["type"] == "tool"}
    assert cards["list_documents"]["items"][0]["filename"] == "Deck.pdf" and cards["list_documents"]["can_open"]
    assert cards["list_documents"]["items"][0]["download_url"].endswith("/file")
    assert cards["read_page"]["items"][0]["cid"] == "c:abcdefg"

    # the next turn sees the earlier one, and its cited passage stays citable
    fake2 = FakeChat([text("As before, the TAM is USD 82.3M [c:abcdefg].")])
    with patch("aura.agent.graph.chat_model", return_value=fake2):
        wait(client, ask(client, thread["id"], "Remind me of the TAM")["run_id"])
    sent = fake2.calls[0]
    assert any("What documents has Test Agritech" in str(m.content) for m in sent)
    last = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    assert "[c:abcdefg]" in last["content"]


def test_scouts_cannot_read_inside_documents(client):
    published_startup(client)
    register(client, plan="scout")
    thread = client.post("/api/copilot/threads", json={}).json()
    fake = FakeChat([[call("search_documents", {"query": "TAM", "startup": "Test Agritech"})],
                     text("Your plan does not include reading decks.")])
    with patch("aura.agent.graph.chat_model", return_value=fake):
        wait(client, ask(client, thread["id"], "What is the TAM in the deck?")["run_id"])
    answer = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    tool = next(p for p in answer["parts"] if p["type"] == "tool")
    assert tool["status"] == "error" and tool["card"]["code"] == "PLAN_REQUIRED"
    tool_reply = fake.calls[1][-1]
    assert "PLAN_REQUIRED" in tool_reply.content and "82.3" not in tool_reply.content


def test_quota_privacy_and_one_run_at_a_time(client):
    published_startup(client)
    owner, user = register(client, plan="scout")
    thread = client.post("/api/copilot/threads", json={"startup": "test-agritech"}).json()
    assert thread["startup_id"]
    with patch("aura.agent.graph.chat_model", return_value=FakeChat([text("Thinking…")], delay=1.0)):
        run = ask(client, thread["id"], "first")
        busy = client.post(f"/api/copilot/threads/{thread['id']}/messages", json={"content": "second"})
        assert busy.status_code == 409 and busy.json()["error"]["code"] == "RUN_ACTIVE"
        assert client.post(f"/api/copilot/runs/{run['run_id']}/cancel").json() == {"cancelled": True}
        assert wait(client, run["run_id"])["status"] == "cancelled"
    stopped = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    assert stopped["status"] == "cancelled"

    with write_tx() as s:
        s.execute(update(UsageCounter).where(UsageCounter.user_id == user["id"], UsageCounter.feature == "copilot")
                  .values(count=30))
    over = client.post(f"/api/copilot/threads/{thread['id']}/messages", json={"content": "third"})
    assert over.status_code == 429 and over.json()["error"]["code"] == "QUOTA_EXCEEDED"

    register(client, plan="angel")
    assert client.get(f"/api/copilot/threads/{thread['id']}").status_code == 404
    assert client.get("/api/copilot/threads").json()["items"] == []
