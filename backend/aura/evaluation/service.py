"""Evaluation jobs: create a versioned evaluation, run it with live progress, and record the result."""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update

from aura.core import clock, jobs
from aura.core.db import read_session, write_tx
from aura.core.jobs import JobContext, start_job
from aura.core.llm import model_name
from aura.evaluation import scoring
from aura.evaluation.context import StartupContext, load_context
from aura.evaluation.evidence import EVIDENCE_VERSION
from aura.evaluation.graph import run_evaluation
from aura.evaluation.research import Mode, ResearchProvider
from aura.models import Evaluation, Startup

logger = logging.getLogger("aura.evaluation")


def input_hash(context: StartupContext) -> str:
    """Identifies what an evaluation read: profile, documents, rubric and model."""
    material = "\n".join([context.profile_block(), *(c["text"] for c in context.chunks),
                          scoring.rubric()["version"], model_name("agent")])
    return hashlib.sha256(material.encode()).hexdigest()


def create_evaluation(startup_id: str, *, visibility: str = "private", source: str = "live") -> str:
    with write_tx() as s:
        version = (s.scalar(select(func.max(Evaluation.version)).where(Evaluation.startup_id == startup_id)) or 0) + 1
        evaluation = Evaluation(startup_id=startup_id, version=version, status="queued", visibility=visibility,
                                source=source)
        s.add(evaluation)
        s.flush()
        return evaluation.id


def record_result(evaluation_id: str, analysis: dict[str, Any], *, source: str = "live") -> None:
    """Store a finished analysis; published evaluations become the startup's headline score."""
    with write_tx() as s:
        evaluation = s.get(Evaluation, evaluation_id)
        evaluation.status = "complete"
        evaluation.stage = "Report ready"
        evaluation.result = analysis
        score = analysis.get("overall_score")
        evaluation.overall_score_x10 = round(score * 10) if score is not None else None
        evaluation.recommendation = analysis.get("recommendation_label")
        evaluation.evidence_version = analysis.get("evidence_version", EVIDENCE_VERSION)
        evaluation.rubric_version = analysis.get("rubric_version")
        evaluation.model = analysis.get("model")
        evaluation.input_hash = analysis.get("input_hash")
        evaluation.source = source
        evaluation.completed_at = clock.now()
        evaluation.error = None
        if evaluation.visibility == "published":
            _promote(s, evaluation)


def _promote(s: Any, evaluation: Evaluation) -> None:
    startup = s.get(Startup, evaluation.startup_id)
    startup.latest_evaluation_id = evaluation.id
    startup.ai_score_x10 = evaluation.overall_score_x10
    startup.recommendation = evaluation.recommendation
    startup.updated_at = clock.now()


def publish(evaluation_id: str, startup_id: str) -> bool:
    """Publish one of this startup's complete evaluations. Returns False when it is not this startup's."""
    with write_tx() as s:
        evaluation = s.get(Evaluation, evaluation_id)
        if evaluation is None or evaluation.startup_id != startup_id:
            return False
        if evaluation.status != "complete":
            raise ValueError("only a complete evaluation can be published")
        evaluation.visibility = "published"
        _promote(s, evaluation)
        return True


def cancel(evaluation_id: str, startup_id: str) -> bool:
    """Stop a queued or running evaluation of this startup (call from the event loop). False if not active."""
    with read_session() as s:
        evaluation = s.get(Evaluation, evaluation_id)
        if evaluation is None or evaluation.startup_id != startup_id or evaluation.status not in ("queued", "running"):
            return False
        job_id = evaluation.job_id
    if job_id:
        jobs.cancel(job_id)
    with write_tx() as s:  # a job cancelled before it started never reaches _run's handler
        s.execute(update(Evaluation).where(Evaluation.id == evaluation_id, Evaluation.status.in_(("queued", "running")))
                  .values(status="failed", error="Cancelled"))
    return True


async def _run(ctx: JobContext, evaluation_id: str, research: ResearchProvider) -> dict[str, Any]:
    with read_session() as s:
        evaluation = s.get(Evaluation, evaluation_id)
        startup_id = evaluation.startup_id
    with write_tx() as s:
        row = s.get(Evaluation, evaluation_id)
        row.status = "running"
        row.job_id = ctx.job_id

    def progress(stage: str, pct: int, message: str) -> None:
        ctx.progress(stage, pct, message)

    try:
        context = load_context(startup_id)
        analysis = await run_evaluation(context, research=research, progress=progress)
        analysis["input_hash"] = input_hash(context)
    except BaseException as exc:  # includes cancellation: a row left "running" would block every later run
        with write_tx() as s:
            row = s.get(Evaluation, evaluation_id)
            row.status = "failed"
            row.error = "Cancelled" if isinstance(exc, asyncio.CancelledError) else str(exc)[:2000]
        raise
    record_result(evaluation_id, analysis)
    return {"evaluation_id": evaluation_id, "score": analysis["overall_score"],
            "label": analysis["recommendation_label"], "sources": len(analysis.get("sources", []))}


def start_evaluation(startup_id: str, *, owner_user_id: str | None, visibility: str = "private",
                     research_mode: Mode = "live", cassette: Path | None = None) -> tuple[str, str]:
    evaluation_id = create_evaluation(startup_id, visibility=visibility)
    research = ResearchProvider(research_mode, cassette)
    job_id = start_job("evaluation", lambda ctx: _run(ctx, evaluation_id, research), owner_user_id=owner_user_id,
                       subject_type="evaluation", subject_id=evaluation_id, payload={"startup_id": startup_id})
    with write_tx() as s:
        s.get(Evaluation, evaluation_id).job_id = job_id
    return evaluation_id, job_id


def fail_orphaned_evaluations() -> int:
    """Evaluations queued or running in a previous process will never finish; mark them failed."""
    with write_tx() as s:
        result = s.execute(
            update(Evaluation)
            .where(Evaluation.status.in_(("queued", "running")))
            .values(status="failed", error="The server restarted while this evaluation was running")
        )
        return result.rowcount or 0


def latest(startup_id: str, *, published_only: bool) -> Evaluation | None:
    with read_session() as s:
        query = select(Evaluation).where(Evaluation.startup_id == startup_id)
        if published_only:
            query = query.where(Evaluation.visibility == "published", Evaluation.status == "complete")
        return s.scalars(query.order_by(Evaluation.version.desc()).limit(1)).first()


def legacy_record(startup: Startup) -> dict[str, Any]:
    """The startup as the PDF renderer reads it."""
    profile = startup.profile or {}
    team = "; ".join(f"{m.get('name')} ({m.get('role')})" for m in profile.get("team", [])) or "Not provided"
    return {
        "startup_id": startup.id,
        "name": startup.name,
        "domain": startup.domain,
        "stage": {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B+"}.get(
            startup.stage, startup.stage),
        "description": startup.description or startup.one_liner,
        "team": team,
        "funding_required": f"Rs {startup.ask_inr / 1e7:g} crore" if startup.ask_inr else None,
        "verification": startup.mca or {},
        "compliance_flags": startup.compliance_flags or [],
    }
