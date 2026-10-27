"""Copilot threads and runs.

A message starts a run: a background job whose events (tokens, tool cards, the final message) stream over
the job's SSE endpoint. The run persists the assistant's turn when it finishes, is cancelled, or fails, so
the thread always shows what happened. Earlier turns are replayed to the model as plain text (the last
MAX_HISTORY messages), and passages cited in them stay citable.
"""

import asyncio
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import delete, func, select

from aura import quotas
from aura.agent.graph import Turn, finalize, run_turn
from aura.agent.tools import Ctx
from aura.api.deps import Viewer
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.errors import AppError, NotFound
from aura.core.events import bus
from aura.core.jobs import JobContext, start_job, stream_key
from aura.models import CopilotMessage, CopilotThread, Job, Startup

logger = logging.getLogger("aura.copilot")

MAX_HISTORY = 12
MAX_HISTORY_CHARS = 12000


def thread_out(thread: CopilotThread) -> dict[str, Any]:
    return {"id": thread.id, "title": thread.title, "startup_id": thread.startup_id,
            "created_at": clock.iso(thread.created_at),
            "updated_at": clock.iso(thread.updated_at) if thread.updated_at else clock.iso(thread.created_at)}


def message_out(message: CopilotMessage) -> dict[str, Any]:
    return {"id": message.id, "seq": message.seq, "role": message.role, "content": message.content,
            "parts": message.parts, "citations": message.citations, "status": message.status,
            "run_id": message.run_id, "created_at": clock.iso(message.created_at)}


def own_thread(viewer: Viewer, thread_id: str) -> CopilotThread:
    with read_session() as s:
        thread = s.get(CopilotThread, thread_id)
    if thread is None or thread.user_id != viewer.user_id:
        raise NotFound("Conversation not found")
    return thread


def create_thread(viewer: Viewer, *, title: str | None = None, startup_id: str | None = None) -> CopilotThread:
    with write_tx() as s:
        thread = CopilotThread(user_id=viewer.user_id, title=(title or "New chat")[:120], startup_id=startup_id,
                               updated_at=clock.now())
        s.add(thread)
        s.flush()
        s.expunge(thread)
        return thread


def active_run(thread_id: str) -> str | None:
    with read_session() as s:
        return s.scalar(select(Job.id).where(Job.kind == "copilot", Job.subject_id == thread_id,
                                             Job.status.in_(("queued", "running"))))


def _next_seq(s: Any, thread_id: str) -> int:
    return (s.scalar(select(func.max(CopilotMessage.seq)).where(CopilotMessage.thread_id == thread_id)) or 0) + 1


def _history(thread_id: str, before_seq: int) -> tuple[list[BaseMessage], dict[str, Any]]:
    """Recent turns as plain text, plus the deck passages they cited (still valid to cite)."""
    with read_session() as s:
        rows = s.scalars(select(CopilotMessage).where(CopilotMessage.thread_id == thread_id, CopilotMessage.seq < before_seq)
                         .order_by(CopilotMessage.seq.desc()).limit(MAX_HISTORY)).all()
    history: list[BaseMessage] = []
    cited: dict[str, Any] = {}
    budget = MAX_HISTORY_CHARS
    for m in rows:  # newest first, so the budget keeps the most recent turns
        text = re.sub(r"\s?\[w:\d+\]", "", m.content)[:4000]  # web numbers are per run
        if m.role == "assistant":
            tools = [f"{p['name']}({', '.join(f'{k}={v}' for k, v in (p.get('args') or {}).items())})"
                     for p in m.parts if p.get("type") == "tool"]
            if tools:
                text += f"\n\n(tools used: {'; '.join(tools)[:500]})"
            cited |= {k: v for k, v in (m.citations or {}).items() if k.startswith("c:")}
        budget -= len(text)
        if budget < 0:
            break
        history.append(HumanMessage(content=text) if m.role == "user" else AIMessage(content=text))
    return list(reversed(history)), cited


def post_message(viewer: Viewer, thread: CopilotThread, content: str) -> dict[str, Any]:
    if active_run(thread.id):
        raise AppError("The copilot is still answering in this conversation", code="RUN_ACTIVE", status=409)
    with write_tx() as s:
        if not viewer.is_admin:
            quotas.consume(s, viewer.user_id, "copilot", viewer.quota_limits.get("copilot"))
        seq = _next_seq(s, thread.id)
        message = CopilotMessage(thread_id=thread.id, seq=seq, role="user", content=content)
        s.add(message)
        row = s.get(CopilotThread, thread.id)
        if row.title == "New chat":
            row.title = (content.strip().splitlines() or ["New chat"])[0][:80]
        row.updated_at = clock.now()
        s.flush()
        user_message = message_out(message)
    job_id = start_job("copilot", lambda ctx: _run(ctx, viewer, thread.id, seq, content), owner_user_id=viewer.user_id,
                       subject_type="copilot_thread", subject_id=thread.id)
    with write_tx() as s:
        s.get(CopilotMessage, user_message["id"]).run_id = job_id
    return {"run_id": job_id, "message": user_message | {"run_id": job_id}}


def _save_answer(thread_id: str, run_id: str, parts: list[dict[str, Any]], citations: dict[str, Any], status: str) -> str:
    content = "\n\n".join(p["text"] for p in parts if p["type"] == "text").strip()
    with write_tx() as s:
        message = CopilotMessage(thread_id=thread_id, seq=_next_seq(s, thread_id), role="assistant", content=content,
                                 parts=parts, citations=citations, run_id=run_id, status=status)
        s.add(message)
        s.get(CopilotThread, thread_id).updated_at = clock.now()
        s.flush()
        return message.id


async def _run(job: JobContext, viewer: Viewer, thread_id: str, user_seq: int, question: str) -> dict[str, Any]:
    history, cited = _history(thread_id, user_seq)
    ctx = Ctx(viewer=viewer)
    ctx.evidence.deck.update(cited)
    with read_session() as s:
        thread = s.get(CopilotThread, thread_id)
        focus = s.get(Startup, thread.startup_id) if thread.startup_id else None

    def emit(kind: str, data: dict[str, Any]) -> None:
        bus.publish(stream_key(job.job_id), kind, data)

    turn = Turn()
    emit("run_start", {"thread_id": thread_id})
    try:
        parts, citations = await run_turn(ctx, history, question, emit, focus=focus, turn=turn)
    except asyncio.CancelledError:
        parts, citations = finalize(ctx, turn)
        _save_answer(thread_id, job.job_id, parts + [{"type": "notice", "text": "Stopped."}], citations, "cancelled")
        raise
    except Exception as exc:
        logger.exception("copilot run failed")
        parts, citations = finalize(ctx, turn)
        notice = "The copilot could not finish this answer (the AI gateway did not respond). Please try again." \
            if "connection" in str(exc).lower() or isinstance(exc, TimeoutError) else f"The copilot hit an error: {exc}"
        _save_answer(thread_id, job.job_id, parts + [{"type": "notice", "text": notice}], citations, "failed")
        raise
    message_id = _save_answer(thread_id, job.job_id, parts, citations, "done")
    emit("message", {"id": message_id, "parts": parts, "citations": citations})
    return {"message_id": message_id}


def delete_thread(viewer: Viewer, thread_id: str) -> None:
    own_thread(viewer, thread_id)
    with write_tx() as s:
        s.execute(delete(CopilotThread).where(CopilotThread.id == thread_id))
