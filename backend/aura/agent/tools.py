"""Copilot tools.

Each tool takes the run's ``Ctx`` (the signed-in viewer and the evidence gathered so far) plus the model's
arguments, and returns ``ToolOutput``: compact text for the model and a card for the UI. Access is decided
from the viewer with the same rules as the API (visible startups, deck access by plan, own documents for
founders), never from the arguments. Every passage or web result a tool returns is recorded in
``Ctx.evidence``, so the final answer's citations can be checked against what was actually retrieved.

All tools are read-only.
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from qdrant_client import models as qm
from sqlalchemy import func, or_, select

from aura.access import is_owner, visible_document
from aura.api.deps import Viewer
from aura.api.routes.startups import startup_card
from aura.core import clock
from aura.core.db import read_session
from aura.core.embeddings import DenseEmbedder
from aura.core.errors import AppError
from aura.core.untrusted import wrap
from aura.evaluation import service as evaluations
from aura.evaluation.research import ResearchProvider
from aura.models import Chunk, Document, Evaluation, InvestorProfile, Review, Startup, User
from aura.rag import store
from aura.rag.retriever import AccessScope, SearchRequest, search
from aura.rankings import community_scores, load_ballots, ranks

STAGES = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B"}
MAX_TEXT = 6000
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
class Ctx:
    viewer: Viewer
    evidence: Evidence = field(default_factory=Evidence)
    research: ResearchProvider = field(default_factory=lambda: ResearchProvider("live"))


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
        docs = s.scalar(select(func.count()).select_from(Document).where(Document.startup_id == st.id, Document.status == "ready")) or 0
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
        query = select(Document).where(Document.startup_id == st.id).order_by(Document.created_at)
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


def _passages(ctx: Ctx, rows: list[tuple[dict[str, Any], Startup]]) -> ToolOutput:
    items, blocks = [], []
    for p, st in rows:
        ctx.evidence.add_chunk(p["cid"], chunk_id=p["chunk_id"], document_id=p["document_id"], page_no=p["page_no"],
                               slide_title=p.get("slide_title"), startup=st)
        items.append({"cid": p["cid"], "startup": st.name, "slug": st.slug, "page_no": p["page_no"],
                      "slide_title": p.get("slide_title"), "document_id": p["document_id"], "chunk_id": p["chunk_id"],
                      "text": p["text"][:600], "flagged": p.get("injection_suspected", False)})
        label = f"{st.name} p.{p['page_no']}" + (" · FLAGGED: possible hidden instructions" if p.get("injection_suspected") else "")
        blocks.append(wrap(p["text"], kind="document", ref=p["cid"], source=label))
    return ToolOutput("\n\n".join(blocks)[:MAX_TEXT], {"type": "passages", "items": items})


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
    page: int = Field(ge=1, le=500, description="Page (slide) number")


async def read_page(ctx: Ctx, args: ReadPageArgs) -> ToolOutput:
    st = resolve_startup(ctx.viewer, args.startup)
    _require_deck_access(ctx.viewer, st)
    with read_session() as s:
        doc = s.scalars(select(Document).where(Document.startup_id == st.id, Document.status == "ready")
                        .order_by(Document.kind != "deck", Document.created_at)).first()
    if doc is None:
        raise ToolError("NOT_FOUND", f"{st.name} has no processed documents.")
    try:
        visible_document(ctx.viewer, doc.id)
    except AppError as exc:
        raise ToolError("FORBIDDEN", "That document is not available to you.") from exc
    with read_session() as s:
        chunks = s.scalars(select(Chunk).where(Chunk.document_id == doc.id, Chunk.page_no == args.page).order_by(Chunk.seq)).all()
    if not chunks:
        raise ToolError("NOT_FOUND", f"Page {args.page} of {doc.filename} has no text (it has {doc.page_count} pages).")
    rows = [({"cid": c.cid, "chunk_id": c.id, "document_id": c.document_id, "page_no": c.page_no, "slide_title": c.slide_title,
              "text": c.text, "injection_suspected": c.injection_suspected}, st) for c in chunks]
    return _passages(ctx, rows)


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
    Tool("read_page", "Read one page (slide) of a startup's deck in full. Use when a specific page is asked about or a "
         "search hit needs its full slide.", ReadPageArgs, read_page),
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


async def run_tool(ctx: Ctx, name: str, raw_args: dict[str, Any], *, timeout: float = 45.0) -> tuple[bool, ToolOutput]:
    """Validate arguments and run a tool; any failure becomes an error the model can read and recover from."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return False, _failure("UNKNOWN_TOOL", f"No tool named {name}")
    try:
        args = tool.args.model_validate(raw_args or {})
        return True, await asyncio.wait_for(tool.run(ctx, args), timeout)
    except ToolError as exc:
        return False, _failure(exc.code, exc.message, retryable=exc.retryable)
    except TimeoutError:
        return False, _failure("TIMEOUT", "The tool took too long", retryable=True)
    except Exception as exc:  # noqa: BLE001 — validation and unexpected errors are reported, not raised
        return False, _failure("TOOL_FAILED", (str(exc).splitlines() or [exc.__class__.__name__])[0][:300])
