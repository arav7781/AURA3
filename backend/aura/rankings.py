"""Community ranking: a weighted, truncated Borda count over every investor's top-10 list.

Position p (1..10) earns 11 - p points. Each investor's points are weighted by plan (Scout 0.5, Angel and
Syndicate 1.0) times reputation (0.5–2.0), so a burst of free accounts cannot outvote paying investors.
The community score is the weighted points as a share of the maximum (every weighted investor ranking the
startup first), scaled to 0–10 so it sits beside the AI score.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from aura.models import InvestorProfile, Ranking

PLAN_WEIGHT = {"scout": 0.5, "angel": 1.0, "syndicate": 1.0}
MAX_POSITION = 10


@dataclass(frozen=True)
class Ballot:
    investor_id: str
    plan: str
    reputation: float  # 0.5–2.0
    startup_ids: list[str]  # best first, at most 10

    @property
    def weight(self) -> float:
        return PLAN_WEIGHT.get(self.plan, 0.5) * min(2.0, max(0.5, self.reputation))


def community_scores(ballots: list[Ballot]) -> dict[str, dict]:
    """startup id → {score (0–10), points, rankers}."""
    total_weight = sum(b.weight for b in ballots if b.startup_ids)
    points: dict[str, float] = {}
    rankers: dict[str, int] = {}
    for ballot in ballots:
        for position, startup_id in enumerate(ballot.startup_ids[:MAX_POSITION], start=1):
            points[startup_id] = points.get(startup_id, 0.0) + ballot.weight * (MAX_POSITION + 1 - position)
            rankers[startup_id] = rankers.get(startup_id, 0) + 1
    maximum = total_weight * MAX_POSITION
    return {
        startup_id: {"score": round(10 * value / maximum, 2) if maximum else 0.0, "points": round(value, 3),
                     "rankers": rankers[startup_id]}
        for startup_id, value in points.items()
    }


def ranks(values: dict[str, float]) -> dict[str, int]:
    """Competition ranking (1, 2, 2, 4): ties share the better rank."""
    ordered = sorted(values.values(), reverse=True)
    return {key: ordered.index(value) + 1 for key, value in values.items()}


def load_ballots(s: Any) -> list[Ballot]:
    """Every investor's saved top-10 list, best first."""
    rows = s.execute(
        select(Ranking.investor_id, Ranking.startup_id, InvestorProfile.plan, InvestorProfile.reputation_milli)
        .join(InvestorProfile, InvestorProfile.user_id == Ranking.investor_id)
        .order_by(Ranking.investor_id, Ranking.position)
    ).all()
    lists: dict[str, tuple[str, float, list[str]]] = {}
    for investor_id, startup_id, plan, reputation in rows:
        lists.setdefault(investor_id, (plan, reputation / 1000, []))[2].append(startup_id)
    return [Ballot(i, plan, rep, ids) for i, (plan, rep, ids) in lists.items()]
