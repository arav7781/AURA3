"""The copilot: private conversations, runs streamed over the job's SSE endpoint, cancel.

    POST /api/copilot/threads/{id}/messages   → {run_id}; then GET /api/jobs/{run_id}/events streams
        run_start · token · tool_start · tool_end · message · job_done | job_error
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from aura.access import visible_startup
from aura.agent import service
from aura.api.deps import Viewer, current_viewer
from aura.core.db import read_session
from aura.core.errors import AppError, NotFound
from aura.core.jobs import cancel
from aura.models import CopilotMessage, CopilotThread, Job

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


@router.get("/threads")
def list_threads(viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    with read_session() as s:
        threads = s.scalars(select(CopilotThread).where(CopilotThread.user_id == viewer.user_id)
                            .order_by(CopilotThread.updated_at.desc()).limit(100)).all()
    return {"items": [service.thread_out(t) for t in threads]}


class ThreadIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    startup: str | None = Field(default=None, max_length=120, description="slug or id of the startup this chat is about")


@router.post("/threads", status_code=201)
def create_thread(body: ThreadIn, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup_id = visible_startup(viewer, body.startup).id if body.startup else None
    return service.thread_out(service.create_thread(viewer, title=body.title, startup_id=startup_id))


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    thread = service.own_thread(viewer, thread_id)
    with read_session() as s:
        messages = s.scalars(select(CopilotMessage).where(CopilotMessage.thread_id == thread_id)
                             .order_by(CopilotMessage.seq)).all()
    return {"thread": service.thread_out(thread), "messages": [service.message_out(m) for m in messages],
            "active_run_id": service.active_run(thread_id)}


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str, viewer: Viewer = Depends(current_viewer)) -> None:
    service.delete_thread(viewer, thread_id)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


@router.post("/threads/{thread_id}/messages", status_code=202)
async def post_message(thread_id: str, body: MessageIn, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    thread = service.own_thread(viewer, thread_id)
    if not body.content.strip():
        raise AppError("Ask a question", code="EMPTY_MESSAGE", status=422)
    return service.post_message(viewer, thread, body.content.strip())


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    with read_session() as s:
        job = s.get(Job, run_id)
    if job is None or job.kind != "copilot" or job.owner_user_id != viewer.user_id:
        raise NotFound("Run not found")
    return {"cancelled": cancel(run_id)}
