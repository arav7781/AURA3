"""Investor plans, features and the AuraCoin they grant.

AuraCoin (AC) is a closed-loop utility credit: granted with a plan, never sold, not transferable between
users and not redeemable. Prices are shown in INR; the demo takes no payment ("Activate" mints AC).
"""

from dataclasses import dataclass
from datetime import timedelta

MINOR_PER_AC = 100
PLAN_PERIOD = timedelta(days=30)
MAX_CATCH_UP_PERIODS = 12

FEATURES: dict[str, str] = {
    "catalogue": "Startup catalogue and search",
    "ai_summary": "AI score, label and executive summary",
    "full_report": "Full 11-section AI due-diligence report",
    "deck_access": "Pitch decks and the TitanOCR evidence viewer",
    "chunk_explorer": "Embedding explorer over deck chunks",
    "pdf_reports": "Investor PDF reports",
    "copilot": "Aura copilot (RAG, web search, code sandbox)",
    "vote": "Quadratic voting on DAO rounds",
    "pledge": "Pledging AuraCoin to funding rounds",
    "co_invest": "Lead co-investment rounds",
    "priority_deal_flow": "Priority access to new rounds",
    "api_access": "Read-only API key",
}


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    rank: int
    price_inr_month: int
    monthly_ac: int
    welcome_ac: int
    copilot_daily: int | None  # None = unlimited
    sandbox_daily: int
    features: frozenset[str]
    blurb: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "price_inr_month": self.price_inr_month,
            "monthly_ac": self.monthly_ac,
            "welcome_ac": self.welcome_ac,
            "copilot_daily": self.copilot_daily,
            "sandbox_daily": self.sandbox_daily,
            "features": sorted(self.features),
            "blurb": self.blurb,
        }


_SCOUT = frozenset({"catalogue", "ai_summary", "copilot"})
_ANGEL = _SCOUT | {"full_report", "deck_access", "chunk_explorer", "pdf_reports", "vote", "pledge"}
_SYNDICATE = _ANGEL | {"co_invest", "priority_deal_flow", "api_access"}

PLANS: dict[str, Plan] = {
    "scout": Plan("scout", "Scout", 0, 0, 0, 500, 30, 5, _SCOUT,
                  "Browse every startup with AI scores. Your 500 AC welcome credit unlocks when you upgrade."),
    "angel": Plan("angel", "Angel", 1, 4999, 5000, 500, None, 50, _ANGEL,
                  "Full decks, TitanOCR evidence, reports, and a vote in every round."),
    "syndicate": Plan("syndicate", "Syndicate", 2, 24999, 25000, 500, None, 200, _SYNDICATE,
                      "Lead co-investments, see new rounds first, and pull data through the API."),
}

# Startups list for free; the platform earns a success fee on each released tranche.
SUCCESS_FEE_BPS = 200
STARTUP_QUOTAS = {"copilot": 100, "sandbox": 20, "evaluation": 5, "deck_build": 10}
STARTUP_FEATURES = frozenset({"catalogue", "ai_summary", "copilot"})


def ac_to_minor(amount_ac: int | float) -> int:
    return int(round(amount_ac * MINOR_PER_AC))


def minor_to_ac(amount_minor: int) -> float:
    return amount_minor / MINOR_PER_AC
