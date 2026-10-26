import json
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from aura.core.config import get_settings
from aura.core.db import read_session
from aura.models import AppState, InvestorProfile, LedgerAccount, Startup
from aura.plans import FEATURES, PLANS, STARTUP_QUOTAS, SUCCESS_FEE_BPS

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/plans")
def plans() -> dict[str, Any]:
    return {
        "plans": [p.as_dict() for p in sorted(PLANS.values(), key=lambda p: p.rank)],
        "features": FEATURES,
        "currency": "INR",
        "demo_payments": True,
        "startup": {"price_inr_month": 0, "success_fee_bps": SUCCESS_FEE_BPS, "quotas": STARTUP_QUOTAS},
        "auracoin": {
            "unit": "AC",
            "closed_loop": True,
            "transferable": False,
            "redeemable": False,
            "note": "AuraCoin is granted with a plan and used inside AURA-3 only. It cannot be bought, sold or cashed out.",
        },
    }


@router.get("/public/stats")
def stats() -> dict[str, Any]:
    with read_session() as s:
        published = s.scalar(select(func.count()).select_from(Startup).where(Startup.status == "published")) or 0
        investors = s.scalar(select(func.count()).select_from(InvestorProfile)) or 0
        issuance = s.scalar(select(LedgerAccount.balance_minor).where(LedgerAccount.code == "sys:issuance")) or 0
        domains = s.execute(
            select(Startup.domain, func.count()).where(Startup.status == "published").group_by(Startup.domain)
        ).all()
    return {
        "startups_published": published,
        "investors": investors,
        "ac_supply_minor": -int(issuance),
        "domains": {d: n for d, n in domains},
    }


@router.get("/public/demo-accounts")
def demo_accounts() -> dict[str, Any]:
    if not get_settings().demo_mode:
        return {"enabled": False, "accounts": []}
    with read_session() as s:
        row = s.get(AppState, "demo_accounts")
    data = json.loads(row.value) if row else {}
    # Written by the seeder: every demo login shares one password, shown on the sign-in page in demo mode.
    return {"enabled": True, "accounts": data.get("accounts", []), "password": data.get("password")}


@router.get("/health")
def health() -> dict[str, Any]:
    from aura.api.app import service_status

    return {"status": "ok", "version": "2.0.0", **service_status()}
