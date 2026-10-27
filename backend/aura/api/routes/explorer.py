"""The embedding explorer: the 2-D map of deck chunks, query placement with HNSW neighbours, and index stats.

Deck-chunk maps need the ``chunk_explorer`` feature (Angel+) unless you are looking at your own startup.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from qdrant_client import models
from sqlalchemy import select

from aura.access import is_owner, visible_startup
from aura.api.deps import Viewer, current_viewer, require_feature
from aura.core.db import read_session
from aura.core.embeddings import DenseEmbedder
from aura.models import Chunk, Document, Startup
from aura.rag import projection, store
from aura.rag.retriever import AccessScope, SearchRequest, build_filter, search

router = APIRouter(prefix="/api/explorer", tags=["explorer"])


def _scope_for_map(viewer: Viewer, startup_id: str | None) -> tuple[AccessScope, list[str] | None]:
    if startup_id:
        startup = visible_startup(viewer, startup_id)
        if not is_owner(viewer, startup):
            require_feature(viewer, "chunk_explorer")
        return AccessScope.for_viewer(viewer), [startup.id]
    require_feature(viewer, "chunk_explorer")
    return AccessScope.for_viewer(viewer), None


@router.get("/map")
def chunk_map(startup_id: str | None = Query(default=None), viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    scope, startup_ids = _scope_for_map(viewer, startup_id)
    with read_session() as s:
        query = (
            select(Chunk, Startup.name, Startup.domain)
            .join(Startup, Startup.id == Chunk.startup_id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.proj_x.is_not(None), Document.thread_id.is_(None))
        )
        if startup_ids:
            query = query.where(Chunk.startup_id.in_(startup_ids))
        rows = s.execute(query.order_by(Chunk.startup_id, Chunk.page_no, Chunk.seq)).all()
    points = []
    for chunk, name, domain in rows:
        own = scope.own_startup_id == chunk.startup_id
        if not own and chunk.visibility not in scope.visibilities:
            continue
        points.append({
            "chunk_id": chunk.id, "cid": chunk.cid, "startup_id": chunk.startup_id, "startup_name": name,
            "domain": domain, "document_id": chunk.document_id, "page_no": chunk.page_no,
            "slide_title": chunk.slide_title, "preview": chunk.text[:160], "x": chunk.proj_x, "y": chunk.proj_y,
            "origin": chunk.origin, "review": chunk.review, "injection_suspected": chunk.injection_suspected,
        })
    return {"points": points, "projection": projection.current()}


class ExplorerQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    startup_id: str | None = None
    k: int = Field(default=8, ge=1, le=20)


async def _neighbours(vector: list[float], flt: models.Filter, *, exact: bool, limit: int = 10) -> list[models.ScoredPoint]:
    response = await store.client().query_points(
        store.names.chunks, query=vector, using="dense", query_filter=flt, limit=limit, with_payload=True,
        search_params=models.SearchParams(hnsw_ef=128, exact=exact),
    )
    return list(response.points)


@router.post("/query")
async def explorer_query(body: ExplorerQuery, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    scope, startup_ids = _scope_for_map(viewer, body.startup_id)
    request = SearchRequest(query=body.query, startup_ids=startup_ids, k=body.k)
    result = await search(request, scope)
    vector = (await DenseEmbedder().embed([body.query]))[0].tolist()
    flt = build_filter(request, scope)
    exact = await _neighbours(vector, flt, exact=True)
    approximate = await _neighbours(vector, flt, exact=False)
    exact_ids = {str(p.id) for p in exact}
    ann_recall = len(exact_ids & {str(p.id) for p in approximate}) / len(exact_ids) if exact_ids else None

    def xy(point: models.ScoredPoint) -> tuple[float, float] | None:
        proj = (point.payload or {}).get("proj")
        return (proj["x"], proj["y"]) if proj else None

    placed = projection.place([(float(p.score), xy(p)) for p in exact])
    return {
        "query": body.query,
        "point": {"x": placed[0], "y": placed[1]} if placed else None,
        "neighbours": [
            {"chunk_id": str(p.id), "cid": (p.payload or {}).get("cid"), "similarity": round(float(p.score), 4),
             "x": (xy(p) or (None, None))[0], "y": (xy(p) or (None, None))[1],
             "page_no": (p.payload or {}).get("page_no"), "startup_name": (p.payload or {}).get("startup_name")}
            for p in approximate
        ],
        "ann_recall_at_10": ann_recall,
        "hits": [h.to_dict() for h in result.hits],
        "timings_ms": result.timings_ms,
    }


@router.get("/stats")
async def explorer_stats(_: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    return {"index": await store.collection_stats(), "projection": projection.current()}
