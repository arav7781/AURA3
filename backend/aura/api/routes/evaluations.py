"""Evaluations: run and cancel (owner), read (owner or investors; Scouts get a redacted view), publish, and
PDF export.

The PDF endpoint only renders an existing evaluation; it never runs one inside the request.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select

from aura import quotas
from aura.access import is_owner, visible_startup
from aura.api.deps import Viewer, current_viewer, require_feature
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.errors import AppError, NotFound
from aura.evaluation import service
from aura.evaluation.graph import to_frontend
from aura.evaluation.report import build_pdf_report
from aura.models import Evaluation
from aura.plans import STARTUP_QUOTAS

router = APIRouter(prefix="/api", tags=["evaluations"])


def evaluation_out(evaluation: Evaluation, *, redacted: bool = False) -> dict[str, Any]:
    return {
        "id": evaluation.id,
        "version": evaluation.version,
        "status": evaluation.status,
        "stage": evaluation.stage,
        "error": evaluation.error,
        "visibility": evaluation.visibility,
        "job_id": evaluation.job_id,
        "source": evaluation.source,
        "created_at": clock.iso(evaluation.created_at),
        "completed_at": clock.iso(evaluation.completed_at) if evaluation.completed_at else None,
        "report": to_frontend(evaluation.result, redacted=redacted) if evaluation.result else None,
    }


@router.post("/startups/{startup_id}/evaluations", status_code=202)
async def run_evaluation(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    if not is_owner(viewer, startup):
        raise NotFound("Startup not found")
    with read_session() as s:
        running = s.scalar(select(Evaluation.id).where(Evaluation.startup_id == startup.id,
                                                       Evaluation.status.in_(("queued", "running"))))
    if running:
        raise AppError("An evaluation is already running", code="EVALUATION_RUNNING", status=409, evaluation_id=running)
    if not viewer.is_admin:
        with write_tx() as s:
            quotas.consume(s, viewer.user_id, "evaluation", STARTUP_QUOTAS["evaluation"])
    evaluation_id, job_id = service.start_evaluation(startup.id, owner_user_id=viewer.user_id)
    return {"evaluation_id": evaluation_id, "job_id": job_id, "events_url": f"/api/jobs/{job_id}/events"}


@router.get("/startups/{startup_id}/evaluation")
def latest_evaluation(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    owner = is_owner(viewer, startup)
    evaluation = service.latest(startup.id, published_only=not owner)
    if evaluation is None:
        raise NotFound("No evaluation yet")
    return evaluation_out(evaluation, redacted=not owner and not viewer.has("full_report"))


@router.get("/startups/{startup_id}/evaluations")
def list_evaluations(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    if not is_owner(viewer, startup):
        raise NotFound("Startup not found")
    with read_session() as s:
        rows = s.scalars(select(Evaluation).where(Evaluation.startup_id == startup.id)
                         .order_by(Evaluation.version.desc())).all()
    return {"items": [evaluation_out(e) | {"report": None} for e in rows]}


@router.post("/startups/{startup_id}/evaluations/{evaluation_id}/publish")
def publish_evaluation(startup_id: str, evaluation_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    if not is_owner(viewer, startup):
        raise NotFound("Startup not found")
    try:
        if not service.publish(evaluation_id, startup.id):
            raise NotFound("Evaluation not found")
    except ValueError as exc:
        raise AppError(str(exc), code="EVALUATION_NOT_COMPLETE", status=409) from exc
    return {"published": evaluation_id}


@router.post("/startups/{startup_id}/evaluations/{evaluation_id}/cancel")
async def cancel_evaluation(startup_id: str, evaluation_id: str,
                            viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    if not is_owner(viewer, startup):
        raise NotFound("Startup not found")
    if not service.cancel(evaluation_id, startup.id):
        raise AppError("This evaluation is not running", code="EVALUATION_NOT_RUNNING", status=409)
    return {"cancelled": evaluation_id}


@router.get("/startups/{startup_id}/report.pdf")
async def report_pdf(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> Response:
    startup = visible_startup(viewer, startup_id)
    owner = is_owner(viewer, startup)
    if not owner:
        require_feature(viewer, "pdf_reports")
    evaluation = service.latest(startup.id, published_only=not owner)
    if evaluation is None or evaluation.status != "complete" or not evaluation.result:
        raise AppError("There is no completed evaluation to export", code="NO_EVALUATION", status=409)
    pdf = await asyncio.to_thread(build_pdf_report, service.legacy_record(startup), evaluation.result)
    filename = f"AURA3_{startup.slug}_evaluation_v{evaluation.version}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
