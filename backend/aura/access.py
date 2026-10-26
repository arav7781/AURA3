"""Who may see which startup data. Private resources are reported as missing (404), not forbidden."""

from aura.api.deps import Viewer, require_feature
from aura.core.db import read_session
from aura.core.errors import NotFound
from aura.models import Chunk, Document, Startup


def is_owner(viewer: Viewer, startup: Startup) -> bool:
    return viewer.is_admin or (viewer.role == "startup" and viewer.startup_id == startup.id)


def visible_startup(viewer: Viewer, startup_id: str) -> Startup:
    with read_session() as s:
        startup = s.get(Startup, startup_id) or s.query(Startup).filter(Startup.slug == startup_id).one_or_none()
    if startup is None or (startup.status != "published" and not is_owner(viewer, startup)):
        raise NotFound("Startup not found")
    return startup


def visible_document(viewer: Viewer, document_id: str) -> tuple[Document, Startup]:
    with read_session() as s:
        doc = s.get(Document, document_id)
        startup = s.get(Startup, doc.startup_id) if doc else None
    if doc is None or startup is None:
        raise NotFound("Document not found")
    if is_owner(viewer, startup):
        return doc, startup
    if viewer.role != "investor" or startup.status != "published" or doc.visibility != "published":
        raise NotFound("Document not found")
    require_feature(viewer, "deck_access")
    return doc, startup


def visible_chunk(viewer: Viewer, ref: str) -> Chunk:
    with read_session() as s:
        chunk = s.get(Chunk, ref) or s.query(Chunk).filter(Chunk.cid == ref).one_or_none()
    if chunk is None:
        raise NotFound("Passage not found")
    visible_document(viewer, chunk.document_id)
    return chunk
