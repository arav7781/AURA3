"""Embed chunks (dense + BM25) and write them to Qdrant with their provenance as payload."""

import asyncio

from qdrant_client import models

from aura.core.config import get_settings
from aura.core.embeddings import DenseEmbedder
from aura.ingest.chunker import ChunkRecord
from aura.rag import models as rag_models
from aura.rag import store


def payload(record: ChunkRecord, *, startup_name: str, domain: str, stage: str, doc_kind: str,
            versions: dict[str, str], injection: bool) -> dict:
    return {
        "chunk_id": record.id,
        "cid": record.cid,
        "startup_id": record.startup_id,
        "startup_name": startup_name,
        "domain": domain,
        "stage": stage,
        "doc_id": record.document_id,
        "doc_kind": doc_kind,
        "page_no": record.page_no,
        "page_count": record.page_count,
        "slide_title": record.slide_title,
        "text": record.text,
        "ctx": record.ctx,
        "bbox": record.bbox,
        "geom_exact": record.geom_exact,
        "origin": record.origin,
        "conf_min": record.conf_min,
        "review": record.review,
        "has_table": record.has_table,
        "injection_suspected": injection,
        "n_tokens": record.n_tokens,
        "visibility": record.visibility,
        "versions": versions,
    }


async def index_chunks(records: list[ChunkRecord], *, startup_name: str, domain: str, stage: str, doc_kind: str,
                       versions: dict[str, str], injected_ids: set[str]) -> int:
    if not records:
        return 0
    texts = [r.embed_text for r in records]
    dense = await DenseEmbedder().embed(texts)
    sparse = await asyncio.to_thread(rag_models.sparse_docs, texts)
    points = [
        models.PointStruct(
            id=record.id,
            vector={"dense": dense[i].tolist(), "bm25": models.SparseVector(indices=sparse[i][0], values=sparse[i][1])},
            payload=payload(record, startup_name=startup_name, domain=domain, stage=stage, doc_kind=doc_kind,
                            versions=versions | {"embed": f"{get_settings().embed_model}@{get_settings().embed_dims}"},
                            injection=record.id in injected_ids),
        )
        for i, record in enumerate(records)
    ]
    await store.upsert_chunks(points)
    return len(points)
