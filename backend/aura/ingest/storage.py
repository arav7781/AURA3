"""Where document files live: ``data/docs/{document_id}/``.

    source.<ext>     the upload as received
    converted.pdf    office uploads converted by LibreOffice
    ir.json          TitanOCR Document IR + page verdicts + versions
    spatial.md       TitanOCR Spatial Markdown (block-level boxes and confidence, for LLMs and audits)
    pages/{n}.webp   page images at TitanOCR pixel size (for bbox overlays)
"""

from pathlib import Path

from aura.core.config import get_settings

# Magic-byte sniffing: the extension a client sends is never trusted.
SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"%PDF-", ".pdf", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"II*\x00", ".tiff", "image/tiff"),
    (b"MM\x00*", ".tiff", "image/tiff"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".ole", "application/x-ole-storage"),
]


def document_dir(document_id: str) -> Path:
    path = get_settings().data_dir / "docs" / document_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff(head: bytes, filename: str) -> tuple[str, str] | None:
    """Return (suffix, mime) from the file's leading bytes, or None if unsupported."""
    for magic, suffix, mime in SIGNATURES:
        if head.startswith(magic):
            if suffix == ".ole":  # legacy .ppt / .doc: trust the extension only to pick the converter
                ext = Path(filename).suffix.lower()
                return (ext, "application/vnd.ms-powerpoint") if ext in (".ppt", ".doc") else None
            return suffix, mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if head[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return ".heic", "image/heic"
    if head.startswith(b"PK\x03\x04"):
        return _office_kind(head, filename)
    return None


def _office_kind(head: bytes, filename: str) -> tuple[str, str] | None:
    ext = Path(filename).suffix.lower()
    mimes = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".odp": "application/vnd.oasis.opendocument.presentation",
        ".odt": "application/vnd.oasis.opendocument.text",
    }
    return (ext, mimes[ext]) if ext in mimes else None
