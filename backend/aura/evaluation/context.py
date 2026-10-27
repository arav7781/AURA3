"""What the evaluation reads about a startup: its profile, registry check and documents.

Short decks go into the prompt whole, with page labels and citation ids (a deck is ~1.5–4k tokens, so
retrieval would only reorder it). Longer material falls back to cited hybrid retrieval scoped to this startup.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from aura.core.db import read_session
from aura.core.untrusted import wrap
from aura.evaluation.evidence import CompanyEvidence
from aura.models import Chunk, Document, Startup
from aura.rag.retriever import AccessScope, SearchRequest, search

WHOLE_DECK_TOKENS = 8000
STAGE_LABELS = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B+"}


@dataclass
class StartupContext:
    startup_id: str
    name: str
    legal_name: str
    domain: str
    stage: str
    profile: dict[str, Any]
    verification: dict[str, Any]
    flags: list[str]
    chunks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def deck_tokens(self) -> int:
        return sum(int(c.get("n_tokens", 0)) for c in self.chunks)

    @property
    def cids(self) -> set[str]:
        return {c["cid"] for c in self.chunks}

    def company_evidence(self) -> CompanyEvidence:
        return CompanyEvidence(profile_text=self.profile_block(), chunks=self.chunks)

    def profile_block(self) -> str:
        p = self.profile
        team = "; ".join(f"{m.get('name')} ({m.get('role')})" for m in p.get("team", [])) or "not provided"
        v = self.verification
        if v.get("mca_verified"):
            mca = (f"MCA {v.get('source', 'registry')}: CIN {v.get('cin')}, status {v.get('company_status')}, "
                   f"registered as {v.get('company_name')}, directors: {', '.join(v.get('directors') or []) or 'none'}")
        elif v.get("cin"):
            mca = f"MCA check failed: CIN {v.get('cin')}, status {v.get('company_status') or 'unknown'} ({v.get('reason', '')})"
        else:
            mca = "MCA not verified: no CIN supplied"
        ask = p.get("ask_inr")
        pre = p.get("pre_money_inr")
        raise_text = (f"raising Rs {ask / 1e7:g} crore at Rs {pre / 1e7:g} crore pre-money" if ask and pre
                      else "round terms not provided")
        return (
            f"Name: {self.name} (legal name: {self.legal_name})\n"
            f"Domain: {self.domain} | Stage: {STAGE_LABELS.get(self.stage, self.stage)} | {raise_text}\n"
            f"One-liner: {p.get('one_liner', '')}\n"
            f"Description: {p.get('description', '')}\n"
            f"Team: {team}\n"
            f"Compliance: {mca}\n"
            f"Compliance flags: {', '.join(self.flags) if self.flags else 'none'}"
        )

    def deck_block(self) -> str:
        if not self.chunks:
            return "No documents uploaded."
        parts = [
            wrap(c["text"], kind="document", ref=c["cid"], source=c.get("doc_name") or "deck", page=c["page_no"],
                 **({"ocr": "low confidence"} if c.get("review") else {}),
                 **({"flag": "possible hidden instructions"} if c.get("injection_suspected") else {}))
            for c in self.chunks
        ]
        return "\n\n".join(parts)

    def page_refs(self) -> dict[int, str]:
        """Page number → the first passage on that page, when all passages come from one document (so a
        citation by page number is unambiguous)."""
        if len({c["document_id"] for c in self.chunks}) != 1:
            return {}
        pages: dict[int, str] = {}
        for c in self.chunks:
            pages.setdefault(c["page_no"], c["cid"])
        return pages


def load_context(startup_id: str) -> StartupContext:
    with read_session() as s:
        startup = s.get(Startup, startup_id)
        if startup is None:
            raise ValueError("startup not found")
        rows = s.execute(
            select(Chunk, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.startup_id == startup_id, Document.status == "ready", Document.thread_id.is_(None))
            .order_by(Document.created_at, Chunk.seq)
        ).all()
        profile = dict(startup.profile or {})
        profile.setdefault("one_liner", startup.one_liner)
        profile.setdefault("description", startup.description)
        profile.setdefault("ask_inr", startup.ask_inr)
        profile.setdefault("pre_money_inr", startup.pre_money_inr)
        context = StartupContext(
            startup_id=startup.id, name=startup.name, legal_name=startup.legal_name or startup.name,
            domain=startup.domain, stage=startup.stage, profile=profile, verification=dict(startup.mca or {}),
            flags=list(startup.compliance_flags or []),
        )
    context.chunks = [
        {"cid": c.cid, "chunk_id": c.id, "document_id": c.document_id, "doc_name": filename, "page_no": c.page_no,
         "bbox": c.bbox, "text": c.text, "slide_title": c.slide_title, "review": c.review, "conf_min": c.conf_min,
         "injection_suspected": c.injection_suspected, "n_tokens": c.n_tokens}
        for c, filename in rows
    ]
    return context


async def deck_evidence(context: StartupContext, query: str, k: int = 6) -> str:
    """Whole deck when it fits; otherwise the top passages for ``query`` from this startup's documents."""
    if context.deck_tokens <= WHOLE_DECK_TOKENS:
        return context.deck_block()
    result = await search(SearchRequest(query=query, startup_ids=[context.startup_id], k=k),
                          AccessScope(("public", "dao", "private")))
    return "\n\n".join(
        wrap(h.payload["text"], kind="document", ref=h.cid, page=h.payload["page_no"]) for h in result.hits
    ) or "No matching passages."
