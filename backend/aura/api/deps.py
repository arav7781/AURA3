"""Request dependencies: who is calling (the viewer), role and plan guards, idempotent writes."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from aura.core import clock
from aura.core.db import read_session
from aura.core.errors import Conflict, Forbidden, PlanRequired, Unauthorized
from aura.core.security import COOKIE_NAME, decode_token
from aura.models import IdempotencyRecord, InvestorProfile, Startup, User, UserSession
from aura.plans import PLANS, STARTUP_FEATURES, STARTUP_QUOTAS


@dataclass(frozen=True)
class Viewer:
    user_id: str
    email: str
    name: str
    role: str
    is_admin: bool
    session_id: str
    plan: str | None = None
    pending_plan: str | None = None
    startup_id: str | None = None

    @property
    def features(self) -> frozenset[str]:
        if self.role == "investor" and self.plan:
            return PLANS[self.plan].features
        return STARTUP_FEATURES

    def has(self, feature: str) -> bool:
        return feature in self.features

    @property
    def quota_limits(self) -> dict[str, int | None]:
        if self.role == "investor" and self.plan:
            plan = PLANS[self.plan]
            return {"copilot": plan.copilot_daily, "sandbox": plan.sandbox_daily}
        return dict(STARTUP_QUOTAS)


def _load_viewer(token: str | None) -> Viewer | None:
    if not token:
        return None
    claims = decode_token(token)
    if not claims:
        return None
    with read_session() as s:
        session = s.get(UserSession, claims.get("sid", ""))
        if session is None or session.revoked_at is not None or session.expires_at <= clock.now():
            return None
        user = s.get(User, claims.get("sub", ""))
        if user is None or user.status != "active" or user.id != session.user_id:
            return None
        plan = pending = startup_id = None
        if user.role == "investor":
            profile = s.get(InvestorProfile, user.id)
            plan = profile.plan if profile else "scout"
            pending = profile.pending_plan if profile else None
        else:
            startup_id = s.scalar(select(Startup.id).where(Startup.owner_user_id == user.id))
        return Viewer(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_admin=user.is_admin,
            session_id=session.id,
            plan=plan,
            pending_plan=pending,
            startup_id=startup_id,
        )


def optional_viewer(request: Request) -> Viewer | None:
    return _load_viewer(request.cookies.get(COOKIE_NAME))


def current_viewer(viewer: Viewer | None = Depends(optional_viewer)) -> Viewer:
    if viewer is None:
        raise Unauthorized("Sign in to continue")
    return viewer


def investor(viewer: Viewer = Depends(current_viewer)) -> Viewer:
    if viewer.role != "investor":
        raise Forbidden("This is for investors", code="FORBIDDEN_ROLE")
    return viewer


def startup_owner(viewer: Viewer = Depends(current_viewer)) -> Viewer:
    if viewer.role != "startup" or viewer.startup_id is None:
        raise Forbidden("This is for startup founders", code="FORBIDDEN_ROLE")
    return viewer


def admin(viewer: Viewer = Depends(current_viewer)) -> Viewer:
    if not viewer.is_admin:
        raise Forbidden("Admins only", code="FORBIDDEN_ROLE")
    return viewer


def require_feature(viewer: Viewer, feature: str) -> None:
    if not viewer.has(feature):
        needed = next((p.id for p in sorted(PLANS.values(), key=lambda p: p.rank) if feature in p.features), None)
        raise PlanRequired(f"Your plan does not include this ({feature})", feature=feature, required_plan=needed)


def idempotency_key(key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100)) -> str:
    return key


def request_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def replay(s: Session, viewer: Viewer, key: str, method: str, path: str, body_hash: str) -> IdempotencyRecord | None:
    """Return the stored response for a retried request, or None if this key is new."""
    record = s.get(IdempotencyRecord, (viewer.user_id, key))
    if record is None:
        return None
    if record.request_hash != body_hash or record.method != method or record.path != path:
        raise Conflict("This Idempotency-Key was used for a different request", code="IDEMPOTENCY_KEY_REUSED")
    return record


def remember(
    s: Session, viewer: Viewer, key: str, method: str, path: str, body_hash: str, status: int, response: Any
) -> None:
    s.add(
        IdempotencyRecord(
            user_id=viewer.user_id,
            key=key,
            method=method,
            path=path,
            request_hash=body_hash,
            status_code=status,
            response=response,
        )
    )
