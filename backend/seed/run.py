"""Seed the demo: 25 startups whose decks go through the real pipeline (TitanOCR, chunking, hybrid index),
AI evaluations, investors on every plan, reviews and rankings. Running it twice changes nothing.

    uv run python -m seed.run                 # committed caches only: no LLM calls when they are complete
    uv run python -m seed.run --allow-llm     # also evaluate startups missing from the cache, and save them
    uv run python -m seed.run --reset         # first wipe the database, documents and vector collections

Caches under seed/cache (committed): embeddings/<slug>.npz (deck and profile vectors), evaluations/<slug>.json
(the analysis and the input hash it was made from) and research/<slug>.json (the web results it read).
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select

from aura.api.routes.auth import RegisterIn, create_account
from aura.core import clock, db, migrate
from aura.core.config import get_settings
from aura.core.db import read_session, write_tx
from aura.core.embeddings import DenseEmbedder
from aura.core.errors import AppError
from aura.decks.build import build_deck, deck_filename
from aura.decks.spec import StartupSpec, load_specs
from aura.evaluation import mca, service
from aura.evaluation.context import load_context
from aura.evaluation.graph import run_evaluation
from aura.evaluation.research import ResearchProvider
from aura.ingest.ocr import ocr_service
from aura.ingest.pipeline import ingest_document
from aura.ingest.storage import document_dir
from aura.models import AppState, Chunk, Document, Evaluation, Ranking, Review, Startup, User
from aura.publishing import publish_startup
from aura.rag import profiles, projection, store

logger = logging.getLogger("seed")

SEED_DIR = Path(__file__).parent
SPECS = SEED_DIR / "specs"
CACHE = SEED_DIR / "cache"
DEMO_PASSWORD = "aura3-demo-2026"
ADMIN = {"email": "admin@aura3.demo", "name": "AURA3 Admin"}
INVESTORS = [
    {"email": "ananya@aura3.demo", "name": "Ananya Rao", "plan": "syndicate", "bias": 0.3,
     "headline": "Syndicate lead · climate and deeptech", "focus": ["Climate & Energy", "Deeptech & AI", "Agritech"]},
    {"email": "vikram@aura3.demo", "name": "Vikram Mehta", "plan": "syndicate", "bias": -0.2,
     "headline": "Syndicate lead · fintech and B2B SaaS", "focus": ["Fintech", "B2B SaaS", "Insurtech"]},
    {"email": "priya@aura3.demo", "name": "Priya Nair", "plan": "angel", "bias": 0.1,
     "headline": "Angel · healthtech and edtech", "focus": ["Healthtech", "Edtech", "Consumer & D2C"]},
    {"email": "rohan@aura3.demo", "name": "Rohan Gupta", "plan": "angel", "bias": 0.0,
     "headline": "Angel · logistics and agritech", "focus": ["Logistics & Mobility", "Agritech", "Proptech"]},
    {"email": "meera@aura3.demo", "name": "Meera Iyer", "plan": "angel", "bias": 0.2,
     "headline": "Angel · consumer and proptech", "focus": ["Consumer & D2C", "Proptech", "Cybersecurity"]},
    {"email": "arjun@aura3.demo", "name": "Arjun Singh", "plan": "scout", "bias": -0.1,
     "headline": "Scout · exploring agritech and edtech", "focus": ["Agritech", "Edtech", "Climate & Energy"]},
]


class Progress:
    """Stands in for a job context: ingestion and evaluations report progress through it."""

    job_id = "seed"

    def __init__(self, label: str) -> None:
        self.label = label

    def progress(self, stage: str, pct: int | None = None, message: str | None = None, **_: object) -> None:
        logger.debug("%s: %s %s %s", self.label, stage, pct, message or "")


# ── accounts ────────────────────────────────────────────────────────────────────────────────────────────

def ensure_account(email: str, name: str, role: str, *, plan: str = "scout", startup_name: str | None = None,
                   is_admin: bool = False) -> str:
    with write_tx() as s:
        existing = s.scalar(select(User.id).where(User.email == email))
        if existing:
            return existing
        body = RegisterIn(email=email, password=DEMO_PASSWORD, name=name, role=role, plan=plan,
                          startup_name=startup_name)
        return create_account(s, body, is_admin=is_admin).id


def seed_accounts(specs: list[StartupSpec]) -> dict[str, str]:
    users = {ADMIN["email"]: ensure_account(ADMIN["email"], ADMIN["name"], "investor", plan="syndicate", is_admin=True)}
    for investor in INVESTORS:
        users[investor["email"]] = ensure_account(investor["email"], investor["name"], "investor", plan=investor["plan"])
    for spec in specs:
        account = spec.founder_account
        users[account.email] = ensure_account(account.email, account.name, "startup", startup_name=spec.name)
    return users


# ── startups ────────────────────────────────────────────────────────────────────────────────────────────

def apply_profile(spec: StartupSpec, owner_id: str) -> str:
    with write_tx() as s:
        startup = s.scalar(select(Startup).where(Startup.owner_user_id == owner_id))
        if s.scalar(select(Startup.id).where(Startup.slug == spec.slug, Startup.id != startup.id)) is None:
            startup.slug = spec.slug
        verification = mca.verify(spec.mca.cin, legal_name=spec.legal_name,
                                  claimed_directors=[member.name for member in spec.team])
        flags = mca.consistency_flags(verification, legal_name=spec.legal_name)
        kept = [f for f in startup.compliance_flags if f in ("DECK_HIDDEN_INSTRUCTIONS", "OCR_REVIEW_REQUIRED", "OCR_PARTIAL")]
        values = {
            "name": spec.name, "legal_name": spec.legal_name, "domain": spec.domain, "sub_domain": spec.sub_domain,
            "stage": spec.stage, "one_liner": spec.one_liner, "description": spec.description,
            "hq_city": spec.hq.city, "hq_state": spec.hq.state, "founded_year": spec.founded_year,
            "ask_inr": spec.round.ask_inr, "pre_money_inr": spec.round.pre_money_inr,
            "cin": verification.get("cin") or spec.mca.cin, "mca_status": verification.get("company_status"),
            "compliance_flags": sorted({*kept, *flags}), "is_seed": True,
            "profile": {
                "team": [member.model_dump() for member in spec.team],
                "competitors": [c.model_dump() for c in spec.competitors],
                "gtm": spec.gtm.model_dump(),
                "round": spec.round.model_dump(),
                "traction_as_of": spec.traction.as_of,
            },
        }
        changed = any(getattr(startup, k) != v for k, v in values.items())
        stored = {k: v for k, v in (startup.mca or {}).items() if k != "last_checked"}
        if changed or stored != {k: v for k, v in verification.items() if k != "last_checked"}:
            for key, value in values.items():
                setattr(startup, key, value)
            startup.mca = verification
            startup.updated_at = clock.now()
        return startup.id


async def seed_deck(spec: StartupSpec, startup_id: str, owner_id: str) -> tuple[str, bool]:
    """Upload and ingest the spec's deck unless the same file is already ingested. Returns (doc id, ingested)."""
    files = build_deck(spec)
    with write_tx() as s:
        doc = s.scalar(select(Document).where(Document.startup_id == startup_id, Document.sha256 == files.sha256))
        stale = s.scalars(select(Document).where(Document.startup_id == startup_id, Document.kind == "deck",
                                                 Document.sha256 != files.sha256)).all()
        stale_ids = [d.id for d in stale]
        for old in stale:
            s.delete(old)
        if doc is None:
            doc = Document(startup_id=startup_id, uploaded_by=owner_id, kind="deck",
                           filename=deck_filename(spec, ".pdf"), mime="application/pdf", size_bytes=len(files.pdf),
                           sha256=files.sha256, storage_dir="", visibility="published")
            s.add(doc)
            s.flush()
            folder = document_dir(doc.id)
            doc.storage_dir = str(folder.relative_to(folder.parents[1]))
        doc_id, ready = doc.id, doc.status == "ready"
    for old_id in stale_ids:
        await store.delete_document(old_id)
        shutil.rmtree(document_dir(old_id), ignore_errors=True)
    folder = document_dir(doc_id)
    (folder / "source.pdf").write_bytes(files.pdf)
    (folder / "deck.pptx").write_bytes(files.pptx)
    (folder / "slides.json").write_text(json.dumps(files.slide_map, indent=1))
    if ready:
        return doc_id, False
    await ingest_document(Progress(spec.slug), doc_id, update_map=False)
    return doc_id, True


def embedding_cache_path(spec: StartupSpec) -> Path:
    return CACHE / "embeddings" / f"{spec.slug}.npz"


def prime_embeddings(spec: StartupSpec) -> int:
    path = embedding_cache_path(spec)
    if not path.exists():
        return 0
    data = np.load(path)
    DenseEmbedder().prime(dict(zip(data["keys"].tolist(), data["vectors"], strict=True)))
    return len(data["keys"])


def save_embeddings(spec: StartupSpec, startup_id: str) -> None:
    with read_session() as s:
        texts = [f"{c.ctx}\n\n{c.text}" for c in s.scalars(select(Chunk).where(Chunk.startup_id == startup_id))]
        texts.append(profiles.profile_text(s.get(Startup, startup_id)))
    vectors = DenseEmbedder().export(texts)
    keys = sorted(vectors)
    path = embedding_cache_path(spec)
    if path.exists() and sorted(np.load(path)["keys"].tolist()) == keys:
        return  # unchanged: leave the committed file alone (npz bytes differ on every write)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, keys=np.array(keys), vectors=np.stack([vectors[k] for k in keys]).astype(np.float32))


# ── evaluations ─────────────────────────────────────────────────────────────────────────────────────────

def evaluation_cache_path(spec: StartupSpec) -> Path:
    return CACHE / "evaluations" / f"{spec.slug}.json"


def has_complete_evaluation(startup_id: str) -> bool:
    with read_session() as s:
        return s.scalar(select(Evaluation.id).where(Evaluation.startup_id == startup_id,
                                                    Evaluation.status == "complete")) is not None


async def seed_evaluation(spec: StartupSpec, startup_id: str, *, allow_llm: bool) -> str:
    if has_complete_evaluation(startup_id):
        return "kept"
    context = load_context(startup_id)
    expected = service.input_hash(context)
    path = evaluation_cache_path(spec)
    if path.exists():
        cached = json.loads(path.read_text())
        if cached["input_hash"] != expected:
            logger.warning("%s: cached evaluation was made from different inputs; using it anyway "
                           "(re-run with --allow-llm after deleting %s to refresh)", spec.slug, path.name)
        evaluation_id = service.create_evaluation(startup_id, visibility="published", source="seed_cache")
        service.record_result(evaluation_id, cached["analysis"], source="seed_cache")
        return "cache"
    if not allow_llm:
        return "missing"
    research = ResearchProvider("record", CACHE / "research" / f"{spec.slug}.json")
    started = time.monotonic()
    analysis = await run_evaluation(context, research=research, progress=Progress(spec.slug).progress)
    if not analysis.get("sources"):
        # Web search was unreachable: a report without market research must not become the demo's cache.
        logger.warning("%s: no web sources were retrieved; not saving this evaluation (re-run later)", spec.slug)
        return "no_research"
    analysis["input_hash"] = expected
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"input_hash": expected, "analysis": analysis}, indent=1, sort_keys=True))
    evaluation_id = service.create_evaluation(startup_id, visibility="published", source="live")
    service.record_result(evaluation_id, analysis, source="live")
    logger.info("%s: evaluated live in %.0fs: %s (%s)", spec.slug, time.monotonic() - started,
                analysis["overall_score"], analysis["recommendation_label"])
    return "live"


# ── publishing, reviews, rankings ───────────────────────────────────────────────────────────────────────

async def publish(startup_id: str) -> bool:
    try:
        await publish_startup(startup_id)
    except AppError:  # no evaluation yet
        return False
    return True


def _rating(score: float | None, bias: float, rng: random.Random) -> int:
    base = 1 + 4 * (score if score is not None else 5.0) / 10
    return max(1, min(5, round(base + bias + rng.uniform(-0.6, 0.6))))


def seed_reviews_and_rankings(specs: list[StartupSpec], users: dict[str, str], startups: dict[str, str]) -> int:
    by_slug = {spec.slug: spec for spec in specs}
    added = 0
    with write_tx() as s:
        published = {st.slug: st for st in s.scalars(select(Startup).where(Startup.status == "published",
                                                                             Startup.is_seed.is_(True)))}
        evaluations = {e.startup_id: e for e in s.scalars(select(Evaluation).where(
            Evaluation.id.in_([st.latest_evaluation_id for st in published.values()])))}
        for investor in INVESTORS:
            investor_id = users[investor["email"]]
            rng = random.Random(int(hashlib.sha256(investor["email"].encode()).hexdigest()[:8], 16))
            in_focus = [slug for slug, st in sorted(published.items()) if st.domain in investor["focus"]]
            others = sorted(set(published) - set(in_focus), key=lambda slug: -(published[slug].ai_score_x10 or 0))
            chosen = (in_focus + others)[:10]
            scored: list[tuple[float, str]] = []
            for slug in chosen:
                startup, spec = published[slug], by_slug[slug]
                result = (evaluations.get(startup.id).result or {}) if startup.id in evaluations else {}
                scores = result.get("category_scores", {})
                ratings = {key: _rating(scores.get(key), investor["bias"], rng) for key in ("team", "market", "product", "traction")}
                scored.append((sum(ratings.values()) / 4 + rng.uniform(0, 0.01), slug))
                if s.scalar(select(Review.id).where(Review.startup_id == startup.id, Review.investor_id == investor_id)):
                    continue
                strength = spec.traction.highlights[0]
                concern = spec.risks[rng.randrange(len(spec.risks))]
                note = f"Liked: {strength}. Watching: {concern.rstrip('.')}."
                if startup.compliance_flags:
                    note += f" Registry/compliance flags to clear first: {', '.join(startup.compliance_flags)}."
                s.add(Review(startup_id=startup.id, investor_id=investor_id, note=note[:2000], **ratings))
                added += 1
            wanted = [published[slug].id for _, slug in sorted(scored, reverse=True)[:10]]
            current = s.scalars(select(Ranking.startup_id).where(Ranking.investor_id == investor_id)
                                .order_by(Ranking.position)).all()
            if list(current) != wanted:  # converge on this run's list (more startups may be published now)
                s.execute(delete(Ranking).where(Ranking.investor_id == investor_id))
                s.flush()
                for position, startup_id in enumerate(wanted, start=1):
                    s.add(Ranking(investor_id=investor_id, startup_id=startup_id, position=position))
    return added


def save_demo_accounts(specs: list[StartupSpec]) -> None:
    accounts = [{"email": inv["email"], "name": inv["name"], "role": "investor", "plan": inv["plan"],
                 "headline": inv["headline"]} for inv in INVESTORS]
    accounts += [{"email": spec.founder_account.email, "name": spec.founder_account.name, "role": "startup",
                  "plan": None, "headline": f"Founder · {spec.name} ({spec.domain})"} for spec in specs]
    value = json.dumps({"password": DEMO_PASSWORD, "accounts": accounts})
    with write_tx() as s:
        row = s.get(AppState, "demo_accounts")
        if row is None:
            s.add(AppState(key="demo_accounts", value=value))
        elif row.value != value:
            row.value = value


# ── reset and main ──────────────────────────────────────────────────────────────────────────────────────

async def reset() -> None:
    settings = get_settings()
    database = settings.data_dir / "aura.db"
    print(f"reset: deleting {database}, {settings.data_dir / 'docs'} and Qdrant collections '{settings.qdrant_prefix}_*'")
    db.dispose_engines()
    for path in (database, database.with_name("aura.db-wal"), database.with_name("aura.db-shm")):
        path.unlink(missing_ok=True)
    shutil.rmtree(settings.data_dir / "docs", ignore_errors=True)
    client = store.client()
    for collection in (await client.get_collections()).collections:  # aliases go with their collection
        if collection.name.startswith(settings.qdrant_prefix + "_"):
            await client.delete_collection(collection.name)


async def main(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logger.setLevel(logging.INFO)
    specs = load_specs(SPECS)
    if args.only:
        specs = [spec for spec in specs if spec.slug in set(args.only.split(","))]
    if args.reset:
        await reset()
    migrate.upgrade()
    db.init_engines()
    await store.bootstrap()
    mca.load_registry_fixtures(SPECS)
    started = time.monotonic()

    users = seed_accounts(load_specs(SPECS))
    print(f"accounts: {len(users)} (password {DEMO_PASSWORD})")
    startups: dict[str, str] = {}
    for spec in specs:
        startups[spec.slug] = apply_profile(spec, users[spec.founder_account.email])

    ingested = 0
    for spec in specs:
        prime_embeddings(spec)
        doc_id, fresh = await seed_deck(spec, startups[spec.slug], users[spec.founder_account.email])
        if fresh:
            ingested += 1
            with read_session() as s:
                doc = s.get(Document, doc_id)
            print(f"  ingested {spec.slug:22} {doc.page_count} pages in {doc.ocr_ms / 1000:.1f}s  flags {doc.flags}")
    print(f"decks: {ingested} ingested, {len(specs) - ingested} already up to date")

    semaphore = asyncio.Semaphore(args.concurrency)

    async def evaluate(spec: StartupSpec) -> tuple[str, str]:
        async with semaphore:
            try:
                return spec.slug, await seed_evaluation(spec, startups[spec.slug], allow_llm=args.allow_llm)
            except Exception as exc:  # report and carry on with the other startups
                logger.error("%s: evaluation failed: %s", spec.slug, exc)
                return spec.slug, "failed"

    outcomes = dict(await asyncio.gather(*(evaluate(spec) for spec in specs)))
    counts = {kind: sum(1 for v in outcomes.values() if v == kind)
              for kind in ("kept", "cache", "live", "missing", "no_research", "failed")}
    print(f"evaluations: {counts}")
    if counts["missing"]:
        print("  without an evaluation (run with --allow-llm): " + ", ".join(k for k, v in outcomes.items() if v == "missing"))

    published = 0
    for spec in specs:
        if await publish(startups[spec.slug]):
            published += 1
        save_embeddings(spec, startups[spec.slug])
    print(f"published: {published}/{len(specs)}")

    reviews = seed_reviews_and_rankings(load_specs(SPECS), users, startups)
    print(f"reviews added: {reviews}")
    save_demo_accounts(load_specs(SPECS))
    with read_session() as s:
        unplaced = s.scalars(select(Chunk.id).where(Chunk.proj_x.is_(None))).all()
    if unplaced:
        print(f"embedding map: {await projection.refresh(list(unplaced))} ({len(unplaced)} chunks were not on it)")
    ocr_service.close()
    print(f"done in {time.monotonic() - started:.0f}s")
    from seed.verify import verify

    return await verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="wipe the database, documents and collections first")
    parser.add_argument("--allow-llm", action="store_true", help="evaluate startups missing from the cache")
    parser.add_argument("--only", help="comma-separated slugs (accounts are always seeded)")
    parser.add_argument("--concurrency", type=int, default=2, help="live evaluations at once")
    sys.exit(asyncio.run(main(parser.parse_args())))
