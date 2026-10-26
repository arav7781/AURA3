from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aura.models.base import Base, CreatedMixin, IdMixin, UTCDateTime


class User(IdMixin, CreatedMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lower"),
        CheckConstraint("role IN ('investor','startup')", name="role_valid"),
        CheckConstraint("status IN ('active','suspended')", name="status_valid"),
    )

    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UserSession(CreatedMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user", "user_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 256-bit random sid
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class ApiKey(IdMixin, CreatedMixin, Base):
    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    key_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[str] = mapped_column(String(40), default="read", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"
    __table_args__ = (
        CheckConstraint("plan IN ('scout','angel','syndicate')", name="plan_valid"),
        CheckConstraint("pending_plan IS NULL OR pending_plan IN ('scout','angel','syndicate')", name="pending_valid"),
        CheckConstraint("reputation_milli BETWEEN 500 AND 2000", name="reputation_range"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), default="scout", nullable=False)
    period_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_grant_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    pending_plan: Mapped[str | None] = mapped_column(String(16))
    reputation_milli: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    thesis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PlanPeriod(Base):
    __tablename__ = "plan_periods"
    __table_args__ = (CheckConstraint("granted_minor >= 0", name="granted_nonneg"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    period_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (CheckConstraint("count >= 0", name="count_nonneg"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    feature: Mapped[str] = mapped_column(String(32), primary_key=True)
    window_start: Mapped[str] = mapped_column(String(10), primary_key=True)  # IST date YYYY-MM-DD
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
