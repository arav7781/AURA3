"""The embedding map: every deck chunk projected to 2-D, so people can see how TitanOCR's output lands
in vector space.

- ``refit`` reads all dense vectors from Qdrant and projects them with UMAP (cosine, n_neighbors=15,
  seed 42); PCA is the fallback when umap-learn is not installed or there are very few points. Coordinates
  are scaled to [-1, 1] and written to SQLite and the Qdrant payload, with the projection's quality
  (trustworthiness@10: how well 2-D neighbourhoods preserve the 1024-D ones).
- ``place`` puts a new point (a query or a freshly ingested chunk) on the existing map as the
  similarity-weighted average of its exact top-10 neighbours, so no fitted model has to be stored.
"""

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from qdrant_client import models
from sqlalchemy import update

from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.models import AppState, Chunk
from aura.rag import store

logger = logging.getLogger("aura.projection")

STATE_KEY = "projection"
PLACE_TEMPERATURE = 0.05


@dataclass
class Projection:
    version: int
    method: str
    points: int
    trustworthiness: float | None
    fitted_at: str
    ms: int


def current() -> dict[str, Any] | None:
    with read_session() as s:
        row = s.get(AppState, STATE_KEY)
    return json.loads(row.value) if row else None


async def _all_vectors() -> tuple[list[str], np.ndarray]:
    ids: list[str] = []
    vectors: list[list[float]] = []
    offset = None
    while True:
        points, offset = await store.client().scroll(
            store.names.chunks, limit=256, offset=offset, with_vectors=["dense"], with_payload=False
        )
        for point in points:
            ids.append(str(point.id))
            vectors.append(point.vector["dense"])  # type: ignore[index]
        if offset is None:
            break
    return ids, np.asarray(vectors, dtype=np.float32)


def _scale(coords: np.ndarray) -> np.ndarray:
    centred = coords - coords.mean(axis=0)
    span = np.abs(centred).max() or 1.0
    return centred / span


def _pca(x: np.ndarray) -> np.ndarray:
    centred = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    return centred @ vt[:2].T


def project(x: np.ndarray) -> tuple[np.ndarray, str, float | None]:
    """Project rows of ``x`` to 2-D. Returns (coords scaled to [-1, 1], method, trustworthiness@10)."""
    n = x.shape[0]
    method = "pca"
    coords: np.ndarray
    if n >= 12:
        try:
            import umap

            reducer = umap.UMAP(n_neighbors=min(15, n - 1), min_dist=0.1, metric="cosine", random_state=42)
            coords = reducer.fit_transform(x)
            method = "umap"
        except ImportError:
            coords = _pca(x)
    else:
        coords = _pca(x) if n >= 2 else np.zeros((n, 2))
    trust = None
    if n > 11:
        try:
            from sklearn.manifold import trustworthiness

            trust = round(float(trustworthiness(x, coords, n_neighbors=10, metric="cosine")), 4)
        except ImportError:
            trust = None
    return _scale(np.asarray(coords, dtype=np.float64)), method, trust


async def refit() -> Projection:
    started = time.monotonic()
    ids, vectors = await _all_vectors()
    if not ids:
        raise ValueError("no chunks to project yet")
    coords, method, trust = await asyncio.to_thread(project, vectors)
    previous = current()
    version = int(previous["version"]) + 1 if previous else 1
    mapping = {pid: (round(float(c[0]), 5), round(float(c[1]), 5)) for pid, c in zip(ids, coords, strict=True)}
    await store.set_projection(mapping, version)
    with write_tx() as s:
        for pid, (x, y) in mapping.items():
            s.execute(update(Chunk).where(Chunk.id == pid).values(proj_x=x, proj_y=y, proj_v=version))
        meta = Projection(version, method, len(ids), trust, clock.iso(clock.now()), int((time.monotonic() - started) * 1000))
        row = s.get(AppState, STATE_KEY)
        value = json.dumps(meta.__dict__)
        if row is None:
            s.add(AppState(key=STATE_KEY, value=value))
        else:
            row.value = value
    logger.info("projection v%d: %s over %d points, trustworthiness %s", version, method, len(ids), trust)
    return meta


def place(neighbours: list[tuple[float, tuple[float, float]]]) -> tuple[float, float] | None:
    """Similarity-weighted average of neighbour positions: w = exp(similarity / 0.05)."""
    usable = [(sim, xy) for sim, xy in neighbours if xy is not None]
    if not usable:
        return None
    top = max(sim for sim, _ in usable)
    weights = [math.exp((sim - top) / PLACE_TEMPERATURE) for sim, _ in usable]
    total = sum(weights)
    x = sum(w * xy[0] for w, (_, xy) in zip(weights, usable, strict=True)) / total
    y = sum(w * xy[1] for w, (_, xy) in zip(weights, usable, strict=True)) / total
    return round(x, 5), round(y, 5)


def needs_refit(projected: int, total: int) -> bool:
    return total > 0 and (projected == 0 or (total - projected) / total > 0.2)


_lock = asyncio.Lock()


async def place_new(chunk_ids: list[str]) -> int:
    """Place freshly indexed chunks onto the current map without refitting it."""
    meta = current()
    if not meta or not chunk_ids:
        return 0
    c = store.client()
    has_projection = models.Filter(must_not=[models.IsEmptyCondition(is_empty=models.PayloadField(key="proj"))])
    placed: dict[str, tuple[float, float]] = {}
    for point in await c.retrieve(store.names.chunks, ids=chunk_ids, with_vectors=["dense"]):
        response = await c.query_points(
            store.names.chunks, query=point.vector["dense"], using="dense", query_filter=has_projection,  # type: ignore[index]
            limit=10, with_payload=["proj"], search_params=models.SearchParams(exact=True),
        )
        neighbours = [(float(p.score), (p.payload["proj"]["x"], p.payload["proj"]["y"]))
                      for p in response.points if p.payload and p.payload.get("proj")]
        xy = place(neighbours)
        if xy is not None:
            placed[str(point.id)] = xy
    if placed:
        await store.set_projection(placed, int(meta["version"]))
        with write_tx() as s:
            for pid, (x, y) in placed.items():
                s.execute(update(Chunk).where(Chunk.id == pid).values(proj_x=x, proj_y=y, proj_v=int(meta["version"])))
    return len(placed)


async def refresh(new_chunk_ids: list[str]) -> str:
    """After ingestion: refit if the map is missing or more than 20% of chunks are new, else place them."""
    from sqlalchemy import func, select

    async with _lock:
        with read_session() as s:
            total = s.scalar(select(func.count()).select_from(Chunk)) or 0
            projected = s.scalar(select(func.count()).select_from(Chunk).where(Chunk.proj_x.is_not(None))) or 0
        if needs_refit(projected, total):
            await refit()
            return "refit"
        await place_new(new_chunk_ids)
        return "placed"
