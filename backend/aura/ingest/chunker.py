"""Layout-aware chunking of a TitanOCR Document IR (read as plain JSON, so IR 1.8 and 1.9 both work).

Rules (``deck-1``):
- Text repeated on at least half of the pages (running headers and footers such as
  "Company · CIN · 4 / 11") and bare page numbers are dropped, so they don't pollute every chunk.
- The slide title is the first non-running ``header`` block (else a short first line).
- Chunks never cross a page. A page longer than ``MAX_TOKENS`` is split at block boundaries.
- Tables are rendered as Markdown tables.
- Every chunk keeps provenance: page, normalised union bbox, per-line boxes, confidence, origin
  (digital text layer vs OCR) and a review flag, so any citation can be shown on the page image.
"""

import base64
import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from aura.core.ids import stable_id
from aura.ingest.geometry import Box, page_exact, to_norm, union

CHUNKER_VERSION = "deck-1"
MAX_TOKENS = 350
NO_TEXT_BLOCKS = {"connector", "rule"}
EDGE = 0.08  # top/bottom band (fraction of page height) where running text lives
LOW_CONFIDENCE = 0.9
_PAGE_NUMBER = re.compile(r"^\s*(page\s*)?\d+\s*(/|of)\s*\d+\s*$", re.IGNORECASE)

STAGE_LABELS = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B+"}
KIND_LABELS = {"deck": "pitch deck", "financials": "financials", "generated_deck": "pitch deck (AI-built)"}


@dataclass(frozen=True)
class DocMeta:
    document_id: str
    startup_id: str
    startup_name: str
    domain: str
    stage: str
    doc_kind: str
    visibility: str
    content_hash: str


@dataclass
class ChunkRecord:
    id: str
    cid: str
    document_id: str
    startup_id: str
    seq: int
    page_no: int
    page_count: int
    slide_title: str | None
    text: str
    ctx: str
    bbox: list[float]
    lines: list[dict[str, Any]] = field(default_factory=list)
    geom_exact: bool = True
    origin: str = "digital"
    conf_min: float = 1.0
    conf_mean: float = 1.0
    review: bool = False
    has_table: bool = False
    n_tokens: int = 0
    visibility: str = "dao"

    @property
    def embed_text(self) -> str:
        """What gets embedded (dense and sparse): the context header, then the chunk text."""
        return f"{self.ctx}\n\n{self.text}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def citation_id(chunk_id: str) -> str:
    digest = hashlib.sha1(chunk_id.encode()).digest()
    return "c:" + base64.b32encode(digest).decode().lower()[:7]


def _norm_key(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.lower())
    return re.sub(r"\d+", "#", collapsed).strip(" ·|-—–:")


def _sorted_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(lines, key=lambda ln: ((ln["bbox"][1] + ln["bbox"][3]) / 2, ln["bbox"][0]))


def _near_edge(block: dict[str, Any], page: dict[str, Any]) -> bool:
    height = float(page.get("height") or 1)
    top, bottom = block["bbox"][1] / height, block["bbox"][3] / height
    return top < EDGE or bottom > 1 - EDGE


def running_keys(pages: list[dict[str, Any]]) -> set[str]:
    """Line texts that repeat near the page edges on at least half the pages (3+ page documents only)."""
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        keys = set()
        for block in page.get("blocks", ()):
            if block["type"] in ("header", "footer") or _near_edge(block, page):
                for line in block.get("lines") or ():
                    key = _norm_key(line.get("text", ""))
                    if key:
                        keys.add(key)
        counts.update(keys)
    threshold = max(3, math.ceil(0.5 * len(pages)))
    return {key for key, n in counts.items() if n >= threshold}


def table_markdown(table: dict[str, Any]) -> str:
    rows, cols = int(table.get("n_rows") or 0), int(table.get("n_cols") or 0)
    if rows == 0 or cols == 0:
        return ""
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in table.get("cells", ()):
        r, c = int(cell["row"]), int(cell["col"])
        if r < rows and c < cols:
            grid[r][c] = " ".join(str(cell.get("text", "")).split()).replace("|", "\\|")
    header_rows = max(1, len(table.get("header_rows") or ()) or 1)
    lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * cols]
    for r in range(header_rows, rows):
        lines.append("| " + " | ".join(grid[r]) + " |")
    if header_rows > 1:  # extra header rows become leading body rows rather than being lost
        lines[2:2] = ["| " + " | ".join(grid[r]) + " |" for r in range(1, header_rows)]
    return "\n".join(lines)


@dataclass
class _Piece:
    text: str
    lines: list[dict[str, Any]]
    block_box: Box
    confidences: list[float]
    origins: set[str]
    is_table: bool


def _piece(block: dict[str, Any], page: dict[str, Any], running: set[str]) -> _Piece | None:
    table = block.get("table")
    if table and table.get("cells"):
        text = table_markdown(table)
        cells = table["cells"]
        lines = [
            {"t": str(c.get("text", "")), "b": list(to_norm(c["bbox"], page)), "c": round(float(c.get("confidence", 1)), 4),
             "o": str(c.get("origin", "digital"))}
            for c in cells
            if str(c.get("text", "")).strip()
        ]
        confidences = [float(c.get("confidence", 1.0)) for c in cells] or [float(block.get("confidence", 1.0))]
        origins = {str(c.get("origin", "digital")) for c in cells} or {str(block.get("origin", "digital"))}
        return _Piece(text, lines, to_norm(block["bbox"], page), confidences, origins, True) if text else None

    kept = [
        ln
        for ln in _sorted_lines(list(block.get("lines") or ()))
        if ln.get("text", "").strip() and _norm_key(ln["text"]) not in running and not _PAGE_NUMBER.match(ln["text"])
    ]
    if not kept:
        return None
    lines = [
        {"t": ln["text"], "b": list(to_norm(ln["bbox"], page)), "c": round(float(ln.get("confidence", 1)), 4),
         "o": str(ln.get("origin", "digital"))}
        for ln in kept
    ]
    return _Piece(
        text="\n".join(ln["text"].strip() for ln in kept),
        lines=lines,
        block_box=union([tuple(ln["b"]) for ln in lines]),  # type: ignore[misc]
        confidences=[float(ln.get("confidence", 1.0)) for ln in kept],
        origins={str(ln.get("origin", "digital")) for ln in kept},
        is_table=False,
    )


def chunk_ir(ir: dict[str, Any], *, doc: DocMeta, verdicts: list[dict[str, Any]] | None = None,
             max_tokens: int = MAX_TOKENS) -> list[ChunkRecord]:
    pages = list(ir.get("pages") or ())
    page_count = int(ir.get("page_count") or len(pages))
    running = running_keys(pages)
    review_pages = {int(v["page_no"]) for v in verdicts or () if v.get("review_required")}
    stage_label = STAGE_LABELS.get(doc.stage, doc.stage)
    kind_label = KIND_LABELS.get(doc.doc_kind, doc.doc_kind)
    records: list[ChunkRecord] = []

    for page in pages:
        page_no = int(page["page_no"])
        exact = page_exact(page)
        title: str | None = None
        pieces: list[_Piece] = []
        for block in sorted(page.get("blocks", ()), key=lambda b: b.get("reading_order", 0)):
            if block["type"] in NO_TEXT_BLOCKS:
                continue
            piece = _piece(block, page, running)
            if piece is None:
                continue
            if title is None and block["type"] == "header":
                title = piece.text.split("\n", 1)[0][:200]
            pieces.append(piece)
        if not pieces:
            continue
        if title is None:
            first = pieces[0].text.split("\n", 1)[0]
            title = first[:200] if len(first) <= 90 and not pieces[0].is_table else None

        groups: list[list[_Piece]] = []
        current: list[_Piece] = []
        tokens = 0
        for piece in pieces:
            size = estimate_tokens(piece.text)
            if current and tokens + size > max_tokens:
                groups.append(current)
                current, tokens = [], 0
            current.append(piece)
            tokens += size
        if current:
            groups.append(current)

        for idx, group in enumerate(groups):
            text = "\n".join(p.text for p in group).strip()
            confidences = [c for p in group for c in p.confidences]
            origins = set().union(*(p.origins for p in group))
            origin = "digital" if origins <= {"digital"} else ("ocr" if "digital" not in origins else "mixed")
            conf_min = round(min(confidences), 4)
            chunk_id = stable_id(doc.content_hash, CHUNKER_VERSION, page_no, idx)
            ctx = f"{doc.startup_name} · {doc.domain} · {stage_label} · {kind_label} p.{page_no}/{page_count}"
            if title:
                ctx += f" · {title}"
            records.append(
                ChunkRecord(
                    id=chunk_id,
                    cid=citation_id(chunk_id),
                    document_id=doc.document_id,
                    startup_id=doc.startup_id,
                    seq=len(records),
                    page_no=page_no,
                    page_count=page_count,
                    slide_title=title,
                    text=text,
                    ctx=ctx,
                    bbox=list(union([p.block_box for p in group])),
                    lines=[ln for p in group for ln in p.lines],
                    geom_exact=exact,
                    origin=origin,
                    conf_min=conf_min,
                    conf_mean=round(sum(confidences) / len(confidences), 4),
                    review=page_no in review_pages or (origin != "digital" and conf_min < LOW_CONFIDENCE),
                    has_table=any(p.is_table for p in group),
                    n_tokens=estimate_tokens(text),
                    visibility=doc.visibility,
                )
            )
    return records
