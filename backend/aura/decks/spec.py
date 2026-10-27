"""The startup spec: one YAML file per seeded startup (``backend/seed/specs/NN-slug.yaml``).

The same model drives the deck renderer (11 slides generated from the fields), the seeder (accounts,
profile, MCA registry fixture, funding round) and the evals (every number here is ground truth, and the
renderer records which slide it lands on).

Validate with: ``uv run python -m aura.decks.spec seed/specs``
"""

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal["reported", "source_forecast", "company_reported", "company_estimate", "company_forecast"]
Stage = Literal["pre_seed", "seed", "series_a", "series_b"]
DOMAINS = (
    "Agritech", "Fintech", "Healthtech", "Edtech", "Climate & Energy", "B2B SaaS", "Logistics & Mobility",
    "Cybersecurity", "Consumer & D2C", "Deeptech & AI", "Proptech", "Insurtech",
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metric(Strict):
    value: float
    unit: str = Field(description="e.g. 'USD million', 'USD billion', 'INR crore', '%'")
    year: int | None = None
    period: str | None = Field(default=None, description="for CAGR: '2025-2030'")
    scope: str | None = Field(default=None, description="market definition, e.g. 'India agriculture IoT'")
    source: str | None = Field(default=None, description="publisher for reported figures; omit for company figures")
    kind: Kind = "reported"


class Stat(Strict):
    claim: str
    source: str | None = None
    kind: Kind = "reported"


class Problem(Strict):
    statement: str
    stats: list[Stat] = Field(min_length=1, max_length=4)


class Solution(Strict):
    summary: str
    bullets: list[str] = Field(min_length=2, max_length=5)


class Market(Strict):
    tam: Metric
    tam_forecast: Metric | None = None
    cagr: Metric | None = None
    sam: Metric | None = None
    som: Metric | None = None


class Stream(Strict):
    name: str
    price_inr: float | None = None
    per: str | None = Field(default=None, description="'one-time', 'month', 'year', 'transaction', ...")
    share_pct: float | None = None
    description: str | None = None


class BusinessModel(Strict):
    streams: list[Stream] = Field(min_length=1, max_length=4)
    notes: list[str] = Field(default_factory=list, max_length=3)


class UnitEconomics(Strict):
    cac_inr: float | None = None
    payback_months: float | None = None
    gross_margin_pct: float | None = None
    nrr_pct: float | None = None
    monthly_churn_pct: float | None = None
    ltv_inr: float | None = None
    other: list[str] = Field(default_factory=list, max_length=3)


class SeriesPoint(Strict):
    year: int
    value: float


class Series(Strict):
    metric: str = Field(description="e.g. 'ARR', 'Revenue', 'GMV'")
    unit: str = Field(description="e.g. 'INR crore'")
    points: list[SeriesPoint] = Field(min_length=2, max_length=6)


class Traction(Strict):
    as_of: str = Field(description="e.g. 'FY2025' or 'Sep 2026'")
    customers: int | None = None
    customer_label: str = "customers"
    arr: Metric | None = None
    series: Series | None = None
    highlights: list[str] = Field(min_length=1, max_length=5)


class Competitor(Strict):
    name: str
    positioning: str


class GoToMarket(Strict):
    channels: list[str] = Field(min_length=1, max_length=5)
    target: str


class Founder(Strict):
    name: str
    role: str
    background: str


class UseOfFunds(Strict):
    category: str
    pct: int = Field(ge=1, le=100)


class Tranche(Strict):
    pct: int = Field(ge=10, le=100)
    title: str
    criteria: str | None = None
    due_days: int | None = None


class Round(Strict):
    ask_inr: int = Field(gt=0, description="rupees, e.g. 120000000 for Rs 12 crore")
    pre_money_inr: int = Field(gt=0)
    min_raise_pct: int = Field(default=60, ge=50, le=100)
    use_of_funds: list[UseOfFunds] = Field(min_length=2, max_length=6)
    tranches: list[Tranche] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _sums(self) -> "Round":
        if sum(u.pct for u in self.use_of_funds) != 100:
            raise ValueError("use_of_funds percentages must sum to 100")
        if sum(t.pct for t in self.tranches) != 100:
            raise ValueError("tranche percentages must sum to 100")
        return self


class Registry(Strict):
    status: Literal["ACTIVE", "STRUCK_OFF", "UNDER_LIQUIDATION", "DORMANT"] = "ACTIVE"
    registered_name: str
    directors: list[str] = Field(min_length=1)
    incorporation_year: int
    state: str


class MCA(Strict):
    cin: str = Field(description="21-char CIN, e.g. U62099MH2024PTC410567 (malformed only if the twist says so)")
    registry: Registry | None = Field(default=None, description="omit to simulate 'not found in registry'")


class Scan(Strict):
    dpi: int = 110
    skew_deg: float = 0.0
    noise: float = Field(default=0.0, ge=0, le=0.2)
    jpeg_quality: int = Field(default=70, ge=20, le=95)
    seed: int = 7


class Adversarial(Strict):
    injection: str | None = Field(default=None, description="hidden white text added to a slide (and PPTX notes)")
    injection_slide: int = 11
    inconsistent: dict[str, str] = Field(
        default_factory=dict, description="slide-level overrides that contradict the spec, e.g. {'traction': '...'}"
    )


class DeckRender(Strict):
    render: Literal["text", "scanned"] = "text"
    scan: Scan | None = None
    adversarial: Adversarial = Field(default_factory=Adversarial)


class EvalExpectations(Strict):
    score_band: tuple[float, float]
    recommendation_in: list[Literal["Strong Buy", "Buy", "Hold", "Pass"]]
    must_flag: list[str] = Field(default_factory=list, description="compliance flags the evaluation must raise")

    @field_validator("score_band")
    @classmethod
    def _band(cls, band: tuple[float, float]) -> tuple[float, float]:
        if not 0 <= band[0] < band[1] <= 10:
            raise ValueError("score_band must be an increasing pair within 0..10")
        return band


class Location(Strict):
    city: str
    state: str


class FounderAccount(Strict):
    email: str
    name: str


class StartupSpec(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["aura.seed.startup/v1"] = Field(alias="schema")
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    legal_name: str
    domain: Literal[DOMAINS]  # type: ignore[valid-type]
    sub_domain: str | None = None
    stage: Stage
    hq: Location
    founded_year: int = Field(ge=2015, le=2026)
    one_liner: str = Field(max_length=120)
    description: str = Field(max_length=600)
    founder_account: FounderAccount
    mca: MCA
    team: list[Founder] = Field(min_length=1, max_length=5)
    problem: Problem
    solution: Solution
    market: Market
    business_model: BusinessModel
    unit_economics: UnitEconomics
    traction: Traction
    competitors: list[Competitor] = Field(min_length=2, max_length=5)
    moat: list[str] = Field(min_length=1, max_length=4)
    gtm: GoToMarket
    round: Round
    risks: list[str] = Field(min_length=2, max_length=5)
    deck: DeckRender = Field(default_factory=DeckRender)
    evaluation_expectations: EvalExpectations

    @property
    def ask_crore(self) -> float:
        return self.round.ask_inr / 1e7

    @property
    def pre_money_crore(self) -> float:
        return self.round.pre_money_inr / 1e7


def load_spec(path: Path) -> StartupSpec:
    return StartupSpec.model_validate(yaml.safe_load(path.read_text()))


def load_specs(folder: Path) -> list[StartupSpec]:
    return [load_spec(p) for p in sorted(folder.glob("*.yaml"))]


def main(folder: str) -> int:
    paths = sorted(Path(folder).glob("*.yaml"))
    failures = 0
    slugs: set[str] = set()
    for path in paths:
        try:
            spec = load_spec(path)
            if spec.slug in slugs:
                raise ValueError(f"duplicate slug {spec.slug}")
            slugs.add(spec.slug)
            print(f"ok    {path.name}  ({spec.name}, {spec.domain}, {spec.stage}, ask Rs {spec.ask_crore:g} Cr)")
        except Exception as exc:  # report every file, then fail
            failures += 1
            print(f"FAIL  {path.name}: {exc}")
    print(f"{len(paths) - failures}/{len(paths)} valid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "seed/specs"))
