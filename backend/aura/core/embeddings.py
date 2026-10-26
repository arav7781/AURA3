"""Dense embeddings through the gateway, with an on-disk cache.

Vectors are L2-normalised float32. The cache key is sha256(model | dims | text), so changing the model
or dimension never returns stale vectors, and re-seeding or re-running evals costs no gateway calls.
"""

import asyncio
import hashlib
import logging
import sqlite3
import threading
from pathlib import Path

import httpx
import numpy as np

from aura.core.config import get_settings

logger = logging.getLogger("aura.embeddings")

_BATCH = 64


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, dims INTEGER, vec BLOB)")
        self._lock = threading.Lock()

    def get_many(self, keys: list[str]) -> dict[str, np.ndarray]:
        found: dict[str, np.ndarray] = {}
        with self._lock:
            for start in range(0, len(keys), 500):
                chunk = keys[start : start + 500]
                rows = self._db.execute(
                    f"SELECT key, vec FROM vectors WHERE key IN ({','.join('?' * len(chunk))})", chunk
                ).fetchall()
                for key, blob in rows:
                    found[key] = np.frombuffer(blob, dtype=np.float32)
        return found

    def put_many(self, items: dict[str, np.ndarray]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO vectors (key, dims, vec) VALUES (?, ?, ?)",
                [(k, int(v.shape[0]), v.astype(np.float32).tobytes()) for k, v in items.items()],
            )
            self._db.commit()


class DenseEmbedder:
    def __init__(self, model: str | None = None, dims: int | None = None) -> None:
        settings = get_settings()
        self.model = model or settings.embed_model
        self.dims = dims or settings.embed_dims
        self._cache = _cache_for(settings.data_dir)

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}|{self.dims}|{text}".encode()).hexdigest()

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed ``texts`` -> (n, dims) float32, L2-normalised, in input order."""
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        keys = [self._key(t) for t in texts]
        cached = self._cache.get_many(list(dict.fromkeys(keys)))
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            todo = list(dict.fromkeys(texts[i] for i in missing))
            fresh = await self._fetch(todo)
            new_items = {self._key(t): v for t, v in zip(todo, fresh, strict=True)}
            self._cache.put_many(new_items)
            cached.update(new_items)
        return np.stack([cached[k] for k in keys]).astype(np.float32)

    def embed_sync(self, texts: list[str]) -> np.ndarray:
        return asyncio.run(self.embed(texts))

    async def _fetch(self, texts: list[str]) -> list[np.ndarray]:
        settings = get_settings()
        settings.require_llm()
        out: list[np.ndarray] = []
        async with httpx.AsyncClient(timeout=120.0) as client:
            for start in range(0, len(texts), _BATCH):
                batch = [t if t.strip() else " " for t in texts[start : start + _BATCH]]
                payload = {"model": self.model, "input": batch, "dimensions": self.dims, "encoding_format": "float"}
                for attempt in range(4):
                    try:
                        resp = await client.post(
                            f"{settings.llm_base_url.rstrip('/')}/embeddings",
                            headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
                            json=payload,
                        )
                        resp.raise_for_status()
                        data = sorted(resp.json()["data"], key=lambda item: item.get("index", 0))
                        for item in data:
                            vec = np.asarray(item["embedding"], dtype=np.float32)
                            if vec.shape[0] != self.dims:
                                raise ValueError(f"expected {self.dims} dims, got {vec.shape[0]}")
                            out.append(vec / (np.linalg.norm(vec) or 1.0))
                        break
                    except (httpx.HTTPError, KeyError, ValueError) as exc:
                        if attempt == 3:
                            raise
                        logger.warning("embedding batch failed (attempt %d): %s", attempt + 1, exc)
                        await asyncio.sleep(1.5 * (attempt + 1))
        return out


_caches: dict[Path, EmbeddingCache] = {}
_caches_lock = threading.Lock()


def _cache_for(data_dir: Path) -> EmbeddingCache:
    with _caches_lock:
        if data_dir not in _caches:
            _caches[data_dir] = EmbeddingCache(data_dir / "cache" / "embeddings.sqlite")
        return _caches[data_dir]
