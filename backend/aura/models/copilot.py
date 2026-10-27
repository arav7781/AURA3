from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aura.models.base import Base, CreatedMixin, IdMixin, UTCDateTime


class CopilotThread(IdMixin, CreatedMixin, Base):
    """A conversation with the copilot. Private to its user."""

    __tablename__ = "copilot_threads"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), default="New chat", nullable=False)
    startup_id: Mapped[str | None] = mapped_column(ForeignKey("startups.id", ondelete="SET NULL"))  # opened from a startup page
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class CopilotMessage(IdMixin, CreatedMixin, Base):
    """One turn. Assistant turns keep the tool calls they made (``parts``) so the UI can redraw their cards,
    and the citations the answer used."""

    __tablename__ = "copilot_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "seq", name="uq_message_seq"),
        CheckConstraint("role IN ('user','assistant')", name="role_valid"),
        CheckConstraint("status IN ('done','failed','cancelled')", name="status_valid"),
    )

    thread_id: Mapped[str] = mapped_column(ForeignKey("copilot_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    citations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), default="done", nullable=False)
