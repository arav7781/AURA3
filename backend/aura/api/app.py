"""The AURA-3 API application.

Run: ``uv run uvicorn aura.api.app:app --port 8010`` (one worker: the OCR engine and the job runner live
in-process).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from fastapi import FastAPI

from aura.api.middleware import CSRFMiddleware
from aura.api.routes import admin, auth, documents, explorer, jobs, me, public, search
from aura.core import clock, migrate
from aura.core.config import get_settings
from aura.core.db import dispose_engines, init_engines, read_session
from aura.core.errors import install_error_handlers
from aura.core.jobs import fail_orphaned_jobs
from aura.ingest.ocr import ocr_service
from aura.models import AppState
from aura.rag import store
from aura.sandbox.runner import runner

logger = logging.getLogger("aura.api")

_status: dict[str, Any] = {"db": "starting", "qdrant": "starting", "sandbox": "unknown"}
_background: set[asyncio.Task[Any]] = set()


def service_status() -> dict[str, Any]:
    return dict(_status) | {"ocr": ocr_service.status}


def _restore_clock() -> None:
    with read_session() as s:
        row = s.get(AppState, "clock_offset_ms")
    if row is not None:
        clock.set_offset(timedelta(milliseconds=int(row.value)))


async def _start_ocr() -> None:
    try:
        await ocr_service.start()
    except Exception as exc:  # the API stays up; ingestion reports the error per document
        logger.error("TitanOCR failed to start: %s", exc)


async def _start_qdrant() -> None:
    try:
        await store.bootstrap()
        _status["qdrant"] = "ok"
    except Exception as exc:
        _status["qdrant"] = f"unavailable: {exc}"[:200]
        logger.error("Qdrant bootstrap failed: %s", exc)


def _start_sandbox() -> None:
    _status["sandbox"] = runner.status()
    if _status["sandbox"] == "ready":
        reaped = runner.reap()
        if reaped:
            logger.warning("removed %d leftover sandbox container(s)", reaped)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    migrate.upgrade()
    init_engines()
    _restore_clock()
    orphaned = fail_orphaned_jobs()
    if orphaned:
        logger.warning("marked %d interrupted job(s) as failed", orphaned)
    _status["db"] = "ok"
    await _start_qdrant()
    await asyncio.to_thread(_start_sandbox)
    if get_settings().ocr_autostart:
        task = asyncio.create_task(_start_ocr())
        _background.add(task)
        task.add_done_callback(_background.discard)
    logger.info("AURA-3 API ready")
    try:
        yield
    finally:
        ocr_service.close()
        await store.reset_client()
        dispose_engines()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA-3 API",
        version="2.0.0",
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(CSRFMiddleware)
    for module in (auth, me, public, jobs, admin, documents, search, explorer):
        app.include_router(module.router)
    return app


app = create_app()
