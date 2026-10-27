"""Spec → slide content. Both renderers draw exactly these slides, and every slide records which spec
facts it states (``facts``), so evals know the gold page for each number.

Numbers are written the way founders write them ("USD 82.3M in 2025", "ARR: Rs 3.1 crore in FY2025"),
which is also what the evaluation's quote checks expect: an amount with its currency, scale and year.
"""

from dataclasses import dataclass, field

from aura.decks.spec import Metric, StartupSpec

STAGE_LABELS = {"pre_seed": "Pre-seed", "seed": "Seed", "series_a": "Series A", "series_b": "Series B"}
PER = {"one-time": "one-time", "month": "per month", "year": "per year"}


@dataclass
class Slide:
    key: str
    title: str
    subtitle: str | None = None
    bullets: list[str] = field(default_factory=list)
    table: list[list[str]] | None = None  # first row is the header
    chart: dict | None = None  # {"title", "labels", "values", "unit"}
    notes: str | None = None  # PPTX speaker notes
    hidden: str | None = None  # white text a reader cannot see (adversarial decks only)
    facts: dict[str, str] = field(default_factory=dict)  # spec field → the text that states it
    stats: list[tuple[str, str]] = field(default_factory=list)  # (figure, label) tiles, e.g. ("4.0x", "LTV / CAC")


def number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def money(metric: Metric) -> str:
    v = metric.value
    return {
        "USD million": f"USD {number(v)}M",
        "USD billion": f"USD {number(v)}B",
        "USD": f"USD {number(v)}",
        "INR crore": f"Rs {number(v)} crore",
        "INR lakh": f"Rs {number(v)} lakh",
        "INR": f"Rs {number(v)}",
        "%": f"{number(v)}%",
    }.get(metric.unit, f"{number(v)} {metric.unit}")


def rupees(value: float) -> str:
    return f"Rs {number(value)}"


def crore(rupee_amount: int) -> str:
    return number(rupee_amount / 1e7)


def year_label(year: int | None, as_of: str) -> str:
    return f"FY{year}" if year and as_of.upper().startswith("FY") else str(year or "")


def provenance(metric: Metric | None = None, *, source: str | None = None, kind: str | None = None) -> str:
    source = metric.source if metric else source
    kind = metric.kind if metric else kind
    if kind in ("reported", "source_forecast") and source:
        return f" (Source: {source})"
    return {"company_estimate": " (company estimate)", "company_forecast": " (company projection)",
            "company_reported": " (company data)"}.get(kind or "", "")


def build_slides(spec: StartupSpec) -> list[Slide]:
    stage = STAGE_LABELS[spec.stage]
    ask, pre = crore(spec.round.ask_inr), crore(spec.round.pre_money_inr)
    post = crore(spec.round.ask_inr + spec.round.pre_money_inr)
    team_names = " · ".join(member.name for member in spec.team)

    title = Slide("title", spec.name, subtitle=spec.one_liner, bullets=[
        spec.legal_name,
        f"CIN {spec.mca.cin} · {spec.hq.city}, {spec.hq.state} · Founded {spec.founded_year}",
        f"{stage} round: raising Rs {ask} crore at Rs {pre} crore pre-money",
        f"Team: {team_names}",
    ], facts={"mca.cin": spec.mca.cin, "round.ask_inr": f"Rs {ask} crore", "round.pre_money_inr": f"Rs {pre} crore"})

    problem = Slide("problem", "Problem", subtitle=spec.problem.statement, bullets=[
        stat.claim + provenance(source=stat.source, kind=stat.kind) for stat in spec.problem.stats
    ])

    solution = Slide("solution", "Solution", subtitle=spec.solution.summary, bullets=list(spec.solution.bullets))

    m = spec.market
    tam = f"TAM — {m.tam.scope or 'Total market'}: {money(m.tam)} in {m.tam.year}"
    if m.tam_forecast:
        tam += f", projected {money(m.tam_forecast)} by {m.tam_forecast.year}"
    if m.cagr:
        tam += f" at {money(m.cagr)} CAGR"
    market = Slide("market", "Market Opportunity (TAM / SAM / SOM)", bullets=[tam + provenance(m.tam)],
                   facts={"market.tam": f"{money(m.tam)} in {m.tam.year}"})
    for key, metric in (("sam", m.sam), ("som", m.som)):
        if metric:
            market.bullets.append(f"{key.upper()} — {metric.scope or 'Segment'}: {money(metric)} in {metric.year}"
                                  + provenance(metric))
            market.facts[f"market.{key}"] = f"{money(metric)} in {metric.year}"
    if m.cagr:
        market.bullets.append(f"{m.cagr.scope or 'Market'} CAGR: {money(m.cagr)} ({m.cagr.period})" + provenance(m.cagr))
        market.facts["market.cagr"] = f"{money(m.cagr)} ({m.cagr.period})"
    if m.tam_forecast:
        market.facts["market.tam_forecast"] = f"{money(m.tam_forecast)} by {m.tam_forecast.year}"

    business = Slide("business_model", "Business Model")
    for stream in spec.business_model.streams:
        line = stream.name
        if stream.price_inr is not None:
            line += f": {rupees(stream.price_inr)} {PER.get(stream.per or '', f'per {stream.per}' if stream.per else '')}".rstrip()
        if stream.share_pct is not None:
            line += f" ({number(stream.share_pct)}% of revenue)"
        if stream.description:
            line += f". {stream.description}"
        business.bullets.append(line)
    business.bullets += spec.business_model.notes

    t = spec.traction
    traction = Slide("traction", f"Traction (as of {t.as_of})")
    if t.arr:
        label = "ARR" if t.series is None else t.series.metric
        arr_line = f"{label}: {money(t.arr)} in {year_label(t.arr.year, t.as_of)}"
        traction.bullets.append(arr_line)
        traction.facts["traction.arr"] = arr_line
    if t.customers is not None and not any(number(t.customers) in h for h in t.highlights):
        traction.bullets.append(f"{number(t.customers)} {t.customer_label}")
    if t.customers is not None:
        traction.facts["traction.customers"] = number(t.customers)
    traction.bullets += t.highlights
    if t.series:
        unit_label = t.series.unit.replace("INR ", "Rs ")
        traction.table = [["Year", f"{t.series.metric} ({unit_label})"]] + [
            [year_label(p.year, t.as_of), number(p.value)] for p in t.series.points
        ]
        traction.chart = {"title": f"{t.series.metric} ({unit_label})",
                          "labels": [year_label(p.year, t.as_of) for p in t.series.points],
                          "values": [p.value for p in t.series.points]}

    u = spec.unit_economics
    economics = Slide("unit_economics", "Unit Economics")
    rows = [
        ("cac_inr", u.cac_inr, lambda v: f"Customer acquisition cost (CAC): {rupees(v)}"),
        ("payback_months", u.payback_months, lambda v: f"CAC payback: {number(v)} months"),
        ("gross_margin_pct", u.gross_margin_pct, lambda v: f"Gross margin: {number(v)}%"),
        ("ltv_inr", u.ltv_inr, lambda v: f"Customer lifetime value (LTV): {rupees(v)}"),
        ("nrr_pct", u.nrr_pct, lambda v: f"Net revenue retention (NRR): {number(v)}%"),
        ("monthly_churn_pct", u.monthly_churn_pct, lambda v: f"Monthly churn: {number(v)}%"),
    ]
    for key, value, text in rows:
        if value is not None:
            economics.bullets.append(text(value))
            economics.facts[f"unit_economics.{key}"] = text(value)
    economics.bullets += u.other
    if u.ltv_inr and u.cac_inr:
        economics.bullets.append(f"LTV / CAC: {u.ltv_inr / u.cac_inr:.1f}x")

    competition = Slide("competition", "Competitive Landscape",
                        table=[["Company", "Positioning"]] + [[c.name, c.positioning] for c in spec.competitors],
                        bullets=[f"Our edge: {item}" for item in spec.moat])

    gtm = Slide("gtm", "Go-to-Market & Key Risks", bullets=[
        *(f"Channel: {channel}" for channel in spec.gtm.channels),
        f"Target: {spec.gtm.target}",
        *(f"Risk: {risk}" for risk in spec.risks),
    ])

    team = Slide("team", "Team", bullets=[f"{f.name} — {f.role}. {f.background}" for f in spec.team])

    r = spec.round
    ask_slide = Slide("ask", "The Ask", bullets=[
        f"Raising Rs {ask} crore {stage} at Rs {pre} crore pre-money (Rs {post} crore post-money).",
        f"Minimum raise: {r.min_raise_pct}% of the target.",
        "Use of funds: " + ", ".join(f"{u.pct}% {u.category}" for u in r.use_of_funds) + ".",
        *(f"Tranche {i}: {t.pct}% at {t.title}" + (f" ({t.criteria})" if t.criteria else "")
          + (f", within {t.due_days} days" if t.due_days else "")
          for i, t in enumerate(r.tranches, start=1)),
    ], facts={"round.ask_inr": f"Rs {ask} crore", "round.pre_money_inr": f"Rs {pre} crore"})

    slides = [title, problem, solution, market, business, traction, economics, competition, gtm, team, ask_slide]

    adversarial = spec.deck.adversarial
    for key, text in adversarial.inconsistent.items():
        target = next((s for s in slides if s.key == key), None)
        if target is None:
            raise ValueError(f"{spec.slug}: no slide {key!r} for the inconsistent override")
        target.subtitle = text
    if adversarial.injection:
        if not 1 <= adversarial.injection_slide <= len(slides):
            raise ValueError(f"{spec.slug}: injection_slide must be 1..{len(slides)}")
        slides[adversarial.injection_slide - 1].hidden = adversarial.injection
        slides[adversarial.injection_slide - 1].notes = adversarial.injection
    return slides


def slide_map(spec: StartupSpec, slides: list[Slide]) -> dict:
    """Gold pages for evals: which slide states each spec fact."""
    pages: dict[str, int] = {}
    for page, slide in enumerate(slides, start=1):
        for fact in slide.facts:
            pages.setdefault(fact, page)
    return {
        "slug": spec.slug,
        "slides": [{"page": i, "key": s.key, "title": s.title} for i, s in enumerate(slides, start=1)],
        "facts": {fact: {"page": page, "text": slides[page - 1].facts[fact]} for fact, page in pages.items()},
        "injection_page": next((i for i, s in enumerate(slides, start=1) if s.hidden), None),
    }
