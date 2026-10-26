from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aura.models.base import Base, CreatedMixin, IdMixin, UTCDateTime


class Review(IdMixin, CreatedMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("startup_id", "investor_id", name="uq_review_once"),
        CheckConstraint("team BETWEEN 1 AND 5 AND market BETWEEN 1 AND 5", name="scores_a"),
        CheckConstraint("product BETWEEN 1 AND 5 AND traction BETWEEN 1 AND 5", name="scores_b"),
        CheckConstraint("length(note) <= 2000", name="note_length"),
    )

    startup_id: Mapped[str] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team: Mapped[int] = mapped_column(Integer, nullable=False)
    market: Mapped[int] = mapped_column(Integer, nullable=False)
    product: Mapped[int] = mapped_column(Integer, nullable=False)
    traction: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Ranking(CreatedMixin, Base):
    """An investor's personal top-10; saving replaces the whole list in one transaction."""

    __tablename__ = "rankings"
    __table_args__ = (
        UniqueConstraint("investor_id", "position", name="uq_ranking_position"),
        CheckConstraint("position BETWEEN 1 AND 10", name="position_range"),
    )

    investor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    startup_id: Mapped[str] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(280))
