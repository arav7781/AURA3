"""End to end: upload → TitanOCR → chunks with provenance → Qdrant (HNSW + BM25) → hybrid retrieval."""

import asyncio

from sqlalchemy import func, select, update

from aura.core.db import read_session, write_tx
from aura.ingest.chunker import CHUNKER_VERSION
from aura.models import Chunk, Document, InvestorProfile, Startup, User
from aura.rag import store
from aura.rag.retriever import AccessScope, SearchRequest, search
from tests.integration.conftest import DECK, upload


def test_ingestion_streams_every_stage(live):
    stages = [e["data"].get("stage") for e in live.events if e["event"] == "job_progress"]
    for stage in ("ocr", "rendering", "scanning", "chunking", "embedding", "indexing"):
        assert stage in stages
    assert live.events[-1]["event"] == "job_done"
    result = live.events[-1]["data"]["result"]
    assert result["pages"] == 11 and result["chunks"] == 11 and result["indexed"] == 11


def test_document_pages_and_images(live):
    doc = live.client.get(f"/api/documents/{live.document_id}").json()
    assert doc["status"] == "ready" and doc["page_count"] == 11 and doc["chunk_count"] == 11
    assert doc["versions"]["titanocr"] == "0.2.0" and doc["versions"]["chunker"] == CHUNKER_VERSION
    page4 = doc["pages"][3]
    assert page4["slide_title"] == "Market Opportunity (TAM / SAM / SOM)" and page4["geom_exact"]
    image = live.client.get(page4["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    chunks = live.client.get(f"/api/documents/{live.document_id}/pages/4/chunks").json()["items"]
    assert "USD 82.3M in 2025" in chunks[0]["text"] and chunks[0]["lines"]


def test_vectors_match_rows_and_hnsw_is_built(live):
    with read_session() as s:
        rows = s.scalar(select(func.count()).select_from(Chunk))
    stats = asyncio.run(store.collection_stats())
    assert stats["points"] == rows == 11
    assert stats["hnsw"]["m"] == 16


def test_duplicate_upload_is_rejected(live):
    response = upload(live.client, live.startup_id, DECK, filename="again.pdf")
    assert response.status_code == 409 and response.json()["error"]["code"] == "DUPLICATE_DOCUMENT"


def test_owner_retrieves_the_right_slide(live):
    hits = live.client.post("/api/search", json={"query": "What TAM does KrishiMitra claim for 2025?"}).json()["hits"]
    assert hits[0]["page_no"] == 4 and "82.3" in hits[0]["text"]
    assert set(hits[0]["ranks"]) == {"dense", "sparse", "rrf", "rerank"}


def test_server_rrf_matches_client_side_fusion(live):
    async def run():
        scope = AccessScope(("public", "dao", "private"))
        fused = await search(SearchRequest(query="unit economics CAC payback", mode="hybrid", k=11, per_page_cap=11), scope)
        return fused.hits

    hits = asyncio.run(run())

    def rrf(hit):
        return sum(1 / (store.RRF_K + r - 1) for r in (hit.ranks.get("dense"), hit.ranks.get("sparse")) if r)

    expected = sorted(hits, key=lambda h: (-rrf(h), h.ranks["rrf"]))
    assert [h.point_id for h in hits] == [h.point_id for h in expected]


def test_access_rules_for_draft_and_published_decks(live):
    client = live.client
    # An Angel investor cannot see a draft startup's deck at all.
    client.cookies.clear()
    angel = {"email": "angel@x.test", "password": "correct-horse-battery", "name": "Priya", "role": "investor",
             "plan": "angel"}
    client.post("/api/auth/register", json=angel)
    assert client.get(f"/api/documents/{live.document_id}").status_code == 404
    assert client.post("/api/search", json={"query": "TAM 2025"}).json()["hits"] == []

    # Publish the startup and its deck (what the founder flow will do), then the Angel can see it.
    with write_tx() as s:
        s.execute(update(Startup).where(Startup.id == live.startup_id).values(status="published"))
        s.execute(update(Document).where(Document.id == live.document_id).values(visibility="published"))
    asyncio.run(store.set_startup_visibility(live.startup_id, "dao"))
    assert client.get(f"/api/documents/{live.document_id}").status_code == 200
    assert client.post("/api/search", json={"query": "TAM 2025"}).json()["hits"][0]["page_no"] == 4

    # A Scout gets an upsell for the deck and no deck chunks from search.
    with write_tx() as s:
        uid = s.scalar(select(User.id).where(User.email == angel["email"]))
        s.execute(update(InvestorProfile).where(InvestorProfile.user_id == uid).values(plan="scout"))
    denied = client.get(f"/api/documents/{live.document_id}")
    assert denied.status_code == 403 and denied.json()["error"]["details"]["required_plan"] == "angel"
    assert client.post("/api/search", json={"query": "TAM 2025"}).json()["hits"] == []


def test_embedding_map_and_query_placement(live):
    client = live.client
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": live.founder["email"],
                                                "password": live.founder["password"]}).status_code == 200
    assert live.events[-1]["data"]["result"]["map"] in ("refit", "placed")
    payload = client.get("/api/explorer/map", params={"startup_id": live.startup_id}).json()
    points = payload["points"]
    assert len(points) == 11 and payload["projection"]["points"] == 11
    assert all(-1.0 <= p["x"] <= 1.0 and -1.0 <= p["y"] <= 1.0 for p in points)
    result = client.post("/api/explorer/query", json={"query": "How big is the market?",
                                                      "startup_id": live.startup_id}).json()
    assert result["point"] is not None and len(result["neighbours"]) == 10
    assert result["ann_recall_at_10"] == 1.0
    assert result["hits"][0]["page_no"] == 4
