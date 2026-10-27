"""The copilot with a scripted chat model: tools, cards, streamed events, citation checks, plan limits."""

import asyncio
import json
import time
import uuid
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk
from sqlalchemy import select, update

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


async def fake_ingest(ctx, document_id: str, **_):
    """Stands in for TitanOCR: the attached draft has two pages, page 2 states a new TAM."""
    with write_tx() as s:
        doc = s.get(Document, document_id)
        doc.status, doc.page_count = "ready", 2
        s.add(Chunk(id=str(uuid.uuid4()), cid="c:draftzz", document_id=doc.id, startup_id=doc.startup_id, seq=0, page_no=2,
                    slide_title="Market", text="New TAM: USD 90M in 2026", bbox=[0.1, 0.1, 0.9, 0.3], origin="digital",
                    conf_min=1.0, conf_mean=1.0, n_tokens=8, visibility="private"))
    return {"document_id": document_id}


def attach(client, thread_id: str, data: bytes = b"%PDF-1.7\n% draft deck\n", name: str = "Deck v2.pdf"):
    with patch("aura.api.routes.documents.ingest_document", fake_ingest):
        response = client.post(f"/api/copilot/threads/{thread_id}/attachments",
                               files={"file": (name, data, "application/pdf")})
        assert response.status_code == 202, response.text
        out = response.json()
        if out["job_id"]:
            wait(client, out["job_id"])
    return out


def test_founders_attach_a_draft_deck_that_only_the_copilot_reads(client):
    startup_id = published_startup(client)
    thread = client.post("/api/copilot/threads", json={}).json()
    out = attach(client, thread["id"])
    doc_id = out["document_id"]
    assert out["document"]["thread_id"] == thread["id"] and out["document"]["visibility"] == "private"

    # a draft, not part of the startup's documents
    listed = client.get(f"/api/startups/{startup_id}/documents").json()["items"]
    assert [d["filename"] for d in listed] == ["Deck.pdf"]

    fake = FakeChat([[call("read_attachment", {})], text("Slide 2 now says USD 90M [c:draftzz]; cite the source.")])
    with patch("aura.agent.graph.chat_model", return_value=fake):
        response = client.post(f"/api/copilot/threads/{thread['id']}/messages",
                               json={"content": "Review my new deck", "attachments": [doc_id]})
        assert response.status_code == 202, response.text
        assert response.json()["message"]["parts"][0] == {
            "type": "attachment", "document_id": doc_id, "filename": "Deck v2.pdf", "pages": 2,
            "size_bytes": len(b"%PDF-1.7\n% draft deck\n"), "mime": "application/pdf"}
        wait(client, response.json()["run_id"])
    assert "read_attachment" in fake.tools
    system, question = fake.calls[0][0].content, fake.calls[0][-1].content
    assert "Deck v2.pdf (2 pages)" in system and "[Attached: Deck v2.pdf (2 pages)" in question
    assert "New TAM: USD 90M" in fake.calls[1][-1].content
    answer = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    assert answer["citations"]["c:draftzz"]["attachment"] is True

    # the same file again is the same document, not a duplicate error
    assert attach(client, thread["id"])["reused"] is True

    # investors never see it
    register(client, plan="syndicate")
    assert client.get(f"/api/documents/{doc_id}").status_code == 404
    assert all(d["id"] != doc_id for d in client.get(f"/api/startups/{startup_id}/documents").json()["items"])


def test_attachment_rules(client):
    published_startup(client)
    thread = client.post("/api/copilot/threads", json={}).json()
    with write_tx() as s:
        startup_id = s.scalar(select(Startup.id).where(Startup.name == "Test Agritech"))
        busy = Document(startup_id=startup_id, filename="Busy.pdf", mime="application/pdf", size_bytes=10, sha256="1" * 64,
                        storage_dir="x", status="processing", visibility="private", thread_id=thread["id"])
        s.add(busy)
        s.flush()
        busy_id = busy.id
    response = client.post(f"/api/copilot/threads/{thread['id']}/messages", json={"content": "Read it", "attachments": [busy_id]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "ATTACHMENT_NOT_READY"
    response = client.post(f"/api/copilot/threads/{thread['id']}/attachments", files={"file": ("x.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert response.status_code == 415

    # another conversation's draft cannot be borrowed
    other = client.post("/api/copilot/threads", json={}).json()
    draft = attach(client, thread["id"], data=b"%PDF-1.7\n% another\n")["document_id"]
    response = client.post(f"/api/copilot/threads/{other['id']}/messages", json={"content": "x", "attachments": [draft]})
    assert response.status_code == 404

    # deleting the conversation removes its drafts
    assert client.delete(f"/api/copilot/threads/{thread['id']}").status_code == 204
    with write_tx() as s:
        assert s.get(Document, draft) is None and s.get(Document, busy_id) is None

    register(client, plan="angel")
    mine = client.post("/api/copilot/threads", json={}).json()
    response = client.post(f"/api/copilot/threads/{mine['id']}/attachments", files={"file": ("d.pdf", b"%PDF-1.7\n", "application/pdf")})
    assert response.status_code == 403


def test_search_and_publishing_leave_attachments_out():
    from aura.rag.retriever import AccessScope, SearchRequest, build_filter

    flt = build_filter(SearchRequest(query="TAM"), AccessScope(("public",), own_startup_id="s1"))
    assert [c.key for c in flt.must_not] == ["doc_kind"] and flt.must_not[0].match.any == ["attachment"]
