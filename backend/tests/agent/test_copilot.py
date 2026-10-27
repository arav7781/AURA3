"""The copilot with a scripted chat model: tools, cards, streamed events, citation checks, plan limits."""

import asyncio
import json
import time
import uuid
from unittest.mock import patch

import pytest
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


def wait(client, run_id: str, timeout: float = 15) -> dict:
    deadline = time.monotonic() + timeout
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


DRAFT = {"slides": [
    {"kind": "cover", "title": "Test Agritech", "subtitle": "Soil sensors for smallholders", "bullets": ["Seed round: raising Rs 2.5 crore"]},
    {"kind": "traction", "title": "Traction", "subtitle": "4x ARR growth in 12 months",
     "stats": [{"value": "Rs 1.6 crore", "label": "ARR, FY2026"}, {"value": "4,100", "label": "Sensors deployed"}],
     "chart": {"title": "ARR (Rs crore)", "labels": ["FY2025", "FY2026"], "values": [0.4, 1.6]},
     "bullets": ["Cooperatives: 7 partnered, up from 3"]},
    {"kind": "business_model", "title": "Business Model",
     "table": [["Stream", "Share", "Gross margin"], ["Hardware", "40%", "35%"], ["Subscription", "60%", "72%"]],
     "bullets": ["LTV / CAC: 4.0x with a 6-month payback"]},
    {"kind": "ask", "title": "The Ask", "stats": [{"value": "Rs 2.5 crore", "label": "Seed round"}],
     "bullets": ["Use of funds: 50% deployment, 30% product, 20% team"]},
]}


async def fake_deck_ingest(ctx, document_id: str, **_):
    """Stands in for TitanOCR: one passage per page with the PDF's own text."""
    import pypdfium2 as pdfium

    from aura.ingest.storage import document_dir
    pdf = pdfium.PdfDocument(str(document_dir(document_id) / "source.pdf"))
    with write_tx() as s:
        doc = s.get(Document, document_id)
        doc.status, doc.page_count = "ready", len(pdf)
        for n in range(len(pdf)):
            s.add(Chunk(id=str(uuid.uuid4()), cid=f"c:{'abcdefghijk'[n]}deckzz", document_id=doc.id, startup_id=doc.startup_id,
                        seq=n, page_no=n + 1, text=pdf[n].get_textpage().get_text_range(), bbox=[0, 0, 1, 1],
                        origin="digital", conf_min=1.0, conf_mean=1.0, n_tokens=10, visibility="private"))
    return {"document_id": document_id}


def test_founders_get_a_designed_deck_they_can_download(client):
    startup_id = published_startup(client)
    thread = client.post("/api/copilot/threads", json={}).json()
    fake = FakeChat([[call("build_pitch_deck", DRAFT)], text("Your deck is ready: download it above.")])
    with patch("aura.agent.graph.chat_model", return_value=fake), patch("aura.agent.tools.ingest_document", fake_deck_ingest):
        wait(client, ask(client, thread["id"], "Create my pitch deck as a PPT")["run_id"])
    answer = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    tool = next(p for p in answer["parts"] if p["type"] == "tool")
    assert tool["status"] == "done", tool
    card = tool["card"]
    assert card["type"] == "deck" and card["pages"] == 4 and card["slides"][0] == "Test Agritech"
    assert card["check"]["figures"] >= 8 and card["check"]["missing"] == []
    assert "found all" in fake.calls[1][-1].content

    pptx = client.get(card["pptx_url"])
    assert pptx.status_code == 200 and pptx.content[:2] == b"PK" and pptx.headers["content-disposition"].endswith('.pptx"')
    assert client.get(card["pdf_url"]).content[:5] == b"%PDF-"
    with write_tx() as s:
        doc = s.get(Document, card["document_id"])
        assert (doc.kind, doc.thread_id, doc.visibility) == ("generated_deck", thread["id"], "private")
    # a private draft: not among the startup's documents, and the next turn can read it
    assert all(d["id"] != card["document_id"] for d in client.get(f"/api/startups/{startup_id}/documents").json()["items"])
    fake2 = FakeChat([[call("read_attachment", {"page": 2})], text("Slide 2 shows ARR Rs 1.6 crore.")])
    with patch("aura.agent.graph.chat_model", return_value=fake2):
        wait(client, ask(client, thread["id"], "What does slide 2 say?")["run_id"])
    assert "Rs 1.6 crore" in fake2.calls[1][-1].content

    register(client, plan="syndicate")
    mine = client.post("/api/copilot/threads", json={}).json()
    fake3 = FakeChat([[call("build_pitch_deck", DRAFT)], text("Only founders can.")])
    with patch("aura.agent.graph.chat_model", return_value=fake3):
        wait(client, ask(client, mine["id"], "make a deck")["run_id"])
    tool = next(p for p in client.get(f"/api/copilot/threads/{mine['id']}").json()["messages"][-1]["parts"] if p["type"] == "tool")
    assert tool["status"] == "error" and tool["card"]["code"] == "FORBIDDEN"


CHART = r"""
import pandas as pd
import matplotlib.pyplot as plt
df = pd.read_csv("startups.csv")
print("startups", len(df), "agritech", int((df.domain == "Agritech").sum()))
df.plot.bar(x="name", y="ai_score")
plt.savefig("out/scores.png", dpi=80)
open("out/evil.svg", "w").write("<svg/>")
"""


@pytest.mark.docker
def test_run_python_runs_in_the_sandbox_and_returns_its_files(client):
    from aura.sandbox.runner import runner

    if runner.status() != "ready":
        pytest.skip("sandbox not available")
    published_startup(client)
    register(client, plan="angel")
    thread = client.post("/api/copilot/threads", json={}).json()
    fake = FakeChat([[call("run_python", {"code": CHART, "purpose": "AI scores"})], text("One agritech startup.")])
    with patch("aura.agent.graph.chat_model", return_value=fake):
        wait(client, ask(client, thread["id"], "Chart the AI scores")["run_id"], timeout=120)  # a cold container
    tool = next(p for p in client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]["parts"] if p["type"] == "tool")
    card = tool["card"]
    assert tool["status"] == "done" and card["status"] == "ok", card
    assert "startups 1 agritech 1" in card["stdout"]
    assert [f["name"] for f in card["files"]] == ["scores.png"]  # the .svg is dropped
    image = client.get(card["files"][0]["url"])
    assert image.status_code == 200 and image.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "startups 1 agritech 1" in fake.calls[1][-1].content

    register(client, plan="angel")  # someone else cannot fetch the file
    assert client.get(card["files"][0]["url"]).status_code == 404
