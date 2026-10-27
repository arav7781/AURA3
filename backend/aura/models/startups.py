from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aura.models.base import Base, CreatedMixin, IdMixin, UTCDateTime

STAGES = ("pre_seed", "seed", "series_a", "series_b")
# doc_kind of an attachment's chunks in the vector store, so searches and publishing can leave them out
ATTACHMENT_KIND = "attachment"


class Startup(IdMixin, CreatedMixin, Base):
    __tablename__ = "startups"
    __table_args__ = (
        CheckConstraint("stage IN ('pre_seed','seed','series_a','series_b')", name="stage_valid"),
        CheckConstraint("status IN ('draft','published','suspended')", name="status_valid"),
        Index("ix_startups_status_domain", "status", "domain"),
        Index("ix_startups_status_score", "status", "ai_score_x10"),
    )

    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(60), default="Other", nullable=False)
    sub_domain: Mapped[str | None] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(16), default="seed", nullable=False)
    one_liner: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hq_city: Mapped[str | None] = mapped_column(String(80))
    hq_state: Mapped[str | None] = mapped_column(String(80))
    founded_year: Mapped[int | None] = mapped_column(Integer)
    ask_inr: Mapped[int | None] = mapped_column(Integer)
    pre_money_inr: Mapped[int | None] = mapped_column(Integer)
    cin: Mapped[str | None] = mapped_column(String(32))
    mca: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    mca_status: Mapped[str | None] = mapped_column(String(40))
    compliance_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    latest_evaluation_id: Mapped[str | None] = mapped_column(String(36))
    ai_score_x10: Mapped[int | None] = mapped_column(Integer)
    recommendation: Mapped[str | None] = mapped_column(String(32))
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Document(IdMixin, CreatedMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('deck','financials','other','milestone_evidence','generated_deck')", name="kind_valid"
        ),
        CheckConstraint("status IN ('uploaded','processing','ready','failed')", name="status_valid"),
        CheckConstraint("visibility IN ('private','published')", name="visibility_valid"),
        UniqueConstraint("startup_id", "sha256", name="uq_document_content"),
    )

    startup_id: Mapped[str] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(24), default="deck", nullable=False)
    parent_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_dir: Mapped[str] = mapped_column(String(255), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ingest_job_id: Mapped[str | None] = mapped_column(String(36))
    ocr_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    # Set for a file attached to a copilot conversation: a private draft the copilot reads. It is never
    # published, evaluated, mapped or shown to investors, and goes when the conversation is deleted.
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("copilot_threads.id", ondelete="CASCADE"), index=True)


class DocumentPage(Base):
    __tablename__ = "document_pages"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    page_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(16), nullable=False)  # digital | ocr | mixed
    mean_confidence: Mapped[float | None] = mapped_column(Float)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    geom_exact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    slide_title: Mapped[str | None] = mapped_column(String(300))


class Chunk(CreatedMixin, Base):
    """Chunk metadata. The id equals the Qdrant point id; vectors live only in Qdrant."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "seq", name="uq_chunk_seq"),
        CheckConstraint("visibility IN ('public','dao','private')", name="visibility_valid"),
        Index("ix_chunks_doc_page", "document_id", "page_no"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cid: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)  # short citation id, e.g. c:7f3k2a
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    startup_id: Mapped[str] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_title: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ctx: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    bbox: Mapped[list[float]] = mapped_column(JSON, nullable=False)  # normalised [x0,y0,x1,y1]
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    geom_exact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    conf_min: Mapped[float] = mapped_column(Float, nullable=False)
    conf_mean: Mapped[float] = mapped_column(Float, nullable=False)
    review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_table: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    n_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="dao", nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    proj_x: Mapped[float | None] = mapped_column(Float)
    proj_y: Mapped[float | None] = mapped_column(Float)
    proj_v: Mapped[int | None] = mapped_column(Integer)


class Evaluation(IdMixin, CreatedMixin, Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','complete','failed')", name="status_valid"),
        CheckConstraint("source IN ('live','seed_cache')", name="source_valid"),
        CheckConstraint("visibility IN ('private','published')", name="visibility_valid"),
        UniqueConstraint("startup_id", "version", name="uq_evaluation_version"),
    )

    startup_id: Mapped[str] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    stage: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    overall_score_x10: Mapped[int | None] = mapped_column(Integer)
    recommendation: Mapped[str | None] = mapped_column(String(32))
    evidence_version: Mapped[int | None] = mapped_column(Integer)
    rubric_version: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(80))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), default="live", nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
