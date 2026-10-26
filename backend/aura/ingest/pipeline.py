"""The ingestion job: upload → (convert) → TitanOCR → page renders → injection scan → chunks → vectors.

Each stage reports progress on the job's SSE stream. Re-ingesting a document replaces its pages, chunks and
vectors (deleted by ``doc_id`` first), so nothing is duplicated.
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import delete

from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.jobs import JobContext
from aura.ingest import injection, render
from aura.ingest.chunker import CHUNKER_VERSION, DocMeta, chunk_ir
from aura.ingest.geometry import page_exact
from aura.ingest.ocr import ocr_service
from aura.ingest.storage import document_dir
from aura.models import Chunk, Document, DocumentPage, Startup
from aura.rag import indexer, store
from aura.sandbox.office import OFFICE_SUFFIXES, convert_to_pdf

logger = logging.getLogger("aura.ingest")

FLAG_INJECTION = "DECK_HIDDEN_INSTRUCTIONS"
FLAG_REVIEW = "OCR_REVIEW_REQUIRED"
FLAG_PARTIAL = "OCR_PARTIAL"


def _source_path(doc: Document):
    folder = document_dir(doc.id)
    matches = sorted(folder.glob("source.*"))
    if not matches:
        raise FileNotFoundError(f"source file for document {doc.id} is missing")
    return matches[0]


async def ingest_document(ctx: JobContext, document_id: str) -> dict[str, Any]:
    with read_session() as s:
        doc = s.get(Document, document_id)
        startup = s.get(Startup, doc.startup_id) if doc else None
        if doc is None or startup is None:
            raise ValueError("document not found")
    with write_tx() as s:
        s.get(Document, document_id).status = "processing"

    try:
        return await _ingest(ctx, doc, startup)
    except Exception as exc:
        with write_tx() as s:
            row = s.get(Document, document_id)
            row.status = "failed"
            row.error = str(exc)[:2000]
        raise


async def _ingest(ctx: JobContext, doc: Document, startup: Startup) -> dict[str, Any]:
    folder = document_dir(doc.id)
    source = _source_path(doc)
    suffix = source.suffix.lower()

    ocr_input = source
    if suffix in OFFICE_SUFFIXES:
        ctx.progress("converting", 10, "Converting to PDF with LibreOffice (sandboxed)")
        ocr_input = await convert_to_pdf(source, workdir=folder / "convert")
        (folder / "converted.pdf").write_bytes(ocr_input.read_bytes())
        ocr_input = folder / "converted.pdf"

    ctx.progress("ocr", 30, "TitanOCR is reading the document")
    outcome = await ocr_service.ocr(ocr_input, filename=doc.filename)
    ir = outcome.ir
    pages = ir.get("pages") or []
    (folder / "ir.json").write_text(json.dumps({"ir": ir, "pages": outcome.pages, "versions": outcome.versions}))
    (folder / "spatial.md").write_text(outcome.spatial_markdown)
    ctx.progress("ocr", 55, f"{len(pages)} page(s) read in {outcome.ms / 1000:.1f}s", pages=len(pages),
                 review_required=outcome.review_required)

    ctx.progress("rendering", 62, "Rendering page images")
    sizes = {int(p["page_no"]): (int(p["width"]), int(p["height"])) for p in pages}
    if ocr_input.suffix.lower() == ".pdf":
        images = await asyncio.to_thread(render.render_pdf_pages, ocr_input, folder / "pages", sizes)
    else:
        images = {1: await asyncio.to_thread(render.render_image_page, ocr_input, folder / "pages", sizes.get(1))}

    ctx.progress("scanning", 68, "Scanning for hidden instructions")
    findings = await asyncio.to_thread(
        injection.scan_document, ocr_input if ocr_input.suffix.lower() == ".pdf" else None,
        original=source if suffix == ".pptx" else None,
    )

    ctx.progress("chunking", 72, "Building chunks with page and box provenance")
    visibility = "dao" if startup.status == "published" and doc.visibility == "published" else "private"
    meta = DocMeta(doc.id, startup.id, startup.name, startup.domain, startup.stage, doc.kind, visibility,
                   str(ir.get("content_hash", doc.sha256)))
    records = chunk_ir(ir, doc=meta, verdicts=outcome.pages)
    hidden_pages = {f.page for f in findings if f.source == "hidden_text"}
    injected = {r.id for r in records if injection.looks_like_instruction(r.text) or r.page_no in hidden_pages}

    ctx.progress("embedding", 80, f"Embedding {len(records)} chunks (dense + BM25)")
    await store.delete_document(doc.id)
    versions = outcome.versions | {"chunker": CHUNKER_VERSION}
    indexed = await indexer.index_chunks(
        records, startup_name=startup.name, domain=startup.domain, stage=startup.stage, doc_kind=doc.kind,
        versions=versions, injected_ids=injected,
    )
    ctx.progress("indexing", 95, f"Indexed {indexed} chunks in Qdrant")

    flags = []
    if findings or injected:
        flags.append(FLAG_INJECTION)
    if outcome.review_required:
        flags.append(FLAG_REVIEW)
    if outcome.status == "partial":
        flags.append(FLAG_PARTIAL)
    verdicts = {int(v["page_no"]): v for v in outcome.pages}

    with write_tx() as s:
        s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        s.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
        s.flush()
        for page in pages:
            n = int(page["page_no"])
            title = next((r.slide_title for r in records if r.page_no == n and r.slide_title), None)
            s.add(DocumentPage(
                document_id=doc.id, page_no=n, width_px=int(page["width"]), height_px=int(page["height"]),
                image_path=str(images[n].relative_to(folder)) if n in images else None,
                origin=str(page.get("origin", "digital")),
                mean_confidence=float((page.get("confidence") or {}).get("mean_rec") or 1.0),
                review_required=bool(verdicts.get(n, {}).get("review_required")),
                geom_exact=page_exact(page), slide_title=title,
            ))
        for r in records:
            s.add(Chunk(
                id=r.id, cid=r.cid, document_id=r.document_id, startup_id=r.startup_id, seq=r.seq, page_no=r.page_no,
                slide_title=r.slide_title, text=r.text, ctx=r.ctx, bbox=r.bbox, lines=r.lines, geom_exact=r.geom_exact,
                origin=r.origin, conf_min=r.conf_min, conf_mean=r.conf_mean, review=r.review, has_table=r.has_table,
                injection_suspected=r.id in injected, n_tokens=r.n_tokens, visibility=r.visibility,
                embedding_model=versions.get("embed"),
            ))
        row = s.get(Document, doc.id)
        row.status = "ready"
        row.page_count = len(pages)
        row.versions = versions
        row.review_required = outcome.review_required
        row.flags = flags
        row.ocr_ms = outcome.ms
        row.error = None
        startup_row = s.get(Startup, startup.id)
        if FLAG_INJECTION in flags and FLAG_INJECTION not in startup_row.compliance_flags:
            startup_row.compliance_flags = [*startup_row.compliance_flags, FLAG_INJECTION]
        startup_row.updated_at = clock.now()

    return {
        "document_id": doc.id,
        "pages": len(pages),
        "chunks": len(records),
        "indexed": indexed,
        "flags": flags,
        "ocr_ms": outcome.ms,
        "findings": [f.__dict__ for f in findings][:10],
    }
