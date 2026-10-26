"""AuraCoin ledger tables: double-entry, append-only (enforced by triggers in the baseline migration)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aura.core import clock
from aura.models.base import Base, UTCDateTime

ACCOUNT_KINDS = ("issuance", "fees", "wallet", "locked", "startup", "escrow")


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint("kind IN ('issuance','fees','wallet','locked','startup','escrow')", name="kind_valid"),
        CheckConstraint(
            "(kind = 'issuance' AND balance_minor <= 0) OR (kind <> 'issuance' AND balance_minor >= 0)",
            name="balance_sign",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    owner_startup_id: Mapped[str | None] = mapped_column(ForeignKey("startups.id", ondelete="RESTRICT"), index=True)
    proposal_id: Mapped[str | None] = mapped_column(String(36), index=True)
    balance_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now, nullable=False)


class LedgerTx(Base):
    __tablename__ = "ledger_txs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    legs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    memo: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now, nullable=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_minor <> 0", name="amount_nonzero"),
        Index("ix_entries_account", "account_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tx_id: Mapped[int] = mapped_column(ForeignKey("ledger_txs.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now, nullable=False)
