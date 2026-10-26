"""Local retrieval models (fastembed, ONNX on CPU): BM25 sparse encoder and a cross-encoder reranker.

Both load lazily and once; the reranker runs behind a lock because ONNX sessions are CPU-bound. BM25's
``avg_len`` is set for deck chunks (slides are short), not fastembed's 256-token default.
"""

import threading
from functools import lru_cache
from typing import Any

from aura.core.config import get_settings

BM25_MODEL = "Qdrant/bm25"
BM25_AVG_LEN = 80.0
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

_rerank_lock = threading.Lock()


def _cache_dir() -> str:
    path = get_settings().cache_path / "models" / "fastembed"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@lru_cache
def bm25() -> Any:
    from fastembed.sparse.bm25 import Bm25

    return Bm25(BM25_MODEL, cache_dir=_cache_dir(), avg_len=BM25_AVG_LEN)


@lru_cache
def cross_encoder() -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(RERANK_MODEL, cache_dir=_cache_dir(), threads=2)


def sparse_docs(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    return [(e.indices.tolist(), e.values.tolist()) for e in bm25().embed(texts)]


def sparse_query(text: str) -> tuple[list[int], list[float]]:
    embedding = next(iter(bm25().query_embed(text)))
    return embedding.indices.tolist(), [float(v) for v in embedding.values]


def rerank(query: str, documents: list[str]) -> list[float]:
    if not documents:
        return []
    with _rerank_lock:
        return [float(s) for s in cross_encoder().rerank(query, documents, batch_size=32)]
