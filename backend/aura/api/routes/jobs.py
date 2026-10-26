from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from aura.api.deps import Viewer, current_viewer
from aura.api.sse import event_stream
from aura.core import clock
from aura.core.db import read_session
from aura.core.errors import NotFound
from aura.core.jobs import stream_key
from aura.models import Job

router = APIRouter(prefix="/api", tags=["jobs"])


def job_out(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "subject_type": job.subject_type,
        "subject_id": job.subject_id,
        "result": job.result,
        "error": job.error,
        "created_at": clock.iso(job.created_at),
        "finished_at": clock.iso(job.finished_at) if job.finished_at else None,
    }


def _visible_job(job_id: str, viewer: Viewer) -> Job:
    with read_session() as s:
        job = s.get(Job, job_id)
    # Other users' jobs are reported as missing rather than forbidden.
    if job is None or (job.owner_user_id != viewer.user_id and not viewer.is_admin):
        raise NotFound("Job not found")
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    return job_out(_visible_job(job_id, viewer))


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, request: Request, viewer: Viewer = Depends(current_viewer)) -> StreamingResponse:
    job = _visible_job(job_id, viewer)
    return event_stream(request, stream_key(job.id), {"job_id": job.id})


@router.get("/me/jobs")
def my_jobs(viewer: Viewer = Depends(current_viewer), limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    with read_session() as s:
        jobs = s.scalars(
            select(Job).where(Job.owner_user_id == viewer.user_id).order_by(Job.created_at.desc()).limit(limit)
        ).all()
    return {"items": [job_out(j) for j in jobs]}
