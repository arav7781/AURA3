"""Copilot tools.

Each tool takes the run's ``Ctx`` (the signed-in viewer and the evidence gathered so far) plus the model's
arguments, and returns ``ToolOutput``: compact text for the model and a card for the UI. Access is decided
from the viewer with the same rules as the API (visible startups, deck access by plan, own documents for
founders), never from the arguments. Every passage or web result a tool returns is recorded in
``Ctx.evidence``, so the final answer's citations can be checked against what was actually retrieved.

All tools are read-only, except ``build_pitch_deck``, which writes a new private draft deck into the
founder's own conversation, and ``run_python``, which runs the model's code in the locked-down sandbox
(no network, a fresh container per run) with a catalogue of the startups the viewer can see.
"""

import asyncio
import csv
import hashlib
import io
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from qdrant_client import models as qm
from sqlalchemy import func, or_, select

from aura import quotas
from aura.access import is_owner, visible_document
from aura.api.deps import Viewer
from aura.api.routes.startups import startup_card
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.embeddings import DenseEmbedder
from aura.core.errors import AppError
from aura.core.untrusted import wrap
from aura.decks.design import Brand
from aura.decks.draft import DeckDraft, draft_slides, figures, normalise
from aura.decks.render_pdf import render_slides_pdf
from aura.decks.render_pptx import render_slides_pptx
from aura.evaluation import service as evaluations
from aura.evaluation.research import ResearchProvider
from aura.ingest.pipeline import ingest_document
from aura.ingest.storage import document_dir
from aura.models import Chunk, Document, Evaluation, InvestorProfile, Review, Startup, User
from aura.rag import store
from aura.rag.retriever import AccessScope, SearchRequest, search
from aura.rankings import community_scores, load_ballots, ranks
from aura.sandbox.runner import RunSpec, SandboxUnavailable, runner
from aura.sandbox.workspace import RUN_FILES, sandbox_dir

STAGES = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B"}
MAX_TEXT = 6000
MAX_ATTACHMENT_TEXT = 16000  # a whole deck, so it can be reviewed slide by slide
_MARKER = re.compile(r"\s?\[(?:c|w):[^\]]{1,40}\]")


class ToolError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolOutput:
    text: str
    card: dict[str, Any] | None = None


@dataclass
class Evidence:
    deck: dict[str, dict[str, Any]] = field(default_factory=dict)  # cid -> where it is
    web: list[dict[str, str]] = field(default_factory=list)  # [w:n] is web[n - 1]

    def add_chunk(self, cid: str, *, chunk_id: str, document_id: str, page_no: int, slide_title: str | None,
                  startup: Startup) -> None:
        self.deck[cid] = {"type": "deck", "chunk_id": chunk_id, "document_id": document_id, "page_no": page_no,
                          "slide_title": slide_title, "startup_slug": startup.slug, "startup_name": startup.name}

    def add_web(self, result: dict[str, str]) -> int:
        for n, known in enumerate(self.web, start=1):
            if known["url"] == result["url"]:
                return n
        self.web.append({"url": result["url"], "title": result.get("title", ""), "snippet": result.get("snippet", "")})
        return len(self.web)


@dataclass
class Attachment:
    """A file the user attached to this conversation (a private draft of their own startup's document)."""
    document_id: str
    filename: str
    pages: int


@dataclass
class Ctx:
    viewer: Viewer
    evidence: Evidence = field(default_factory=Evidence)
    research: ResearchProvider = field(default_factory=lambda: ResearchProvider("live"))
    attachments: list[Attachment] = field(default_factory=list)
    thread_id: str | None = None


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────────────

def _visible(viewer: Viewer):
    if viewer.is_admin:
        return Startup.id.is_not(None)
    return or_(Startup.status == "published", Startup.owner_user_id == viewer.user_id)


def resolve_startup(viewer: Viewer, ref: str) -> Startup:
    """A startup by id, slug or (partial) name, among those the viewer may see."""
    ref = ref.strip()
    if not ref:
        raise ToolError("BAD_ARGUMENT", "Name the startup.")
    with read_session() as s:
        exact = s.scalar(select(Startup).where(_visible(viewer), or_(
            Startup.id == ref, Startup.slug == ref.lower(), func.lower(Startup.name) == ref.lower())))
        if exact:
            return exact
        like = f"%{ref.lower().replace(' ', '%')}%"
        matches = s.scalars(select(Startup).where(_visible(viewer), or_(
            func.lower(Startup.name).like(like), Startup.slug.like(like))).limit(6)).all()
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ToolError("AMBIGUOUS", f"'{ref}' matches several startups: {', '.join(m.name for m in matches)}. "
                                     "Use the exact name.")
    raise ToolError("NOT_FOUND", f"No startup called '{ref}' is visible to you. Use search_startups to find it.")


def _require_deck_access(viewer: Viewer, startup: Startup | None = None) -> None:
    if viewer.role == "investor" and not viewer.has("deck_access") and not viewer.is_admin:
        raise ToolError("PLAN_REQUIRED", "Reading inside startup documents needs the Angel plan or above. "
                                         "The Scout plan includes AI scores and summaries only.")
    if viewer.role == "startup" and startup is not None and not is_owner(viewer, startup):
        raise ToolError("FORBIDDEN", "Founders can read their own documents only.")


def _line(startup: Startup) -> str:
    score = f"{startup.ai_score_x10 / 10:.1f}/10 {startup.recommendation}" if startup.ai_score_x10 is not None else "not evaluated"
    flags = f" · flags: {', '.join(startup.compliance_flags)}" if startup.compliance_flags else ""
    ask = f" · raising Rs {startup.ask_inr / 1e7:g} crore" if startup.ask_inr else ""
    return (f"- {startup.name} (slug {startup.slug}) · {startup.domain} · {STAGES.get(startup.stage, startup.stage)}"
            f" · AI {score}{ask}{flags}: {startup.one_liner}")


def _strip_markers(text: str) -> str:
    return _MARKER.sub("", text or "").strip()


# ── tools ───────────────────────────────────────────────────────────────────────────────────────────────

class SearchStartupsArgs(BaseModel):
    query: str = Field(default="", description="What the investor is looking for, e.g. 'IoT for farmers' or 'B2B SaaS with strong NRR'. Empty lists by filters only.")
    domain: str | None = Field(default=None, description="Domain filter, e.g. Agritech, Fintech, Healthtech, B2B SaaS, Climate & Energy")
    stage: str | None = Field(default=None, description="pre_seed, seed, series_a or series_b")
    min_score: float | None = Field(default=None, ge=0, le=10, description="Minimum AI score")
    limit: int = Field(default=8, ge=1, le=25)


async def search_startups(ctx: Ctx, args: SearchStartupsArgs) -> ToolOutput:
    order: list[str] = []
    if args.query.strip():
        try:
            vector = (await DenseEmbedder().embed([args.query.strip()]))[0]
            hits = await store.client().query_points(
                store.names.startups, query=vector.tolist(), using="dense", limit=40,
                query_filter=qm.Filter(must=[qm.FieldCondition(key="visibility", match=qm.MatchValue(value="dao"))]))
            order = [str(p.id) for p in hits.points]
        except Exception:  # noqa: BLE001 — fall back to keyword matching below
            order = []
    with read_session() as s:
        query = select(Startup).where(Startup.status == "published")
        if args.domain:
            query = query.where(func.lower(Startup.domain).like(f"%{args.domain.lower()}%"))
        if args.stage:
            query = query.where(Startup.stage == args.stage.lower().replace("-", "_").replace(" ", "_"))
        if args.min_score is not None:
            query = query.where(Startup.ai_score_x10 >= round(args.min_score * 10))
        rows = s.scalars(query).all()
    words = [w for w in re.findall(r"[a-z0-9]+", args.query.lower()) if len(w) > 2]
    rank = {startup_id: i for i, startup_id in enumerate(order)}

    def key(st: Startup) -> tuple:
        text = f"{st.name} {st.one_liner} {st.domain} {st.description}".lower()
        keyword_hits = sum(w in text for w in words)
        return (-keyword_hits if not order else 0, rank.get(st.id, 999), -(st.ai_score_x10 or 0))

    picked = sorted(rows, key=key)[: args.limit]
    if not picked:
        return ToolOutput("No published startups match these filters.", {"type": "startups", "items": []})
    return ToolOutput(f"{len(picked)} startup(s), best match first:\n" + "\n".join(_line(st) for st in picked),
                      {"type": "startups", "items": [startup_card(st) for st in picked]})


class StartupArgs(BaseModel):
    startup: str = Field(description="Startup name or slug, e.g. 'KrishiMitra AI' or 'krishimitra-ai'")


async def get_startup(ctx: Ctx, args: StartupArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    p = st.profile or {}
    with read_session() as s:
        docs = s.scalar(select(func.count()).select_from(Document).where(
            Document.startup_id == st.id, Document.status == "ready", Document.thread_id.is_(None))) or 0
        reviews = s.execute(select(func.count(), func.avg((Review.team + Review.market + Review.product + Review.traction) / 4.0))
                            .where(Review.startup_id == st.id)).one()
    team = "; ".join(f"{m.get('name')} — {m.get('role')}" + (f" ({m['background']})" if m.get("background") else "")
                     for m in p.get("team", [])) or "not given"
    rnd = p.get("round") or {}
    tranches = "; ".join(f"{t['pct']}% at {t['title']}" for t in rnd.get("tranches", []))
    mca = st.mca or {}
    lines = [
        f"{st.name} ({st.legal_name or 'legal name not given'}) · slug {st.slug}",
        f"Domain {st.domain}{f' / {st.sub_domain}' if st.sub_domain else ''} · {STAGES.get(st.stage, st.stage)} · "
        f"HQ {st.hq_city or '?'}, {st.hq_state or '?'} · founded {st.founded_year or '?'}",
        f"One-liner: {st.one_liner}",
        f"Description: {st.description}",
        f"Team: {team}",
        f"Round: raising Rs {(st.ask_inr or 0) / 1e7:g} crore at Rs {(st.pre_money_inr or 0) / 1e7:g} crore pre-money"
        + (f"; minimum raise {rnd.get('min_raise_pct')}%; tranches: {tranches}" if rnd else ""),
        f"Registry (MCA): CIN {st.cin or 'none'}, status {mca.get('company_status') or 'unknown'}"
        + (f", registered as {mca.get('company_name')}" if mca.get("company_name") else "")
        + (f"; compliance flags: {', '.join(st.compliance_flags)}" if st.compliance_flags else "; no compliance flags"),
        f"AI evaluation: {st.ai_score_x10 / 10:.1f}/10, {st.recommendation}" if st.ai_score_x10 is not None else "AI evaluation: none published",
        f"Documents: {docs} processed · investor reviews: {reviews[0]}" + (f", average {reviews[1]:.2f}/5" if reviews[0] else ""),
    ]
    return ToolOutput("\n".join(lines), {"type": "startup", "item": startup_card(st) | {"legal_name": st.legal_name, "documents": docs}})


async def list_documents(ctx: Ctx, args: StartupArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    owner = is_owner(ctx.viewer, st)
    with read_session() as s:
        query = select(Document).where(Document.startup_id == st.id, Document.thread_id.is_(None)).order_by(Document.created_at)
        if not owner:
            query = query.where(Document.visibility == "published", Document.status == "ready")
        docs = s.scalars(query).all()
    can_open = owner or ctx.viewer.is_admin or (ctx.viewer.role == "investor" and ctx.viewer.has("deck_access"))
    items = [{
        "id": d.id, "filename": d.filename, "kind": d.kind, "pages": d.page_count, "status": d.status,
        "uploaded_at": clock.iso(d.created_at), "flags": d.flags, "ocr_seconds": round((d.ocr_ms or 0) / 1000, 1),
        "size_bytes": d.size_bytes, "view_url": f"/startups/{st.slug}?tab=evidence&doc={d.id}",
        "download_url": f"/api/documents/{d.id}/file" if can_open else None,
    } for d in docs]
    if not items:
        return ToolOutput(f"{st.name} has not submitted any processed documents yet.",
                          {"type": "documents", "startup": startup_card(st), "items": [], "can_open": can_open})
    text = [f"{st.name} has submitted {len(items)} document(s):"]
    for d in items:
        flags = f", flags {', '.join(d['flags'])}" if d["flags"] else ""
        text.append(f"- {d['filename']} ({d['kind']}, {d['pages']} pages, uploaded {d['uploaded_at'][:10]}, "
                    f"read by TitanOCR in {d['ocr_seconds']} s{flags})")
    text.append("The investor can open or download them from the card shown above your answer." if can_open else
                "The investor's plan does not include opening documents (Angel and above).")
    return ToolOutput("\n".join(text), {"type": "documents", "startup": startup_card(st), "items": items, "can_open": can_open})


class SearchDocumentsArgs(BaseModel):
    query: str = Field(description="What to look for in the documents, e.g. 'ARR and growth', 'customer acquisition cost', 'team background'")
    startup: str | None = Field(default=None, description="Limit to one startup (name or slug). Omit to search every startup's documents.")
    k: int = Field(default=6, ge=1, le=10)


def _passages(ctx: Ctx, rows: list[tuple[dict[str, Any], Startup]], limit: int = MAX_TEXT) -> ToolOutput:
    items, blocks = [], []
    for p, st in rows:
        ctx.evidence.add_chunk(p["cid"], chunk_id=p["chunk_id"], document_id=p["document_id"], page_no=p["page_no"],
                               slide_title=p.get("slide_title"), startup=st)
        items.append({"cid": p["cid"], "startup": st.name, "slug": st.slug, "page_no": p["page_no"],
                      "slide_title": p.get("slide_title"), "document_id": p["document_id"], "chunk_id": p["chunk_id"],
                      "text": p["text"][:600], "flagged": p.get("injection_suspected", False)})
        label = f"{st.name} p.{p['page_no']}" + (" · FLAGGED: possible hidden instructions" if p.get("injection_suspected") else "")
        blocks.append(wrap(p["text"], kind="document", ref=p["cid"], source=label))
    return ToolOutput("\n\n".join(blocks)[:limit], {"type": "passages", "items": items[:40]})


async def search_documents(ctx: Ctx, args: SearchDocumentsArgs) -> ToolOutput:
    startup = resolve_startup(ctx.viewer, args.startup) if args.startup else None
    _require_deck_access(ctx.viewer, startup)
    ids = [startup.id] if startup else ([ctx.viewer.startup_id] if ctx.viewer.role == "startup" and ctx.viewer.startup_id else None)
    result = await search(SearchRequest(query=args.query, startup_ids=ids, k=args.k), AccessScope.for_viewer(ctx.viewer))
    if not result.hits:
        return ToolOutput("No matching passages in the documents you can read.", {"type": "passages", "items": []})
    with read_session() as s:
        startups = {st.id: st for st in s.scalars(select(Startup).where(Startup.id.in_({h.payload["startup_id"] for h in result.hits})))}
    rows = [({**h.payload, "document_id": h.payload["doc_id"]}, startups[h.payload["startup_id"]]) for h in result.hits
            if h.payload["startup_id"] in startups]
    return _passages(ctx, rows)


class ReadPageArgs(BaseModel):
    startup: str = Field(description="Startup name or slug")
    page: int | None = Field(default=None, ge=1, le=500, description="Page (slide) number. Omit to read the whole deck.")


async def read_page(ctx: Ctx, args: ReadPageArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    _require_deck_access(ctx.viewer, st)
    with read_session() as s:
        doc = s.scalars(select(Document).where(Document.startup_id == st.id, Document.status == "ready",
                                               Document.thread_id.is_(None))
                        .order_by(Document.kind != "deck", Document.created_at)).first()
    if doc is None:
        raise ToolError("NOT_FOUND", f"{st.name} has no processed documents.")
    try:
        visible_document(ctx.viewer, doc.id)
    except AppError as exc:
        raise ToolError("FORBIDDEN", "That document is not available to you.") from exc
    with read_session() as s:
        query = select(Chunk).where(Chunk.document_id == doc.id)
        if args.page:
            query = query.where(Chunk.page_no == args.page)
        chunks = s.scalars(query.order_by(Chunk.page_no, Chunk.seq)).all()
    if not chunks:
        raise ToolError("NOT_FOUND", f"Page {args.page} of {doc.filename} has no text (it has {doc.page_count} pages).")
    rows = [({"cid": c.cid, "chunk_id": c.id, "document_id": c.document_id, "page_no": c.page_no, "slide_title": c.slide_title,
              "text": c.text, "injection_suspected": c.injection_suspected}, st) for c in chunks]
    return _passages(ctx, rows, limit=MAX_TEXT if args.page else MAX_ATTACHMENT_TEXT)


class ReadAttachmentArgs(BaseModel):
    document: str | None = Field(default=None, description="File name or id of the attachment. Omit for the most recent one.")
    page: int | None = Field(default=None, ge=1, le=500, description="One page (slide). Omit to read the whole file.")


async def read_attachment(ctx: Ctx, args: ReadAttachmentArgs) -> ToolOutput:
    if not ctx.attachments:
        raise ToolError("NOT_FOUND", "No file is attached to this conversation.")
    pick = ctx.attachments[-1]
    if args.document:
        ref = args.document.strip().lower()
        matches = [a for a in ctx.attachments if a.document_id == args.document or ref in a.filename.lower()]
        if not matches:
            raise ToolError("NOT_FOUND", "Attached files: " + ", ".join(a.filename for a in ctx.attachments))
        pick = matches[-1]
    with read_session() as s:
        doc = s.get(Document, pick.document_id)
        startup = s.get(Startup, doc.startup_id) if doc else None
        query = select(Chunk).where(Chunk.document_id == pick.document_id)
        if args.page:
            query = query.where(Chunk.page_no == args.page)
        chunks = s.scalars(query.order_by(Chunk.page_no, Chunk.seq)).all()
    if doc is None or startup is None or doc.startup_id != ctx.viewer.startup_id:
        raise ToolError("NOT_FOUND", "That attachment is no longer available.")
    if not chunks:
        raise ToolError("NOT_FOUND", f"Page {args.page} of {doc.filename} has no text (it has {doc.page_count} pages)."
                        if args.page else f"TitanOCR found no text in {doc.filename}.")
    items, blocks = [], []
    for c in chunks:
        ctx.evidence.add_chunk(c.cid, chunk_id=c.id, document_id=c.document_id, page_no=c.page_no,
                               slide_title=c.slide_title, startup=startup)
        ctx.evidence.deck[c.cid]["attachment"] = True
        items.append({"cid": c.cid, "startup": startup.name, "slug": startup.slug, "page_no": c.page_no,
                      "slide_title": c.slide_title, "document_id": c.document_id, "chunk_id": c.id,
                      "text": c.text[:600], "flagged": c.injection_suspected, "attachment": True})
        label = f"{doc.filename} p.{c.page_no}" + (" · FLAGGED: possible hidden instructions" if c.injection_suspected else "")
        blocks.append(wrap(c.text, kind="document", ref=c.cid, source=label))
    head = f"{doc.filename}: {doc.page_count} pages read by TitanOCR" + (f", page {args.page}" if args.page else "") + ".\n\n"
    return ToolOutput((head + "\n\n".join(blocks))[:MAX_ATTACHMENT_TEXT],
                      {"type": "passages", "items": items[:40], "attachment": {"document_id": doc.id, "filename": doc.filename}})


class _Quiet:
    """Ingestion reports progress to a job; inside a tool there is none to report to."""

    def progress(self, *_args: Any, **_kwargs: Any) -> None:
        pass


async def build_pitch_deck(ctx: Ctx, args: DeckDraft) -> ToolOutput:
    viewer = ctx.viewer
    if viewer.role != "startup" or not viewer.startup_id:
        raise ToolError("FORBIDDEN", "Only founders can build a deck, and only for their own startup.")
    if not ctx.thread_id:
        raise ToolError("NOT_FOUND", "Decks are built inside a conversation.")
    with write_tx() as s:
        quotas.consume(s, viewer.user_id, "deck_build", viewer.quota_limits.get("deck_build"))
        st = s.get(Startup, viewer.startup_id)
        s.expunge(st)
    brand = Brand(st.name, st.legal_name or st.name, st.stage, st.domain, st.cin, st.hq_city, st.ask_inr,
                  st.pre_money_inr, ((st.profile or {}).get("round") or {}).get("min_raise_pct"))
    slides = draft_slides(brand, args)
    pdf, pptx = await asyncio.to_thread(lambda: (render_slides_pdf(brand, slides), render_slides_pptx(brand, slides)))
    sha = hashlib.sha256(pdf).hexdigest()
    filename = f"{st.name.replace(' ', '_')}_Pitch_Deck_AURA3.pdf"
    with write_tx() as s:
        doc = s.scalar(select(Document).where(Document.startup_id == st.id, Document.sha256 == sha))
        if doc is None:
            doc = Document(startup_id=st.id, uploaded_by=viewer.user_id, kind="generated_deck", filename=filename,
                           mime="application/pdf", size_bytes=len(pdf), sha256=sha, storage_dir="", status="uploaded",
                           visibility="private", thread_id=ctx.thread_id)
            s.add(doc)
            s.flush()
            folder = document_dir(doc.id)
            doc.storage_dir = str(folder.relative_to(folder.parents[1]))
            (folder / "source.pdf").write_bytes(pdf)
            (folder / "deck.pptx").write_bytes(pptx)
        doc_id, ready = doc.id, doc.status == "ready"
    if not ready:  # TitanOCR reads the new deck back, exactly as it would read an upload
        await ingest_document(_Quiet(), doc_id)  # type: ignore[arg-type]
    with read_session() as s:
        doc = s.get(Document, doc_id)
        text = normalise(" ".join(s.scalars(select(Chunk.text).where(Chunk.document_id == doc_id))))
    stated = figures(args)
    missing = [f for f in stated if f not in text]
    if not any(a.document_id == doc_id for a in ctx.attachments):
        ctx.attachments.append(Attachment(doc_id, doc.filename, doc.page_count or len(slides)))
    pages = doc.page_count or len(slides)
    card = {
        "type": "deck", "document_id": doc_id, "filename": doc.filename, "pages": pages,
        "slides": [sl.title for sl in slides],
        "pdf_url": f"/api/documents/{doc_id}/file", "pptx_url": f"/api/documents/{doc_id}/deck.pptx",
        "previews": [f"/api/documents/{doc_id}/pages/{n}/image" for n in range(1, pages + 1)],
        "check": {"figures": len(stated), "found": len(stated) - len(missing), "missing": missing[:12]},
    }
    check = (f"TitanOCR read the PDF back and found all {len(stated)} figures it states."
             if not missing else f"TitanOCR read the PDF back: {len(stated) - len(missing)} of {len(stated)} figures "
             f"found; not found: {', '.join(missing[:8])}.")
    return ToolOutput(
        f"Built {doc.filename} ({pages} slides: {', '.join(sl.title for sl in slides)}) in AURA3's deck design, as "
        f"PowerPoint and PDF. {check} The founder downloads it from the card above your answer; it is a private "
        "draft, not what investors see. Do not repeat the slide text: say in a few lines what the deck now does "
        "better and what they should check or add before using it.", card)


class RunPythonArgs(BaseModel):
    code: str = Field(max_length=20000, description=(
        "A complete Python 3.13 script. pandas, numpy, scipy, matplotlib, openpyxl and python-pptx are installed; "
        "there is no internet. startups.csv in the working directory has one row per startup the user can see "
        "(name, domain, stage, AI score and rubric scores, round terms, registry status). Print the results; save "
        "charts and files to out/, e.g. plt.savefig('out/chart.png', dpi=160, bbox_inches='tight')."))
    purpose: str = Field(default="", max_length=120, description="One line: what the code works out")


CATALOGUE_COLUMNS = ["name", "slug", "domain", "stage", "city", "founded", "ai_score", "recommendation",
                     "team", "market", "product", "traction", "business_model", "moat", "execution_risk",
                     "ask_inr_crore", "pre_money_inr_crore", "min_raise_pct", "registry_status", "flags"]


def catalogue_csv(viewer: Viewer) -> bytes:
    """The startups the viewer can see, with the published AI scores, as CSV for the sandbox."""
    with read_session() as s:
        startups = s.scalars(select(Startup).where(_visible(viewer)).order_by(Startup.name)).all()
        evaluations = {e.id: e for e in s.scalars(select(Evaluation).where(
            Evaluation.id.in_([st.latest_evaluation_id for st in startups if st.latest_evaluation_id])))}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CATALOGUE_COLUMNS)
    for st in startups:
        evaluation = evaluations.get(st.latest_evaluation_id or "")
        scores = ((evaluation.result if evaluation else None) or {}).get("category_scores") or {}
        writer.writerow([st.name, st.slug, st.domain, st.stage, st.hq_city or "", st.founded_year or "",
                         st.ai_score_x10 / 10 if st.ai_score_x10 is not None else "", st.recommendation or "",
                         *(scores.get(k, "") for k in ("team", "market", "product", "traction", "business_model", "moat",
                                                       "execution_risk")),
                         st.ask_inr / 1e7 if st.ask_inr else "", st.pre_money_inr / 1e7 if st.pre_money_inr else "",
                         ((st.profile or {}).get("round") or {}).get("min_raise_pct", ""),
                         (st.mca or {}).get("company_status", ""), ";".join(st.compliance_flags)])
    return out.getvalue().encode()


def _collect(out_dir) -> list[dict[str, Any]]:
    """Files the run saved to out/: only known types, size-capped; images re-encoded (no hidden payloads)."""
    from PIL import Image

    files = []
    for path in sorted(out_dir.iterdir()) if out_dir.is_dir() else []:
        suffix = path.suffix.lower()
        if not path.is_file() or path.is_symlink() or suffix not in RUN_FILES or path.stat().st_size > 10 << 20:
            path.unlink(missing_ok=True)
            continue
        if suffix == ".png":
            try:
                with Image.open(path) as image:
                    image.load()
                    if image.width * image.height > 25_000_000:
                        raise ValueError("image too large")
                    clean = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
                clean.save(path, format="PNG")
            except Exception:  # noqa: BLE001 — anything Pillow cannot read is dropped
                path.unlink(missing_ok=True)
                continue
        files.append({"name": path.name, "kind": "image" if suffix == ".png" else "file", "bytes": path.stat().st_size})
        if len(files) >= 10:
            break
    return files


async def run_python(ctx: Ctx, args: RunPythonArgs) -> ToolOutput:
    viewer = ctx.viewer
    if not ctx.thread_id:
        raise ToolError("NOT_FOUND", "Code runs inside a conversation.")
    if await asyncio.to_thread(runner.status) != "ready":
        raise ToolError("SANDBOX_UNAVAILABLE", "The code sandbox is not running right now.", retryable=True)
    with write_tx() as s:
        quotas.consume(s, viewer.user_id, "sandbox", viewer.quota_limits.get("sandbox"))
    run_id = uuid.uuid4().hex[:12]
    workspace = sandbox_dir(ctx.thread_id) / run_id
    try:
        result = await runner.run(RunSpec(
            argv=["python", "/opt/aura/runner.py", "/work/main.py"], workspace=workspace, timeout_s=60, mem="768m",
            files={"main.py": args.code.encode(), "startups.csv": catalogue_csv(viewer)}))
    except SandboxUnavailable as exc:
        raise ToolError("SANDBOX_UNAVAILABLE", str(exc), retryable=True) from exc
    files = _collect(workspace / "out")
    base = f"/api/copilot/threads/{ctx.thread_id}/runs/{run_id}/files"
    for f in files:
        f["url"] = f"{base}/{f['name']}"
    stdout, stderr = "\n".join(result.stdout), "\n".join(result.stderr)
    outcome = {"ok": "finished", "error": f"failed (exit code {result.exit_code})", "timeout": "was stopped after 60 s",
               "oom": "ran out of memory (768 MB)", "failed_to_start": "could not start"}[result.status]
    text = [f"The script {outcome} in {result.ms / 1000:.1f} s."]
    if stdout:
        text.append("stdout:\n" + stdout[-4000:])
    if stderr and result.status != "ok":
        text.append("stderr:\n" + stderr[-2000:])
    if files:
        text.append("Files it saved (shown to the user on the card): " + ", ".join(f["name"] for f in files))
    if result.truncated:
        text.append("(output was cut off at 2,000 lines)")
    card = {"type": "code", "purpose": args.purpose, "code": args.code, "status": result.status,
            "exit_code": result.exit_code, "ms": result.ms, "stdout": result.stdout[-80:], "stderr": result.stderr[-30:],
            "files": files, "truncated": result.truncated}
    return ToolOutput("\n\n".join(text), card)


async def get_evaluation(ctx: Ctx, args: StartupArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    owner = is_owner(ctx.viewer, st)
    evaluation = evaluations.latest(st.id, published_only=not owner)
    if evaluation is None or evaluation.status != "complete" or not evaluation.result:
        return ToolOutput(f"{st.name} has no completed AI evaluation you can see.", {"type": "evaluation", "startup": startup_card(st), "score": None})
    a = evaluation.result
    full = owner or ctx.viewer.is_admin or ctx.viewer.has("full_report")
    for ref, c in (a.get("citations") or {}).items():
        if c.get("type") == "deck":
            ctx.evidence.add_chunk(ref, chunk_id=c["chunk_id"], document_id=c["document_id"], page_no=c["page_no"],
                                   slide_title=c.get("slide_title"), startup=st)
    summary = re.sub(r"\s?\[w:\d+\]", "", a["sections"].get("executive_summary", ""))
    scores = ", ".join(f"{k.replace('_', ' ')} {v:.1f}" for k, v in a.get("category_scores", {}).items())
    lines = [f"AI evaluation of {st.name} (version {evaluation.version}, {clock.iso(evaluation.completed_at)[:10]}): "
             f"{a.get('overall_score')}/10, {a.get('recommendation_label')}.",
             f"Compliance flags: {', '.join(a.get('compliance_flags') or []) or 'none'}.",
             f"Executive summary: {summary}"]
    if full:
        lines.append(f"Rubric scores (0-10): {scores}.")
        for key, text in (a.get("score_rationales") or {}).items():
            lines.append(f"Why {key.replace('_', ' ')}: {re.sub(r'\s?\[w:\d+\]', '', text)}")
        claims = (a.get("market_sizing") or {}).get("claims") or {}
        for key, c in claims.items():
            lines.append(f"Deck claim {key.split('_')[0].upper()}: {c['value']:g} {c['unit']} ({c.get('year') or c.get('period')}) — "
                         f"check: {c.get('check', {}).get('status', 'unverified').replace('_', ' ')}.")
        if a.get("data_gaps"):
            lines.append("Data gaps: " + " ".join(a["data_gaps"][:6]))
    else:
        lines.append("(The full report — rubric rationales, claim checks and data gaps — needs the Angel plan.)")
    card = {"type": "evaluation", "startup": startup_card(st), "score": a.get("overall_score"),
            "label": a.get("recommendation_label"), "categories": a.get("category_scores") if full else None,
            "flags": a.get("compliance_flags") or [], "version": evaluation.version}
    return ToolOutput("\n".join(lines)[:MAX_TEXT], card)


class CompareArgs(BaseModel):
    startups: list[str] = Field(min_length=2, max_length=4, description="2 to 4 startup names or slugs")


async def compare_startups(ctx: Ctx, args: CompareArgs) -> ToolOutput:
    picked = [resolve_startup(ctx.viewer, ref) for ref in args.startups]
    with read_session() as s:
        board = community_scores([b for b in load_ballots(s) if b.startup_ids])
        published = {st.id for st in s.scalars(select(Startup).where(Startup.status == "published"))}
        community_rank = ranks({k: v["score"] for k, v in board.items() if k in published})
        rows = []
        for st in picked:
            ev = s.get(Evaluation, st.latest_evaluation_id) if st.latest_evaluation_id else None
            cats = (ev.result or {}).get("category_scores", {}) if ev and ctx.viewer.has("full_report") else {}
            review = s.execute(select(func.count(), func.avg((Review.team + Review.market + Review.product + Review.traction) / 4.0))
                               .where(Review.startup_id == st.id)).one()
            rows.append(startup_card(st) | {"categories": cats, "reviews": review[0],
                                            "review_avg": round(review[1], 2) if review[1] else None,
                                            "community_rank": community_rank.get(st.id)})
    header = "| | " + " | ".join(r["name"] for r in rows) + " |"
    lines = [header, "|---" * (len(rows) + 1) + "|"]

    def row(label: str, values: list[Any]) -> None:
        lines.append(f"| {label} | " + " | ".join("—" if v in (None, "") else str(v) for v in values) + " |")

    row("Domain / stage", [f"{r['domain']} / {STAGES.get(r['stage'], r['stage'])}" for r in rows])
    row("AI score", [f"{r['ai_score']} ({r['recommendation']})" if r["ai_score"] is not None else None for r in rows])
    for key in ("product", "market", "team", "business_model", "moat", "execution_risk", "traction"):
        if any(key in r["categories"] for r in rows):
            row(key.replace("_", " ").capitalize(), [r["categories"].get(key) for r in rows])
    row("Raising (Rs crore)", [f"{r['ask_inr'] / 1e7:g}" if r["ask_inr"] else None for r in rows])
    row("Pre-money (Rs crore)", [f"{r['pre_money_inr'] / 1e7:g}" if r["pre_money_inr"] else None for r in rows])
    row("Investor reviews", [f"{r['reviews']} (avg {r['review_avg']}/5)" if r["reviews"] else "0" for r in rows])
    row("Community rank", [r["community_rank"] for r in rows])
    row("Compliance flags", [", ".join(r["compliance_flags"]) or "none" for r in rows])
    return ToolOutput("\n".join(lines), {"type": "comparison", "items": rows})


async def get_reviews(ctx: Ctx, args: StartupArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    anonymise = is_owner(ctx.viewer, st) and not ctx.viewer.is_admin
    with read_session() as s:
        rows = s.execute(select(Review, User.name, InvestorProfile.plan).join(User, User.id == Review.investor_id)
                         .outerjoin(InvestorProfile, InvestorProfile.user_id == Review.investor_id)
                         .where(Review.startup_id == st.id).order_by(Review.created_at)).all()
    if not rows:
        return ToolOutput(f"No investor has reviewed {st.name} yet.", {"type": "reviews", "startup": startup_card(st), "items": []})
    items = []
    for i, (r, name, plan) in enumerate(rows):
        items.append({"reviewer": f"Investor {chr(65 + i % 26)}" if anonymise else name, "plan": None if anonymise else plan,
                      "team": r.team, "market": r.market, "product": r.product, "traction": r.traction, "note": r.note})
    avg = {d: round(sum(x[d] for x in items) / len(items), 2) for d in ("team", "market", "product", "traction")}
    text = [f"{len(items)} review(s) of {st.name}; averages out of 5: " + ", ".join(f"{k} {v}" for k, v in avg.items()) + "."]
    text += [f"- {x['reviewer']}: team {x['team']}, market {x['market']}, product {x['product']}, traction {x['traction']}. {x['note']}"
             for x in items[:8]]
    return ToolOutput(wrap("\n".join(text), kind="reviews"), {"type": "reviews", "startup": startup_card(st), "items": items, "averages": avg})


class WebSearchArgs(BaseModel):
    query: str = Field(description="A focused web query, e.g. 'India agriculture IoT market size 2025 CAGR'")


async def web_search(ctx: Ctx, args: WebSearchArgs) -> ToolOutput:
    results = [r for r in await ctx.research.search(args.query, max_results=5) if r.get("url")]
    if not results:
        raise ToolError("UNAVAILABLE", "Web search returned nothing (it may be unreachable). Answer from platform data and say so.", retryable=True)
    items, blocks = [], []
    for r in results:
        n = ctx.evidence.add_web(r)
        items.append({"n": n, "title": r.get("title", ""), "url": r["url"], "snippet": r.get("snippet", "")[:300]})
        blocks.append(wrap(f"{r.get('title', '')}\nURL: {r['url']}\n{r.get('snippet', '')}", kind="web", ref=f"w:{n}"))
    return ToolOutput("\n\n".join(blocks)[:MAX_TEXT], {"type": "web", "items": items})


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[Ctx, Any], Awaitable[ToolOutput]]
    timeout: float = 45.0

    def spec(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.args.model_json_schema()}}


TOOLS = [
    Tool("search_startups", "Find published startups by what they do, domain, stage or minimum AI score. Use first when the "
         "investor describes a kind of company rather than naming one.", SearchStartupsArgs, search_startups),
    Tool("get_startup", "One startup's profile: team, round terms, registry (MCA) status and flags, AI score, document and "
         "review counts. Use when a startup is named.", StartupArgs, get_startup),
    Tool("list_documents", "The documents a startup has submitted (pitch deck etc.) with pages, upload date and links the "
         "investor can open. Use when asked what a startup submitted or for its documents.", StartupArgs, list_documents),
    Tool("search_documents", "Search inside startups' submitted documents and return cited passages. Use for any question "
         "the documents can answer (traction, revenue, pricing, team, market claims). Optionally limit to one startup.",
         SearchDocumentsArgs, search_documents),
    Tool("read_page", "Read one page (slide) of a startup's deck in full, or the whole deck in one call by omitting page. "
         "Use for a specific slide, a search hit's full slide, or (without page) before reviewing or rebuilding a deck.",
         ReadPageArgs, read_page),
    Tool("read_attachment", "Read a file the user attached to this conversation (e.g. a new draft of their pitch deck), "
         "in full or one page. Use it whenever the user refers to the attached file; it is not found by search_documents.",
         ReadAttachmentArgs, read_attachment),
    Tool("build_pitch_deck", "Founders only: create their pitch deck as a designed PowerPoint and PDF file from slide "
         "content you write (cover, problem, solution, market, business model, traction, unit economics, competition, "
         "go-to-market, roadmap, team, ask). Use it whenever the founder asks you to make, create, rebuild, redesign or "
         "export their deck or slides. Write every slide in full, using only figures from their documents and "
         "evaluation (mark estimates as estimates).", DeckDraft, build_pitch_deck, timeout=150.0),
    Tool("run_python", "Write and run a Python script in a sandbox (no internet) for calculations, projections, "
         "comparisons across startups (startups.csv) or charts. Use it whenever an answer needs arithmetic beyond a "
         "single step or a chart; put the numbers you need from documents or the web in the script.",
         RunPythonArgs, run_python, timeout=100.0),
    Tool("get_evaluation", "A startup's AI due-diligence evaluation: score, label, rubric scores and reasons, deck claims "
         "checked against sources, data gaps.", StartupArgs, get_evaluation),
    Tool("compare_startups", "Side-by-side comparison of 2 to 4 startups: AI and rubric scores, round terms, reviews, "
         "community rank and flags.", CompareArgs, compare_startups),
    Tool("get_reviews", "What other investors said about a startup: ratings and notes.", StartupArgs, get_reviews),
    Tool("web_search", "Search the web for facts not on the platform: market sizes, competitors, funding news, regulation. "
         "Do not use it for facts the startup's own documents or evaluation already answer.", WebSearchArgs, web_search),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def _failure(code: str, message: str, *, retryable: bool = False) -> ToolOutput:
    envelope = {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}
    return ToolOutput(json.dumps(envelope), {"type": "error", "code": code, "message": message})


async def run_tool(ctx: Ctx, name: str, raw_args: dict[str, Any], *, timeout: float | None = None) -> tuple[bool, ToolOutput]:
    """Validate arguments and run a tool; any failure becomes an error the model can read and recover from."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return False, _failure("UNKNOWN_TOOL", f"No tool named {name}")
    try:
        args = tool.args.model_validate(raw_args or {})
        return True, await asyncio.wait_for(tool.run(ctx, args), timeout or tool.timeout)
    except ToolError as exc:
        return False, _failure(exc.code, exc.message, retryable=exc.retryable)
    except AppError as exc:  # e.g. a daily quota
        return False, _failure(exc.code, exc.message)
    except TimeoutError:
        return False, _failure("TIMEOUT", "The tool took too long", retryable=True)
    except Exception as exc:  # noqa: BLE001 — validation and unexpected errors are reported, not raised
        return False, _failure("TOOL_FAILED", (str(exc).splitlines() or [exc.__class__.__name__])[0][:300])
