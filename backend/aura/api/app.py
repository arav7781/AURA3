"""The AURA-3 API application.

Run: ``uv run uvicorn aura.api.app:app --port 8010`` (one worker: the OCR engine and the job runner live
in-process).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from fastapi import FastAPI

from aura.api.middleware import CSRFMiddleware
from aura.api.routes import admin, auth, jobs, me, public
from aura.core import clock, migrate
from aura.core.db import dispose_engines, init_engines, read_session
from aura.core.errors import install_error_handlers
from aura.core.jobs import fail_orphaned_jobs
from aura.models import AppState

logger = logging.getLogger("aura.api")

_status: dict[str, Any] = {"db": "starting"}


def service_status() -> dict[str, Any]:
    return dict(_status)


def _restore_clock() -> None:
    with read_session() as s:
        row = s.get(AppState, "clock_offset_ms")
    if row is not None:
        clock.set_offset(timedelta(milliseconds=int(row.value)))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    migrate.upgrade()
    init_engines()
    _restore_clock()
    orphaned = fail_orphaned_jobs()
    if orphaned:
        logger.warning("marked %d interrupted job(s) as failed", orphaned)
    _status["db"] = "ok"
    logger.info("AURA-3 API ready")
    try:
        yield
    finally:
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
    for module in (auth, me, public, jobs, admin):
        app.include_router(module.router)
    return app


app = create_app()
