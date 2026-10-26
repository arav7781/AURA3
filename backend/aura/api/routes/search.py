from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aura.api.deps import Viewer, current_viewer
from aura.rag.retriever import AccessScope, SearchRequest, search

router = APIRouter(prefix="/api", tags=["search"])


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    startup_ids: list[str] | None = Field(default=None, max_length=25)
    mode: Literal["dense", "sparse", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    k: int = Field(default=8, ge=1, le=25)


@router.post("/search")
async def search_passages(body: SearchIn, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    result = await search(
        SearchRequest(query=body.query, startup_ids=body.startup_ids, mode=body.mode, k=body.k),
        AccessScope.for_viewer(viewer),
    )
    return {
        "query": result.query,
        "mode": result.mode,
        "hits": [h.to_dict() for h in result.hits],
        "timings_ms": result.timings_ms,
        "candidates": result.candidates,
    }
