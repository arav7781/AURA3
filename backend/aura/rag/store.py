"""Qdrant collections and queries.

``aura_chunks`` (an alias of ``aura_chunks_v1``, so a re-index can be built and swapped atomically) holds
one point per deck chunk with two vectors:
- ``dense``: text-embedding-3-large at 1024 dims, cosine, HNSW (m=16, ef_construct=128);
- ``bm25``: a sparse BM25 vector (Qdrant applies IDF).

At demo scale (hundreds of chunks) Qdrant would never build the HNSW graph and would scan exactly, so the
indexing and full-scan thresholds are set tiny: the collection really is served by HNSW, including filtered
per-startup queries (``payload_m`` builds tenant-aware links). ``ann_vs_exact`` measures the recall cost.

``aura_startups`` holds one profile vector per startup for catalogue search and "similar startups".
"""

import warnings
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from aura.core.config import get_settings

RRF_K = 61  # Qdrant ranks from 0; k=61 equals the RRF paper's k=60 with 1-based ranks
VERSION = "v1"

_client: AsyncQdrantClient | None = None


class _Names:
    """Collection names, derived from the configured prefix (``aura`` in the app, a throwaway one in tests)."""

    @property
    def prefix(self) -> str:
        return get_settings().qdrant_prefix

    @property
    def chunks(self) -> str:
        return f"{self.prefix}_chunks"

    @property
    def chunks_v(self) -> str:
        return f"{self.prefix}_chunks_{VERSION}"

    @property
    def startups(self) -> str:
        return f"{self.prefix}_startups"

    @property
    def startups_v(self) -> str:
        return f"{self.prefix}_startups_{VERSION}"


names = _Names()


def client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        with warnings.catch_warnings():
            # Qdrant listens on 127.0.0.1 only; plain HTTP to localhost is expected in local development.
            warnings.filterwarnings("ignore", message="Api key is used with an insecure connection")
            _client = AsyncQdrantClient(url=settings.qdrant_url, api_key=key, prefer_grpc=False, timeout=30)
    return _client


async def reset_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
    _client = None


def _hnsw() -> models.HnswConfigDiff:
    return models.HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10, payload_m=16)


async def _ensure(name: str, alias: str, vectors: dict, sparse: dict | None, keyword_fields: list[str],
                  int_fields: list[str]) -> None:
    c = client()
    if not await c.collection_exists(name):
        await c.create_collection(
            name,
            vectors_config=vectors,
            sparse_vectors_config=sparse,
            hnsw_config=_hnsw(),
            optimizers_config=models.OptimizersConfigDiff(indexing_threshold=1, default_segment_number=2),
        )
        await c.create_payload_index(
            name, "startup_id",
            field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True),
        )
        for field in keyword_fields:
            await c.create_payload_index(name, field, field_schema=models.PayloadSchemaType.KEYWORD)
        for field in int_fields:
            await c.create_payload_index(name, field, field_schema=models.PayloadSchemaType.INTEGER)
    aliases = {a.alias_name: a.collection_name for a in (await c.get_aliases()).aliases}
    if aliases.get(alias) != name:
        ops: list[Any] = []
        if alias in aliases:
            ops.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
        ops.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=name, alias_name=alias)))
        await c.update_collection_aliases(change_aliases_operations=ops)


async def bootstrap(dims: int | None = None) -> None:
    dims = dims or get_settings().embed_dims
    dense = {"dense": models.VectorParams(size=dims, distance=models.Distance.COSINE)}
    await _ensure(
        names.chunks_v, names.chunks, dense, {"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        keyword_fields=["doc_id", "domain", "stage", "doc_kind", "visibility", "cid"], int_fields=["page_no"],
    )
    await _ensure(names.startups_v, names.startups, dense, None, keyword_fields=["domain", "stage", "visibility"], int_fields=[])


async def upsert_chunks(points: list[models.PointStruct]) -> None:
    for start in range(0, len(points), 128):
        await client().upsert(names.chunks, points=points[start : start + 128], wait=True)


async def delete_document(doc_id: str) -> None:
    await client().delete(
        names.chunks,
        points_selector=models.FilterSelector(
            filter=models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])
        ),
        wait=True,
    )


async def set_startup_visibility(startup_id: str, visibility: str) -> None:
    await client().set_payload(
        names.chunks,
        payload={"visibility": visibility},
        points=models.Filter(must=[models.FieldCondition(key="startup_id", match=models.MatchValue(value=startup_id))]),
        wait=True,
    )


async def set_projection(coords: dict[str, tuple[float, float]], version: int) -> None:
    c = client()
    for point_id, (x, y) in coords.items():
        await c.set_payload(names.chunks, payload={"proj": {"x": x, "y": y, "v": version}}, points=[point_id], wait=False)


async def collection_stats() -> dict[str, Any]:
    info = await client().get_collection(names.chunks)
    hnsw = info.config.hnsw_config
    return {
        "points": info.points_count,
        "indexed_vectors": info.indexed_vectors_count,
        "segments": info.segments_count,
        "status": str(info.status.value if hasattr(info.status, "value") else info.status),
        "hnsw": {"m": hnsw.m, "ef_construct": hnsw.ef_construct, "full_scan_threshold": hnsw.full_scan_threshold,
                 "payload_m": hnsw.payload_m},
    }


async def upsert_startup(point: models.PointStruct) -> None:
    await client().upsert(names.startups, points=[point], wait=True)
