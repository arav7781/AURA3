"""Daily usage quotas (copilot messages, sandbox runs, evaluations, deck builds), reset at midnight IST."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from aura.core import clock
from aura.core.errors import QuotaExceeded
from aura.models import UsageCounter

IST = timezone(timedelta(hours=5, minutes=30))


def _window(now: datetime | None = None) -> tuple[str, datetime]:
    local = (now or clock.now()).astimezone(IST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d"), start + timedelta(days=1)


def used(s: Session, user_id: str, feature: str) -> int:
    day, _ = _window()
    row = s.get(UsageCounter, (user_id, feature, day))
    return row.count if row else 0


def consume(s: Session, user_id: str, feature: str, limit: int | None, amount: int = 1) -> int:
    """Count ``amount`` uses of ``feature`` today; raise QuotaExceeded (429) past ``limit``. None = unlimited."""
    day, resets_at = _window()
    row = s.get(UsageCounter, (user_id, feature, day))
    current = row.count if row else 0
    if limit is not None and current + amount > limit:
        raise QuotaExceeded(
            f"Daily {feature} limit reached", feature=feature, limit=limit, resets_at=clock.iso(resets_at)
        )
    if row is None:
        row = UsageCounter(user_id=user_id, feature=feature, window_start=day, count=0)
        s.add(row)
    row.count = current + amount
    return row.count


def snapshot(s: Session, user_id: str, limits: dict[str, int | None]) -> dict[str, dict]:
    day, resets_at = _window()
    rows = {
        r.feature: r.count
        for r in s.scalars(select(UsageCounter).where(UsageCounter.user_id == user_id, UsageCounter.window_start == day))
    }
    return {
        feature: {"limit": limit, "used": rows.get(feature, 0), "resets_at": clock.iso(resets_at)}
        for feature, limit in limits.items()
    }
