"""Evaluation routes: run with progress, one at a time, cancel, publish, plan-based redaction, PDF export."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

from aura.core.db import read_session, write_tx
from aura.core.jobs import cancel, start_job
from aura.evaluation import service
from aura.evaluation.evidence import normalise_financials
from aura.evaluation.graph import SCORE_DIMENSIONS, SECTION_TITLES
from aura.models import Document, Evaluation, Job, Startup, User
from tests.conftest import register


def fake_analysis(score: float = 6.8, label: str = "Buy") -> dict:
    return {
        "overall_score": score, "recommendation_label": label,
        "category_scores": dict.fromkeys(SCORE_DIMENSIONS, score), "score_rationales": {}, "score_spread": {},
        "rubric_version": "r1", **normalise_financials({}, []),
        "sections": {key: f"{title} for the test." for key, title in SECTION_TITLES.items()},
        "citations": {}, "citations_removed": 0, "sources": [], "rewrites": 0, "compliance_flags": [],
        "generated_at": "2026-10-26T00:00:00Z", "model": "fake",
    }


async def finishes(context, *, research, progress):
    progress("scoring", 60, "Scoring the rubric")
    return fake_analysis()


async def never_finishes(context, *, research, progress):
    await asyncio.Event().wait()


def wait_for_job(client, job_id: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def founder(client) -> str:
    register(client, role="startup", startup_name="Test Agritech")
    return client.get("/api/me").json()["startup"]["id"]


def test_run_publish_and_read_by_plan(client):
    startup_id = founder(client)
    base = f"/api/startups/{startup_id}"
    assert client.get(f"{base}/report.pdf").json()["error"]["code"] == "NO_EVALUATION"
    with patch("aura.evaluation.service.run_evaluation", finishes):
        started = client.post(f"{base}/evaluations")
        assert started.status_code == 202
        job = wait_for_job(client, started.json()["job_id"])
    assert job["status"] == "done" and job["result"]["score"] == 6.8
    own = client.get(f"{base}/evaluation").json()
    assert own["status"] == "complete" and own["visibility"] == "private"
    assert own["report"]["recommendationLabel"] == "Buy" and not own["report"]["redacted"]

    with write_tx() as s:
        s.add(Document(startup_id=startup_id, filename="deck.pdf", mime="application/pdf", size_bytes=1,
                       sha256="0" * 64, storage_dir="x", status="ready"))
    with patch("aura.publishing.profiles.index_startup", AsyncMock()) as index:
        published = client.post(f"{base}/publish")
    index.assert_awaited_once_with(startup_id)
    assert published.status_code == 200, published.text
    assert published.json()["ai_score"] == 6.8 and published.json()["recommendation"] == "Buy"

    register(client, plan="scout")
    scout = client.get(f"{base}/evaluation").json()["report"]
    assert scout["redacted"] and scout["score"] == 6.8 and "marketAnalysis" not in scout
    assert client.get(f"{base}/report.pdf").json()["error"]["code"] == "PLAN_REQUIRED"
    assert client.post(f"{base}/evaluations").status_code == 404  # only the owner runs evaluations

    register(client, plan="angel")
    angel = client.get(f"{base}/evaluation").json()["report"]
    assert not angel["redacted"] and angel["marketAnalysis"]
    pdf = client.get(f"{base}/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_one_evaluation_at_a_time_and_cancel(client):
    startup_id = founder(client)
    base = f"/api/startups/{startup_id}"
    with patch("aura.evaluation.service.run_evaluation", never_finishes):
        first = client.post(f"{base}/evaluations").json()
        again = client.post(f"{base}/evaluations")
        assert again.status_code == 409 and again.json()["error"]["code"] == "EVALUATION_RUNNING"
        assert client.post(f"{base}/evaluations/{first['evaluation_id']}/cancel").status_code == 200
        assert wait_for_job(client, first["job_id"])["status"] == "cancelled"
    row = client.get(f"{base}/evaluations").json()["items"][0]
    assert row["status"] == "failed" and row["error"] == "Cancelled"
    repeat = client.post(f"{base}/evaluations/{first['evaluation_id']}/cancel")
    assert repeat.json()["error"]["code"] == "EVALUATION_NOT_RUNNING"
    with patch("aura.evaluation.service.run_evaluation", finishes):
        second = client.post(f"{base}/evaluations").json()
        assert wait_for_job(client, second["job_id"])["status"] == "done"


def test_a_founder_cannot_publish_another_startups_evaluation(client):
    victim_id = founder(client)
    with patch("aura.evaluation.service.run_evaluation", finishes):
        job_id = client.post(f"/api/startups/{victim_id}/evaluations").json()["job_id"]
        wait_for_job(client, job_id)
    evaluation_id = client.get(f"/api/startups/{victim_id}/evaluation").json()["id"]

    attacker_id = founder(client)
    response = client.post(f"/api/startups/{attacker_id}/evaluations/{evaluation_id}/publish")
    assert response.status_code == 404
    with read_session() as s:
        assert s.get(Evaluation, evaluation_id).visibility == "private"


def test_interrupted_evaluations_are_failed_on_restart(app_env):
    with write_tx() as s:
        user = User(email="f@x.test", password_hash="x", role="startup", name="F")
        s.add(user)
        s.flush()
        startup = Startup(owner_user_id=user.id, slug="x", name="X", status="draft")
        s.add(startup)
        s.flush()
        s.add(Evaluation(startup_id=startup.id, version=1, status="running"))
    assert service.fail_orphaned_evaluations() == 1
    with read_session() as s:
        assert s.query(Evaluation).one().status == "failed"


async def test_a_job_cancelled_before_it_starts_is_recorded(app_env):
    async def never(ctx):
        await asyncio.Event().wait()

    job_id = start_job("echo", never)
    assert cancel(job_id)
    await asyncio.sleep(0.05)
    with read_session() as s:
        assert s.get(Job, job_id).status == "cancelled"
