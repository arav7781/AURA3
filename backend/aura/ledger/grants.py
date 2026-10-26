"""Plan grants: the only way AuraCoin enters circulation.

- Every investor gets a one-time 500 AC welcome grant at registration (usable once on a paid plan).
- Activating a paid plan from Scout starts a 30-day period and grants that plan's monthly AC.
- Upgrading mid-period tops up the difference, so a period never grants more than the plan reached.
- Downgrades take effect when the period ends. Renewals happen lazily (``ensure_current_period``).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from aura.core import clock
from aura.core.errors import AppError, Forbidden
from aura.ledger import service as ledger
from aura.models import InvestorProfile, PlanPeriod, User
from aura.plans import MAX_CATCH_UP_PERIODS, PLAN_PERIOD, PLANS, ac_to_minor


def grant_welcome(s: Session, user_id: str) -> None:
    amount = ac_to_minor(PLANS["scout"].welcome_ac)
    ledger.post_tx(
        s,
        kind="welcome_grant",
        key=f"welcome:{user_id}",
        legs=[(ledger.issuance(s), -amount), (ledger.wallet(s, user_id), amount)],
        actor_user_id=user_id,
        ref_type="user",
        ref_id=user_id,
        memo="Welcome credit",
    )


def _profile(s: Session, user: User) -> InvestorProfile:
    if user.role != "investor":
        raise Forbidden("Only investors have plans", code="FORBIDDEN_ROLE")
    profile = s.get(InvestorProfile, user.id)
    if profile is None:
        profile = InvestorProfile(user_id=user.id, plan="scout")
        s.add(profile)
        s.flush()
    return profile


def _grant(s: Session, user_id: str, period: PlanPeriod, amount_minor: int, *, kind: str, key: str, memo: str) -> None:
    if amount_minor <= 0:
        return
    ledger.post_tx(
        s,
        kind=kind,
        key=key,
        legs=[(ledger.issuance(s), -amount_minor), (ledger.wallet(s, user_id), amount_minor)],
        actor_user_id=user_id,
        ref_type="plan_period",
        ref_id=f"{user_id}:{period.period_index}",
        memo=memo,
    )
    period.granted_minor += amount_minor


def _start_period(s: Session, profile: InvestorProfile, plan_id: str, start: datetime) -> PlanPeriod:
    profile.period_index += 1
    profile.plan = plan_id
    profile.period_started_at = start
    profile.next_grant_at = start + PLAN_PERIOD
    period = PlanPeriod(
        user_id=profile.user_id,
        period_index=profile.period_index,
        plan=plan_id,
        granted_minor=0,
        started_at=start,
        ends_at=start + PLAN_PERIOD,
    )
    s.add(period)
    s.flush()
    plan = PLANS[plan_id]
    _grant(
        s,
        profile.user_id,
        period,
        ac_to_minor(plan.monthly_ac),
        kind="plan_grant",
        key=f"grant:{profile.user_id}:{period.period_index}",
        memo=f"{plan.name} plan — period {period.period_index}",
    )
    return period


def ensure_current_period(s: Session, user: User) -> InvestorProfile:
    """Roll any finished periods forward: apply a pending downgrade, then grant the next period."""
    profile = _profile(s, user)
    now = clock.now()
    rolled = 0
    while profile.next_grant_at is not None and now >= profile.next_grant_at and rolled < MAX_CATCH_UP_PERIODS:
        boundary = profile.next_grant_at
        next_plan = profile.pending_plan or profile.plan
        profile.pending_plan = None
        if next_plan == "scout":
            profile.plan = "scout"
            profile.next_grant_at = None
            profile.period_started_at = None
            break
        _start_period(s, profile, next_plan, boundary)
        rolled += 1
    return profile


def activate_plan(s: Session, user: User, plan_id: str) -> dict:
    """Switch plan (demo: no payment). Returns a summary of what changed."""
    if plan_id not in PLANS:
        raise AppError("Unknown plan", code="UNKNOWN_PLAN", plan=plan_id)
    profile = ensure_current_period(s, user)
    current = PLANS[profile.plan]
    target = PLANS[plan_id]
    if target.id == current.id:
        cancelled = profile.pending_plan is not None
        profile.pending_plan = None
        return {"plan": profile.plan, "effective": "now", "granted_minor": 0, "cancelled_pending": cancelled}

    if target.rank < current.rank:
        profile.pending_plan = target.id
        return {
            "plan": profile.plan,
            "pending_plan": target.id,
            "effective": "period_end",
            "effective_at": clock.iso(profile.next_grant_at) if profile.next_grant_at else None,
            "granted_minor": 0,
        }

    profile.pending_plan = None
    if current.id == "scout":
        period = _start_period(s, profile, target.id, clock.now())
        return {"plan": target.id, "effective": "now", "granted_minor": period.granted_minor}

    period = s.scalar(
        select(PlanPeriod).where(PlanPeriod.user_id == user.id, PlanPeriod.period_index == profile.period_index)
    )
    if period is None:  # defensive: a paid plan always has an open period
        period = _start_period(s, profile, target.id, clock.now())
        return {"plan": target.id, "effective": "now", "granted_minor": period.granted_minor}
    top_up = ac_to_minor(target.monthly_ac) - period.granted_minor
    before = period.granted_minor
    _grant(
        s,
        user.id,
        period,
        top_up,
        kind="plan_topup",
        key=f"topup:{user.id}:{period.period_index}:{target.id}",
        memo=f"Upgrade to {target.name} — period {period.period_index}",
    )
    period.plan = target.id
    profile.plan = target.id
    return {"plan": target.id, "effective": "now", "granted_minor": period.granted_minor - before}
