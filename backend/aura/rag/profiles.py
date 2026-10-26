"""One profile vector per startup (collection ``aura_startups``) for semantic catalogue search and
"similar startups"."""

from qdrant_client import models

from aura.core.db import read_session
from aura.core.embeddings import DenseEmbedder
from aura.models import Startup
from aura.rag import store

STAGE_LABELS = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B"}


def profile_text(startup: Startup) -> str:
    parts = [f"{startup.name} · {startup.domain}"
             + (f" ({startup.sub_domain})" if startup.sub_domain else "")
             + f" · {STAGE_LABELS.get(startup.stage, startup.stage)}",
             startup.one_liner or "", startup.description or ""]
    return "\n".join(p for p in parts if p)


async def index_startup(startup_id: str) -> None:
    with read_session() as s:
        startup = s.get(Startup, startup_id)
        if startup is None:
            raise ValueError("startup not found")
        text = profile_text(startup)
        payload = {
            "startup_id": startup.id, "slug": startup.slug, "name": startup.name, "domain": startup.domain,
            "stage": startup.stage, "one_liner": startup.one_liner,
            "visibility": "dao" if startup.status == "published" else "private",
        }
    vector = (await DenseEmbedder().embed([text]))[0]
    await store.upsert_startup(models.PointStruct(id=startup_id, vector={"dense": vector.tolist()}, payload=payload))
