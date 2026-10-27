"""Check the seeded demo end to end. Exit code 1 if any hard check fails.

    uv run python -m seed.verify

Hard checks: every deck ingested with chunks in both the database and Qdrant, scanned decks really have no
text layer, registry and injection flags match the specs, demo logins work, and the ledger audit passes.
Evaluation scores are compared with each spec's expected band and reported, not enforced: they are what
the evals measure.
"""

import asyncio
import sys
from pathlib import Path

from qdrant_client import models
from sqlalchemy import func, select

from aura.core import db
from aura.core.db import read_session
from aura.core.security import verify_password
from aura.decks.spec import load_specs
from aura.ledger.audit import run_audit
from aura.models import AppState, Chunk, Document, DocumentPage, Evaluation, Ranking, Review, Startup, User
from aura.rag import store

SPECS = Path(__file__).parent / "specs"


async def _points(document_id: str) -> int:
    """Vectors of one document (a startup may also have private drafts from copilot conversations)."""
    result = await store.client().count(store.names.chunks, exact=True, count_filter=models.Filter(
        must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=document_id))]))
    return result.count


async def _profiles() -> int:
    return (await store.client().count(store.names.startups, exact=True)).count


async def verify() -> int:
    if db._rw is None:  # run on its own
        db.init_engines()
    import json

    import pdfplumber

    from aura.ingest.storage import document_dir
    from seed.run import DEMO_PASSWORD

    failures: list[str] = []
    notes: list[str] = []
    specs = load_specs(SPECS)
    in_band = 0
    with read_session() as s:
        for spec in specs:
            startup = s.scalar(select(Startup).where(Startup.slug == spec.slug))
            if startup is None:
                failures.append(f"{spec.slug}: startup missing")
                continue
            docs = s.scalars(select(Document).where(Document.startup_id == startup.id, Document.kind == "deck")).all()
            ready = [d for d in docs if d.status == "ready"]
            if len(ready) != 1 or len(docs) != 1:
                failures.append(f"{spec.slug}: expected one ready deck, found {[d.status for d in docs]}")
                continue
            doc = ready[0]
            chunks = s.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)) or 0
            points = await _points(doc.id)
            if chunks == 0 or chunks != points:
                failures.append(f"{spec.slug}: {chunks} chunks in the database, {points} in Qdrant")
            if doc.page_count != 11:
                failures.append(f"{spec.slug}: {doc.page_count} pages, expected 11")
            if spec.deck.render == "scanned":
                with pdfplumber.open(document_dir(doc.id) / "source.pdf") as pdf:
                    if any(page.chars for page in pdf.pages):
                        failures.append(f"{spec.slug}: scanned deck has a text layer")
                ocr_pages = s.scalar(select(func.count()).select_from(DocumentPage).where(
                    DocumentPage.document_id == doc.id, DocumentPage.origin != "digital")) or 0
                if ocr_pages == 0:
                    failures.append(f"{spec.slug}: scanned deck was not OCR'd")
            for flag in spec.evaluation_expectations.must_flag:
                if flag not in startup.compliance_flags:
                    failures.append(f"{spec.slug}: missing flag {flag} (has {startup.compliance_flags})")
            unexpected = set(startup.compliance_flags) - set(spec.evaluation_expectations.must_flag) - {
                "OCR_REVIEW_REQUIRED", "OCR_PARTIAL", "SANDBOX_REGISTRY"}
            if unexpected:
                failures.append(f"{spec.slug}: unexpected flags {sorted(unexpected)}")

            if startup.status != "published" or startup.latest_evaluation_id is None:
                notes.append(f"{spec.slug}: not published (no evaluation yet)")
                continue
            evaluation = s.get(Evaluation, startup.latest_evaluation_id)
            score = evaluation.overall_score_x10 / 10 if evaluation.overall_score_x10 is not None else None
            low, high = spec.evaluation_expectations.score_band
            labels = spec.evaluation_expectations.recommendation_in
            ok = score is not None and low <= score <= high and evaluation.recommendation in labels
            in_band += ok
            if not ok:
                notes.append(f"{spec.slug}: {score} {evaluation.recommendation} (expected {low}-{high}, {labels})")

        users = {u.email: u for u in s.scalars(select(User))}
        row = s.get(AppState, "demo_accounts")
        accounts = json.loads(row.value)["accounts"] if row else []
        if len(accounts) != 31:
            failures.append(f"demo accounts: {len(accounts)}, expected 31")
        for account in accounts:
            user = users.get(account["email"])
            if user is None or not verify_password(user.password_hash, DEMO_PASSWORD):
                failures.append(f"demo login fails for {account['email']}")
        reviews = s.scalar(select(func.count()).select_from(Review)) or 0
        rankers = s.scalar(select(func.count(func.distinct(Ranking.investor_id)))) or 0
        if reviews < 50 or rankers < 6:
            failures.append(f"community: {reviews} reviews, {rankers} ranking lists")
        published = s.scalar(select(func.count()).select_from(Startup).where(Startup.status == "published")) or 0
        audit = {name: problems for name, problems in run_audit(s).items() if problems}
        if audit:
            failures.append(f"ledger audit: {audit}")
    profile_points = await _profiles()
    if profile_points < published:
        failures.append(f"startup profiles: {profile_points} vectors for {published} published startups")

    print(f"verify: {len(specs)} specs, {published} published, {reviews} reviews, {rankers} ranking lists, "
          f"{in_band} evaluations within their expected band")
    for note in notes:
        print(f"  note  {note}")
    for failure in failures:
        print(f"  FAIL  {failure}")
    print("verify: OK" if not failures else f"verify: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(verify()))
