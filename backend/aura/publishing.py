"""Publishing a startup: one place that flips every copy of its visibility (startup, documents, chunks in
the database and in Qdrant, the latest complete evaluation) and refreshes its catalogue vector."""

import logging

from sqlalchemy import func, select, update

from aura.core import clock
from aura.core.db import write_tx
from aura.core.errors import AppError
from aura.models import Chunk, Document, Evaluation, Startup
from aura.rag import profiles, store

logger = logging.getLogger("aura.publishing")


async def publish_startup(startup_id: str) -> Startup:
    """Requires a processed deck and a complete evaluation; raises AppError (409) otherwise."""
    with write_tx() as s:
        startup = s.get(Startup, startup_id)
        ready = s.scalar(select(func.count()).select_from(Document)
                         .where(Document.startup_id == startup_id, Document.status == "ready")) or 0
        if ready == 0:
            raise AppError("Upload a pitch deck before publishing", code="DECK_REQUIRED", status=409)
        latest = s.scalars(select(Evaluation).where(Evaluation.startup_id == startup_id, Evaluation.status == "complete")
                           .order_by(Evaluation.version.desc()).limit(1)).first()
        if latest is None:
            raise AppError("Run an AI evaluation before publishing", code="EVALUATION_REQUIRED", status=409)
        startup.status = "published"
        startup.published_at = startup.published_at or clock.now()
        s.execute(update(Document).where(Document.startup_id == startup_id, Document.status == "ready")
                  .values(visibility="published"))
        s.execute(update(Chunk).where(Chunk.startup_id == startup_id).values(visibility="dao"))
        latest.visibility = "published"
        startup.latest_evaluation_id = latest.id
        startup.ai_score_x10 = latest.overall_score_x10
        startup.recommendation = latest.recommendation
        startup.updated_at = clock.now()
        s.flush()
        s.expunge(startup)
    await store.set_startup_visibility(startup_id, "dao")
    try:
        await profiles.index_startup(startup_id)
    except Exception as exc:  # semantic catalogue search is an extra; publishing must not depend on it
        logger.warning("could not index the profile of %s: %s", startup_id, exc)
    return startup
