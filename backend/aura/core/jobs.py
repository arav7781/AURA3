"""Background jobs (ingestion, evaluation, seeding) with durable status and live progress.

``start_job`` records a Job row and runs ``fn(ctx)`` as an asyncio task. ``ctx.progress`` updates the row
(throttled) and publishes ``job_progress`` on the event bus stream ``job:{id}``; completion publishes
``job_done`` or ``job_error`` and closes the stream. Jobs left running by a restart are marked failed.
"""

import asyncio
import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import update

from aura.core import clock
from aura.core.db import write_tx
from aura.core.events import bus
from aura.models import Job

logger = logging.getLogger("aura.jobs")

JobFn = Callable[["JobContext"], Awaitable[dict[str, Any] | None]]
_tasks: dict[str, asyncio.Task[None]] = {}
_limits: dict[str, asyncio.Semaphore] = {}
LIMITS = {"ingest": 2, "evaluation": 2, "seed": 1, "copilot": 6}


def stream_key(job_id: str) -> str:
    return f"job:{job_id}"


class JobContext:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._last_write = 0.0
        self._pct = 0

    def progress(self, stage: str, pct: int | None = None, message: str | None = None, **extra: Any) -> None:
        """Report progress. Safe to call from worker threads."""
        data: dict[str, Any] = {"stage": stage, **extra}
        if pct is not None:  # never moves backwards, even when a stage repeats (e.g. a research retry)
            self._pct = data["pct"] = max(self._pct, min(100, int(pct)))
        if message:
            data["message"] = message
        bus.publish(stream_key(self.job_id), "job_progress", data)
        now = time.monotonic()
        if now - self._last_write > 0.5 or pct in (0, 100):
            self._last_write = now
            values: dict[str, Any] = {"stage": stage[:120]}
            if pct is not None:
                values["progress"] = data["pct"]
            with write_tx() as s:
                s.execute(update(Job).where(Job.id == self.job_id).values(**values))

    def log(self, message: str, **extra: Any) -> None:
        bus.publish(stream_key(self.job_id), "log", {"message": message, **extra})


def start_job(
    kind: str,
    fn: JobFn,
    *,
    owner_user_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    with write_tx() as s:
        job = Job(
            kind=kind,
            status="queued",
            owner_user_id=owner_user_id,
            subject_type=subject_type,
            subject_id=subject_id,
            payload=payload or {},
        )
        s.add(job)
        s.flush()
        job_id = job.id
    bus.publish(stream_key(job_id), "job_queued", {"kind": kind, "subject_type": subject_type, "subject_id": subject_id})
    task = asyncio.get_running_loop().create_task(_run(job_id, kind, fn))
    _tasks[job_id] = task
    task.add_done_callback(lambda t: _on_done(job_id, t))
    return job_id


def _on_done(job_id: str, task: asyncio.Task) -> None:
    _tasks.pop(job_id, None)
    if task.cancelled():  # a task cancelled before its first step never ran _run's handler
        with write_tx() as s:
            s.execute(update(Job).where(Job.id == job_id, Job.status.in_(("queued", "running")))
                      .values(status="cancelled", error="cancelled", finished_at=clock.now()))
        bus.publish(stream_key(job_id), "job_error", {"message": "cancelled"})
        bus.close(stream_key(job_id))


async def _run(job_id: str, kind: str, fn: JobFn) -> None:
    semaphore = _limits.setdefault(kind, asyncio.Semaphore(LIMITS.get(kind, 2)))
    ctx = JobContext(job_id)
    try:
        async with semaphore:  # a job cancelled while still queued here is recorded as cancelled too
            with write_tx() as s:
                s.execute(update(Job).where(Job.id == job_id).values(status="running", started_at=clock.now()))
            bus.publish(stream_key(job_id), "job_started", {})
            result = await fn(ctx)
    except asyncio.CancelledError:
        _finish(job_id, "cancelled", error="cancelled")
        bus.publish(stream_key(job_id), "job_error", {"message": "cancelled"})
        raise
    except Exception as exc:  # noqa: BLE001 — every failure is reported on the job
        logger.error("job %s (%s) failed: %s\n%s", job_id, kind, exc, traceback.format_exc())
        message = str(exc) or exc.__class__.__name__
        _finish(job_id, "failed", error=message[:2000])
        bus.publish(stream_key(job_id), "job_error", {"message": message[:500]})
    else:
        _finish(job_id, "done", result=result or {})
        bus.publish(stream_key(job_id), "job_done", {"result": result or {}})
    finally:
        bus.close(stream_key(job_id))


def _finish(job_id: str, status: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    values: dict[str, Any] = {"status": status, "finished_at": clock.now(), "error": error}
    if status == "done":
        values["progress"] = 100
        values["result"] = result
    with write_tx() as s:
        s.execute(update(Job).where(Job.id == job_id).values(**values))


def cancel(job_id: str) -> bool:
    """Cancel a queued or running job. Call from the event loop thread (task.cancel is not thread-safe)."""
    task = _tasks.get(job_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def fail_orphaned_jobs() -> int:
    """Jobs still queued or running from a previous process will never finish; mark them failed."""
    with write_tx() as s:
        result = s.execute(
            update(Job)
            .where(Job.status.in_(("queued", "running")))
            .values(status="failed", error="The server restarted while this job was running", finished_at=clock.now())
        )
        return result.rowcount or 0
