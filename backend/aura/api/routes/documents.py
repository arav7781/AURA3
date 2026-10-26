import hashlib
import shutil
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from aura.access import is_owner, visible_chunk, visible_document, visible_startup
from aura.api.deps import Viewer, current_viewer
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.errors import AppError, Conflict, NotFound
from aura.core.jobs import start_job
from aura.ingest.pipeline import ingest_document
from aura.ingest.storage import document_dir, sniff
from aura.models import Chunk, Document, DocumentPage
from aura.rag import store

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 25 << 20
KINDS = {"deck", "financials", "other", "milestone_evidence"}
_OFFICE_PARTS = {".pptx": "ppt/presentation.xml", ".docx": "word/document.xml"}


def _check_office_archive(data: bytes, suffix: str) -> None:
    required = _OFFICE_PARTS.get(suffix)
    if required is None:
        return
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise AppError("This file is not a valid office document", code="UNSUPPORTED_FILE", status=415) from exc
    if required not in names:
        raise AppError("This file is not a valid office document", code="UNSUPPORTED_FILE", status=415)


def document_out(doc: Document, pages: list[DocumentPage] | None = None, chunk_count: int | None = None) -> dict:
    out: dict[str, Any] = {
        "id": doc.id,
        "startup_id": doc.startup_id,
        "kind": doc.kind,
        "filename": doc.filename,
        "mime": doc.mime,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "visibility": doc.visibility,
        "page_count": doc.page_count,
        "review_required": doc.review_required,
        "flags": doc.flags,
        "versions": doc.versions,
        "ocr_ms": doc.ocr_ms,
        "error": doc.error,
        "job_id": doc.ingest_job_id,
        "created_at": clock.iso(doc.created_at),
    }
    if pages is not None:
        out["pages"] = [
            {
                "page_no": p.page_no,
                "width": p.width_px,
                "height": p.height_px,
                "origin": p.origin,
                "mean_confidence": p.mean_confidence,
                "review_required": p.review_required,
                "geom_exact": p.geom_exact,
                "slide_title": p.slide_title,
                "image_url": f"/api/documents/{doc.id}/pages/{p.page_no}/image",
            }
            for p in pages
        ]
    if chunk_count is not None:
        out["chunk_count"] = chunk_count
    return out


def chunk_out(chunk: Chunk, *, with_lines: bool = True) -> dict:
    out = {
        "id": chunk.id,
        "cid": chunk.cid,
        "document_id": chunk.document_id,
        "startup_id": chunk.startup_id,
        "page_no": chunk.page_no,
        "slide_title": chunk.slide_title,
        "text": chunk.text,
        "ctx": chunk.ctx,
        "bbox": chunk.bbox,
        "geom_exact": chunk.geom_exact,
        "origin": chunk.origin,
        "conf_min": chunk.conf_min,
        "conf_mean": chunk.conf_mean,
        "review": chunk.review,
        "has_table": chunk.has_table,
        "injection_suspected": chunk.injection_suspected,
        "proj": {"x": chunk.proj_x, "y": chunk.proj_y} if chunk.proj_x is not None else None,
    }
    if with_lines:
        out["lines"] = chunk.lines
    return out


@router.post("/startups/{startup_id}/documents", status_code=202)
async def upload_document(
    startup_id: str,
    file: UploadFile = File(...),
    kind: str = Form("deck"),
    viewer: Viewer = Depends(current_viewer),
) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    if not is_owner(viewer, startup):
        raise NotFound("Startup not found")
    if kind not in KINDS:
        raise AppError("Unknown document kind", code="INVALID_KIND", kinds=sorted(KINDS))
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("Files are limited to 25 MB", code="FILE_TOO_LARGE", status=413)
    filename = (file.filename or "document").replace("/", "_").replace("\\", "_")[:200]
    detected = sniff(data[:64], filename)
    if detected is None:
        raise AppError("Upload a PDF, PPTX, DOCX or an image (PNG, JPEG, TIFF, WebP, HEIC)",
                       code="UNSUPPORTED_FILE", status=415)
    suffix, mime = detected
    _check_office_archive(data, suffix)
    sha = hashlib.sha256(data).hexdigest()

    with write_tx() as s:
        existing = s.scalar(select(Document).where(Document.startup_id == startup.id, Document.sha256 == sha))
        if existing is not None:
            raise Conflict("This file was already uploaded", code="DUPLICATE_DOCUMENT", document_id=existing.id)
        doc = Document(
            startup_id=startup.id, uploaded_by=viewer.user_id, kind=kind, filename=filename, mime=mime,
            size_bytes=len(data), sha256=sha, storage_dir="", status="uploaded",
            visibility="published" if startup.status == "published" else "private",
        )
        s.add(doc)
        s.flush()
        folder = document_dir(doc.id)
        doc.storage_dir = str(folder.relative_to(folder.parents[1]))
        (folder / f"source{suffix}").write_bytes(data)
        document_id = doc.id

    job_id = start_job(
        "ingest",
        lambda ctx: ingest_document(ctx, document_id),
        owner_user_id=viewer.user_id,
        subject_type="document",
        subject_id=document_id,
        payload={"filename": filename},
    )
    with write_tx() as s:
        s.get(Document, document_id).ingest_job_id = job_id
    return {"document_id": document_id, "job_id": job_id, "events_url": f"/api/jobs/{job_id}/events"}


@router.get("/startups/{startup_id}/documents")
def list_documents(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    owner = is_owner(viewer, startup)
    with read_session() as s:
        query = select(Document).where(Document.startup_id == startup.id).order_by(Document.created_at.desc())
        if not owner:
            query = query.where(Document.visibility == "published", Document.status == "ready")
        docs = s.scalars(query).all()
    return {"items": [document_out(d) for d in docs], "can_open": owner or viewer.has("deck_access")}


@router.get("/documents/{document_id}")
def get_document(document_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    doc, _ = visible_document(viewer, document_id)
    with read_session() as s:
        pages = s.scalars(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                          .order_by(DocumentPage.page_no)).all()
        count = s.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id))
    return document_out(doc, list(pages), count)


@router.get("/documents/{document_id}/pages/{page_no}/image")
def page_image(document_id: str, page_no: int, viewer: Viewer = Depends(current_viewer)) -> FileResponse:
    doc, _ = visible_document(viewer, document_id)
    path = document_dir(doc.id) / "pages" / f"{page_no}.webp"
    if not path.is_file():
        raise NotFound("Page not found")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/documents/{document_id}/pages/{page_no}/chunks")
def page_chunks(document_id: str, page_no: int, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    doc, _ = visible_document(viewer, document_id)
    with read_session() as s:
        chunks = s.scalars(select(Chunk).where(Chunk.document_id == doc.id, Chunk.page_no == page_no)
                           .order_by(Chunk.seq)).all()
    return {"items": [chunk_out(c) for c in chunks]}


@router.get("/chunks/{ref}")
def get_chunk(ref: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    return chunk_out(visible_chunk(viewer, ref))


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, viewer: Viewer = Depends(current_viewer)) -> None:
    doc, startup = visible_document(viewer, document_id)
    if not is_owner(viewer, startup):
        raise NotFound("Document not found")
    await store.delete_document(doc.id)
    with write_tx() as s:
        row = s.get(Document, doc.id)
        if row is not None:
            s.delete(row)
    shutil.rmtree(document_dir(doc.id), ignore_errors=True)
