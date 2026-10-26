"""Hybrid retrieval with per-stage provenance.

One batched Qdrant call runs the dense (HNSW) query, the BM25 query and their RRF fusion together, so every
hit carries its rank in each stage. ``hybrid_rerank`` then reorders the fused candidates with a local
cross-encoder. A per-page cap keeps one slide from crowding out the rest.

Access control: the filter always comes from the server-side ``AccessScope`` (viewer role and plan), never
from tool or request arguments. Scouts see no deck chunks; founders see their own drafts.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from qdrant_client import models

from aura.core.embeddings import DenseEmbedder
from aura.rag import models as rag_models
from aura.rag import store

Mode = Literal["dense", "sparse", "hybrid", "hybrid_rerank"]
RERANK_CANDIDATES = 30


@dataclass(frozen=True)
class AccessScope:
    visibilities: tuple[str, ...]
    own_startup_id: str | None = None

    @classmethod
    def for_viewer(cls, viewer: Any) -> "AccessScope":
        if getattr(viewer, "is_admin", False):
            return cls(("public", "dao", "private"))
        if viewer.role == "investor":
            return cls(("public", "dao") if viewer.has("deck_access") else ("public",))
        return cls(("public",), own_startup_id=viewer.startup_id)


@dataclass
class SearchRequest:
    query: str
    startup_ids: list[str] | None = None
    doc_kinds: list[str] | None = None
    pages: list[int] | None = None
    k: int = 8
    mode: Mode = "hybrid_rerank"
    per_page_cap: int = 2
    prefetch: int = 40
    exact: bool = False


@dataclass
class Hit:
    point_id: str
    payload: dict[str, Any]
    ranks: dict[str, int | None] = field(default_factory=dict)
    scores: dict[str, float | None] = field(default_factory=dict)

    @property
    def cid(self) -> str:
        return self.payload["cid"]

    def to_dict(self, *, with_text: bool = True) -> dict[str, Any]:
        p = self.payload
        out = {
            "chunk_id": p["chunk_id"],
            "cid": p["cid"],
            "startup_id": p["startup_id"],
            "startup_name": p.get("startup_name"),
            "doc_id": p["doc_id"],
            "page_no": p["page_no"],
            "page_count": p.get("page_count"),
            "slide_title": p.get("slide_title"),
            "bbox": p.get("bbox"),
            "geom_exact": p.get("geom_exact", True),
            "origin": p.get("origin"),
            "conf_min": p.get("conf_min"),
            "review": p.get("review", False),
            "injection_suspected": p.get("injection_suspected", False),
            "proj": p.get("proj"),
            "ranks": self.ranks,
            "scores": self.scores,
        }
        if with_text:
            out["text"] = p.get("text", "")
            out["ctx"] = p.get("ctx", "")
        return out


@dataclass
class SearchResult:
    query: str
    mode: Mode
    hits: list[Hit]
    timings_ms: dict[str, int]
    candidates: int


def build_filter(req: SearchRequest, scope: AccessScope) -> models.Filter:
    allowed = [models.FieldCondition(key="visibility", match=models.MatchAny(any=list(scope.visibilities)))]
    access: list[models.Filter | models.FieldCondition] = [models.Filter(must=allowed)]
    if scope.own_startup_id:
        access.append(models.FieldCondition(key="startup_id", match=models.MatchValue(value=scope.own_startup_id)))
    must: list[models.Condition] = [models.Filter(should=access)]
    if req.startup_ids:
        must.append(models.FieldCondition(key="startup_id", match=models.MatchAny(any=req.startup_ids)))
    if req.doc_kinds:
        must.append(models.FieldCondition(key="doc_kind", match=models.MatchAny(any=req.doc_kinds)))
    if req.pages:
        must.append(models.FieldCondition(key="page_no", match=models.MatchAny(any=req.pages)))
    return models.Filter(must=must)


def _ranked(points: list[models.ScoredPoint]) -> dict[str, tuple[int, float, dict]]:
    return {str(p.id): (i + 1, float(p.score), p.payload or {}) for i, p in enumerate(points)}


async def search(req: SearchRequest, scope: AccessScope) -> SearchResult:
    started = time.perf_counter()
    timings: dict[str, int] = {}
    use_dense = req.mode in ("dense", "hybrid", "hybrid_rerank")
    use_sparse = req.mode in ("sparse", "hybrid", "hybrid_rerank")
    fused = req.mode in ("hybrid", "hybrid_rerank")

    dense_vec: list[float] | None = None
    sparse_vec: models.SparseVector | None = None
    if use_dense:
        t = time.perf_counter()
        dense_vec = (await DenseEmbedder().embed([req.query]))[0].tolist()
        timings["embed"] = int((time.perf_counter() - t) * 1000)
    if use_sparse:
        indices, values = await asyncio.to_thread(rag_models.sparse_query, req.query)
        sparse_vec = models.SparseVector(indices=indices, values=values)

    flt = build_filter(req, scope)
    params = models.SearchParams(hnsw_ef=128, exact=req.exact)
    requests: list[models.QueryRequest] = []
    labels: list[str] = []
    if use_dense:
        requests.append(models.QueryRequest(query=dense_vec, using="dense", filter=flt, params=params,
                                            limit=req.prefetch, with_payload=True))
        labels.append("dense")
    if use_sparse:
        requests.append(models.QueryRequest(query=sparse_vec, using="bm25", filter=flt, limit=req.prefetch,
                                            with_payload=True))
        labels.append("sparse")
    if fused:
        requests.append(
            models.QueryRequest(
                prefetch=[
                    models.Prefetch(query=dense_vec, using="dense", filter=flt, params=params, limit=req.prefetch),
                    models.Prefetch(query=sparse_vec, using="bm25", filter=flt, limit=req.prefetch),
                ],
                query=models.RrfQuery(rrf=models.Rrf(k=store.RRF_K)),
                filter=flt,
                limit=req.prefetch,
                with_payload=True,
            )
        )
        labels.append("rrf")

    t = time.perf_counter()
    responses = await store.client().query_batch_points(store.names.chunks, requests=requests)
    timings["qdrant"] = int((time.perf_counter() - t) * 1000)
    stages = {label: _ranked(response.points) for label, response in zip(labels, responses, strict=True)}

    order_stage = "rrf" if fused else labels[0]
    candidates = [
        Hit(
            point_id=pid,
            payload=payload,
            ranks={s: stages[s][pid][0] if pid in stages[s] else None for s in stages},
            scores={s: round(stages[s][pid][1], 5) if pid in stages[s] else None for s in stages},
        )
        for pid, (_, _, payload) in sorted(stages[order_stage].items(), key=lambda kv: kv[1][0])
    ]

    if req.mode == "hybrid_rerank" and candidates:
        head = candidates[:RERANK_CANDIDATES]
        t = time.perf_counter()
        scores = await asyncio.to_thread(
            rag_models.rerank, req.query, [f"{h.payload.get('ctx', '')}\n{h.payload.get('text', '')}" for h in head]
        )
        timings["rerank"] = int((time.perf_counter() - t) * 1000)
        for hit, score in zip(head, scores, strict=True):
            hit.scores["rerank"] = round(score, 4)
        head.sort(key=lambda h: h.scores["rerank"] or float("-inf"), reverse=True)
        for rank, hit in enumerate(head, start=1):
            hit.ranks["rerank"] = rank
        candidates = head + candidates[RERANK_CANDIDATES:]

    hits: list[Hit] = []
    per_page: dict[tuple[str, int], int] = {}
    for hit in candidates:
        key = (hit.payload["doc_id"], int(hit.payload["page_no"]))
        if per_page.get(key, 0) >= req.per_page_cap:
            continue
        per_page[key] = per_page.get(key, 0) + 1
        hits.append(hit)
        if len(hits) >= req.k:
            break
    timings["total"] = int((time.perf_counter() - started) * 1000)
    return SearchResult(query=req.query, mode=req.mode, hits=hits, timings_ms=timings, candidates=len(candidates))
