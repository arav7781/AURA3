"""In-process vector index (cosine similarity over gateway embeddings), persisted to disk."""

import json
import logging
import re
import threading
from typing import Any, Dict, List

import numpy as np

from aura.config import DATA_DIR
from aura.llm import embed

logger = logging.getLogger("aura.vectors")

_VECTOR_DIR = DATA_DIR / "vectors"
_VECTOR_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.RLock()
_collections: Dict[str, Dict[str, Any]] = {}


def _safe_name(collection: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", collection)


def _load(collection: str) -> Dict[str, Any]:
    with _lock:
        if collection in _collections:
            return _collections[collection]
        name = _safe_name(collection)
        meta_path, vec_path = _VECTOR_DIR / f"{name}.json", _VECTOR_DIR / f"{name}.npy"
        if meta_path.exists() and vec_path.exists():
            meta = json.loads(meta_path.read_text())
            entry = {"texts": meta["texts"], "metadata": meta["metadata"], "vectors": np.load(vec_path)}
        else:
            entry = {"texts": [], "metadata": [], "vectors": np.zeros((0, 0), dtype=np.float32)}
        _collections[collection] = entry
        return entry


def _persist(collection: str, entry: Dict[str, Any]) -> None:
    name = _safe_name(collection)
    (_VECTOR_DIR / f"{name}.json").write_text(
        json.dumps({"texts": entry["texts"], "metadata": entry["metadata"]})
    )
    np.save(_VECTOR_DIR / f"{name}.npy", entry["vectors"])


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def add_texts(collection: str, texts: List[str], metadata: List[Dict[str, Any]]) -> int:
    """Embed and index texts. Returns the number of chunks added."""
    if not texts:
        return 0
    vectors = _normalise(np.asarray(embed(texts), dtype=np.float32))
    with _lock:
        entry = _load(collection)
        entry["vectors"] = vectors if entry["vectors"].size == 0 else np.vstack([entry["vectors"], vectors])
        entry["texts"].extend(texts)
        entry["metadata"].extend(metadata)
        _persist(collection, entry)
    logger.info(f"Indexed {len(texts)} chunks into '{collection}' ({len(entry['texts'])} total)")
    return len(texts)


def search(collection: str, query: str, k: int = 6) -> List[Dict[str, Any]]:
    """Return the top-k chunks for a query as {text, metadata, score}."""
    entry = _load(collection)
    if not entry["texts"]:
        return []
    query_vec = _normalise(np.asarray(embed([query]), dtype=np.float32))[0]
    scores = entry["vectors"] @ query_vec
    top = np.argsort(-scores)[:k]
    return [
        {"text": entry["texts"][i], "metadata": entry["metadata"][i], "score": float(scores[i])}
        for i in top
    ]


def count(collection: str) -> int:
    return len(_load(collection)["texts"])


def reset(collection: str) -> None:
    with _lock:
        _collections.pop(collection, None)
        name = _safe_name(collection)
        for suffix in (".json", ".npy"):
            (_VECTOR_DIR / f"{name}{suffix}").unlink(missing_ok=True)
