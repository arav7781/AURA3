"""Admin tools for the demo: an echo job (to exercise live progress end to end), the demo clock, the
ledger audit. Everything here requires an admin; the clock and echo job also require demo mode."""

import asyncio
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aura.api.deps import Viewer, admin
from aura.core import clock
from aura.core.config import get_settings
from aura.core.db import read_session, write_tx
from aura.core.errors import Forbidden
from aura.core.jobs import JobContext, start_job
from aura.ledger.audit import run_audit
from aura.models import AppState

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _demo_only() -> None:
    if not get_settings().demo_mode:
        raise Forbidden("Only available in demo mode", code="DEMO_ONLY")


class EchoIn(BaseModel):
    steps: int = Field(default=5, ge=1, le=50)
    delay_ms: int = Field(default=200, ge=0, le=60_000)


@router.post("/jobs/echo", status_code=202)
async def echo_job(body: EchoIn, viewer: Viewer = Depends(admin)) -> dict[str, Any]:
    _demo_only()

    async def run(ctx: JobContext) -> dict[str, Any]:
        for i in range(1, body.steps + 1):
            await asyncio.sleep(body.delay_ms / 1000)
            ctx.progress(f"step {i}", pct=round(100 * i / body.steps))
        return {"steps": body.steps}

    job_id = start_job("echo", run, owner_user_id=viewer.user_id, payload=body.model_dump())
    return {"job_id": job_id}


class ClockIn(BaseModel):
    advance_seconds: int = Field(ge=0, le=60 * 60 * 24 * 400)


@router.post("/clock")
def advance_clock(body: ClockIn, _: Viewer = Depends(admin)) -> dict[str, Any]:
    _demo_only()
    clock.advance(timedelta(seconds=body.advance_seconds))
    offset_ms = int(clock.offset().total_seconds() * 1000)
    with write_tx() as s:
        row = s.get(AppState, "clock_offset_ms")
        if row is None:
            s.add(AppState(key="clock_offset_ms", value=str(offset_ms)))
        else:
            row.value = str(offset_ms)
    return {"now": clock.iso(clock.now()), "offset_ms": offset_ms}


@router.get("/audit")
def audit(_: Viewer = Depends(admin)) -> dict[str, Any]:
    with read_session() as s:
        results = run_audit(s)
    return {"ok": not any(results.values()), "checks": results}
