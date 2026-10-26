"""Web research for evaluations, with record/replay.

- ``live``: search the web now.
- ``record``: search live and save every query's results to a cassette file.
- ``replay``: answer from the cassette only, so consistency evals measure the model's variance, not the search
  engine's. The agent words its queries differently on every run, so a query that was not recorded verbatim
  gets the results of the closest recorded query (content-word overlap); with no close match it gets nothing.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Literal

from aura.core import clock
from aura.evaluation.search import web_search

logger = logging.getLogger("aura.research")

Mode = Literal["live", "record", "replay"]
REPLAY_MIN_OVERLAP = 0.3  # Jaccard over content words; rewordings of one question score well above this
_STOPWORDS = frozenset("a an and are as at by for from in is of on or the to vs with what which how".split())


def _key(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _words(query: str) -> frozenset[str]:
    return frozenset(w.removesuffix("s") for w in re.findall(r"[a-z0-9]+", query.lower())
                     if w not in _STOPWORDS and len(w) > 1)


class ResearchProvider:
    def __init__(self, mode: Mode = "live", cassette: Path | None = None) -> None:
        if mode != "live" and cassette is None:
            raise ValueError("record/replay need a cassette path")
        self.mode = mode
        self.cassette = cassette
        self._entries: dict[str, dict] = {}
        if cassette is not None and cassette.exists():
            self._entries = json.loads(cassette.read_text()).get("queries", {})
        self._lock = asyncio.Lock()

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        key = _key(query)
        if self.mode == "replay":
            entry = self._entries.get(key) or self._closest(key)
            if entry is None:
                logger.info("replay: no recorded results for %r", query[:80])
                return []
            return [{**r, "retrieved_at": entry["retrieved_at"]} for r in entry["results"][:max_results]]
        results = await asyncio.to_thread(web_search, query, max_results)
        retrieved_at = clock.iso(clock.now())
        if self.mode == "record":
            async with self._lock:
                self._entries[key] = {"query": query, "retrieved_at": retrieved_at, "results": results}
        return [{**r, "retrieved_at": retrieved_at} for r in results]

    def _closest(self, key: str) -> dict | None:
        wanted = _words(key)
        best, best_overlap = None, 0.0
        for recorded in sorted(self._entries):  # sorted: ties resolve the same way on every run
            words = _words(recorded)
            overlap = len(wanted & words) / len(wanted | words) if wanted | words else 0.0
            if overlap > best_overlap:
                best, best_overlap = recorded, overlap
        if best is None or best_overlap < REPLAY_MIN_OVERLAP:
            return None
        logger.info("replay: %r answered with recorded %r (overlap %.2f)", key[:80], best[:80], best_overlap)
        return self._entries[best]

    def save(self) -> None:
        if self.mode == "record" and self.cassette is not None:
            self.cassette.parent.mkdir(parents=True, exist_ok=True)
            self.cassette.write_text(json.dumps({"queries": self._entries}, indent=1, sort_keys=True))
