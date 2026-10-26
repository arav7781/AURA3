from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from aura import quotas
from aura.api.deps import Viewer, current_viewer, idempotency_key, investor, remember, replay, request_hash
from aura.core import clock
from aura.core.db import write_tx
from aura.ledger import service as ledger
from aura.ledger.grants import activate_plan, ensure_current_period
from aura.models import InvestorProfile, LedgerAccount, LedgerEntry, LedgerTx, Startup, User
from aura.plans import FEATURES, PLANS

router = APIRouter(prefix="/api/me", tags=["me"])


def _plan_block(s: Session, viewer: Viewer) -> dict[str, Any] | None:
    if viewer.role != "investor":
        return None
    profile = s.get(InvestorProfile, viewer.user_id)
    plan = PLANS[profile.plan if profile else "scout"]
    return {
        "id": plan.id,
        "name": plan.name,
        "price_inr_month": plan.price_inr_month,
        "monthly_ac": plan.monthly_ac,
        "pending_plan": profile.pending_plan if profile else None,
        "period_index": profile.period_index if profile else 0,
        "next_grant_at": clock.iso(profile.next_grant_at) if profile and profile.next_grant_at else None,
    }


def _balances(s: Session, viewer: Viewer) -> dict[str, int]:
    if viewer.role == "investor":
        return ledger.user_balances(s, viewer.user_id)
    if viewer.startup_id:
        return {"available": ledger.balance(s, ledger.startup_wallet(s, viewer.startup_id)), "locked": 0, "escrowed": 0}
    return {"available": 0, "locked": 0, "escrowed": 0}


def me_payload(s: Session, viewer: Viewer) -> dict[str, Any]:
    user = s.get(User, viewer.user_id)
    if viewer.role == "investor":
        ensure_current_period(s, user)
    # Re-read the plan after a possible period roll.
    profile = s.get(InvestorProfile, viewer.user_id) if viewer.role == "investor" else None
    plan_id = profile.plan if profile else None
    features = sorted(PLANS[plan_id].features) if plan_id else sorted(viewer.features)
    limits = (
        {"copilot": PLANS[plan_id].copilot_daily, "sandbox": PLANS[plan_id].sandbox_daily}
        if plan_id
        else viewer.quota_limits
    )
    startup = None
    if viewer.startup_id:
        row = s.get(Startup, viewer.startup_id)
        if row is not None:
            startup = {"id": row.id, "slug": row.slug, "name": row.name, "status": row.status}
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "is_admin": user.is_admin},
        "plan": _plan_block(s, viewer),
        "entitlements": {
            "features": features,
            "feature_labels": {f: FEATURES[f] for f in features},
            "quotas": quotas.snapshot(s, viewer.user_id, limits),
        },
        "balances": _balances(s, viewer),
        "startup": startup,
    }


@router.get("")
def get_me(viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    with write_tx() as s:
        return me_payload(s, viewer)


class PlanIn(BaseModel):
    plan: Literal["scout", "angel", "syndicate"]


@router.post("/plan")
def change_plan(
    body: PlanIn, request: Request, viewer: Viewer = Depends(investor), key: str = Depends(idempotency_key)
) -> dict[str, Any]:
    body_hash = request_hash(body.model_dump())
    with write_tx() as s:
        prior = replay(s, viewer, key, "POST", request.url.path, body_hash)
        if prior is not None:
            return prior.response
        user = s.get(User, viewer.user_id)
        result = activate_plan(s, user, body.plan)
        result["balances"] = ledger.user_balances(s, viewer.user_id)
        remember(s, viewer, key, "POST", request.url.path, body_hash, 200, result)
        return result


@router.get("/wallet")
def wallet(viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    with write_tx() as s:
        if viewer.role == "investor":
            ensure_current_period(s, s.get(User, viewer.user_id))
        return {"balances": _balances(s, viewer), "plan": _plan_block(s, viewer)}


def _account_codes(viewer: Viewer) -> dict[str, str]:
    if viewer.role == "investor":
        return {f"user:{viewer.user_id}:wallet": "wallet", f"user:{viewer.user_id}:locked": "locked"}
    return {f"startup:{viewer.startup_id}:wallet": "startup"} if viewer.startup_id else {}


@router.get("/ledger")
def ledger_history(
    viewer: Viewer = Depends(current_viewer),
    cursor: int | None = Query(default=None, description="Return entries older than this entry id"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    codes = _account_codes(viewer)
    with write_tx() as s:
        query = (
            select(LedgerEntry, LedgerTx, LedgerAccount.code)
            .join(LedgerTx, LedgerTx.id == LedgerEntry.tx_id)
            .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
            .where(LedgerAccount.code.in_(codes))
            .order_by(LedgerEntry.id.desc())
            .limit(limit + 1)
        )
        if cursor is not None:
            query = query.where(LedgerEntry.id < cursor)
        rows = s.execute(query).all()
    items = [
        {
            "id": entry.id,
            "tx_id": tx.id,
            "kind": tx.kind,
            "account": codes[code],
            "amount_minor": entry.amount_minor,
            "memo": tx.memo,
            "ref_type": tx.ref_type,
            "ref_id": tx.ref_id,
            "created_at": clock.iso(entry.created_at),
        }
        for entry, tx, code in rows[:limit]
    ]
    return {"items": items, "next_cursor": items[-1]["id"] if len(rows) > limit else None}
