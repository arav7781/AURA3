"""Evidence checks shared by evaluation, dashboard responses and PDF exports.

Search excerpts establish traceability, not independent verification. Never fill missing years, infer market
shares or turn a publisher's forecast into an actual.

Evidence v2 (deck provenance): a company figure must be quoted from a chunk of the startup's own documents
and carries that chunk's citation (page and box), so the UI can show the exact spot on the slide. Market
sizes the deck claims are kept separately as *claims*; only figures found in retrieved research are treated
as source-backed, and a claim is cross-checked against the sourced figure for the same period when there is
one. Provenance follows where a quote is actually found, not the label the model gave it: a publisher's
figure quoted from the deck is the startup's claim. Figures from low-confidence OCR are flagged and kept out
of charts.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

EVIDENCE_VERSION = 2
SUPPORTED_EVIDENCE_VERSIONS = {1, 2}
MARKET_KEYS = ("tam_usd_b", "sam_usd_b", "som_usd_b", "cagr_pct")
KINDS = ("reported", "source_forecast", "company_reported", "company_estimate", "company_forecast")
KIND_LABELS = {
    "reported": "Source-reported",
    "source_forecast": "Source forecast",
    "company_reported": "Company-reported (unverified)",
    "company_estimate": "Company estimate (unverified)",
    "company_forecast": "Company forecast (unverified)",
}
# Unit conversions only; currency exchange is never assumed.
UNITS = {
    "USD": ("USD", 1), "USD million": ("USD", 1e6), "USD billion": ("USD", 1e9),
    "INR": ("INR", 1), "INR lakh": ("INR", 1e5), "INR crore": ("INR", 1e7),
    "INR million": ("INR", 1e6), "INR billion": ("INR", 1e9),
    "EUR": ("EUR", 1), "EUR million": ("EUR", 1e6), "EUR billion": ("EUR", 1e9),
    "GBP": ("GBP", 1), "GBP million": ("GBP", 1e6), "GBP billion": ("GBP", 1e9),
    "%": ("%", 1),
}
LOW_CONFIDENCE = 0.9


@dataclass
class CompanyEvidence:
    """The startup's own material: profile text and document chunks (with provenance)."""

    profile_text: str = ""
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def locate(self, quote: str) -> dict[str, Any] | None:
        needle = _text(quote)
        for chunk in self.chunks:
            if needle and needle in _text(chunk.get("text", "")):
                return chunk
        return None

    @property
    def all_text(self) -> str:
        return self.profile_text + "\n" + "\n".join(c.get("text", "") for c in self.chunks)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _has_year(quote: str, year: int) -> bool:
    """A year in the quote, including fiscal forms: 2025, FY2025, FY 2025, FY25, FY'25, 2024-25."""
    yy = f"{year % 100:02d}"
    patterns = [
        rf"(?<![\d.]){year}(?!\d)",
        rf"\bFY\s?'?{yy}\b",
        rf"(?<!\d){year - 1}\s?[-–/]\s?{yy}(?!\d)",
    ]
    return any(re.search(p, quote, flags=re.IGNORECASE) for p in patterns)


def _has_quantity(quote: str, value: float, unit: str) -> bool:
    """Check the quoted amount and its adjoining currency/scale, not just a number."""
    number = r"(?<![\d.,])(?P<amount>-?\d[\d,]*(?:\.\d+)?)(?![\d,]|\.\d)"
    if unit == "%":
        patterns = [rf"{number}\s*(?:%|percent\b|per cent\b)"]
    else:
        currency, _, scale = unit.partition(" ")
        currency_pattern = {
            "USD": r"(?:US\$|USD\b|\$|U\.S\. dollars?)",
            "INR": r"(?:INR\b|Rs\.?|₹|rupees?\b)",
            "EUR": r"(?:EUR\b|€|euros?\b)",
            "GBP": r"(?:GBP\b|£|pounds?\b)",
        }[currency]
        scales = {
            "million": r"(?:millions?|mn|m)", "billion": r"(?:billions?|bn|b)",
            "lakh": r"(?:lakhs?|lacs?)", "crore": r"(?:crores?|cr)",
        }
        suffix = rf"\s*{scales[scale]}\b" if scale else r"(?!\s*(?:billion|million|lakh|lac|crore|bn|mn|cr|[mb])\b)"
        patterns = [rf"{currency_pattern}\s*{number}{suffix}", rf"{number}{suffix}\s*{currency_pattern}"]
    return any(
        math.isclose(float(match.group("amount").replace(",", "")), value, rel_tol=1e-10, abs_tol=1e-10)
        for pattern in patterns for match in re.finditer(pattern, quote, flags=re.IGNORECASE)
    )


def source_catalog(sources: list[dict]) -> list[dict]:
    catalog: dict[str, dict] = {}
    for source in sources:
        url = str(source.get("url") or "").strip()
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                continue
        except ValueError:
            continue
        if url not in catalog:
            catalog[url] = {key: str(source.get(key) or "") for key in
                            ("title", "url", "snippet", "retrieved_at", "query")}
        elif source.get("snippet") and source["snippet"] not in catalog[url]["snippet"]:
            catalog[url]["snippet"] += "\n" + source["snippet"]
    return list(catalog.values())


def _metric(raw: Any, sources: dict[str, dict], company: CompanyEvidence, *, company_allowed: bool = False) -> dict | None:
    if not isinstance(raw, dict):
        return None
    value = finite_number(raw.get("value"))
    unit, kind = raw.get("unit"), raw.get("kind")
    if value is None or unit not in UNITS or kind not in KINDS or (unit != "%" and value < 0):
        return None
    if unit == "%" and value <= -100:
        return None
    quote = str(raw.get("quote") or "").strip()
    if not quote or not _has_quantity(quote, value, unit):
        return None
    # Even a past forecast must never be relabeled as an observed result.
    if re.search(r"\b(?:forecast\w*|projected|expected|will reach|anticipated)\b", quote, re.IGNORECASE):
        kind = {"reported": "source_forecast", "company_reported": "company_forecast"}.get(kind, kind)
    url = str(raw.get("source_url") or "")
    source = sources.get(url)
    if not kind.startswith("company_") and not (source and _text(quote) in _text(source["snippet"])):
        if not company_allowed:
            return None
        # Not in any retrieved excerpt: if the startup's own material has it, it is the startup's claim.
        kind = {"reported": "company_reported", "source_forecast": "company_forecast"}[kind]
    citation = None
    low_confidence = False
    if kind.startswith("company_"):
        if not company_allowed:
            return None
        chunk = company.locate(quote)
        if chunk is not None:
            citation = {k: chunk.get(k) for k in ("cid", "chunk_id", "document_id", "page_no", "bbox")}
            title = f"{chunk.get('doc_name') or 'Pitch deck'}, p.{chunk.get('page_no')}"
            low_confidence = bool(chunk.get("review")) or float(chunk.get("conf_min", 1.0)) < LOW_CONFIDENCE
        elif _text(quote) in _text(company.profile_text):
            title = "Startup profile"
        else:
            return None
        retrieved_at = None
        url = ""
    else:
        title, retrieved_at = source["title"], source["retrieved_at"]
    # Require a period present in the evidence, rather than assigning today's year.
    year = finite_number(raw.get("year"))
    period = str(raw.get("period") or "").strip()
    if unit == "%":
        years = re.findall(r"\b(?:19|20|21)\d{2}\b", period)
        if len(years) < 2 or not all(y in quote for y in years):
            return None
        year = None
    elif year is None or not year.is_integer() or not 1900 <= year <= 2199 or not _has_year(quote, int(year)):
        return None
    elif kind in ("reported", "company_reported") and year > datetime.now(UTC).year:
        return None
    return {
        "value": value, "unit": unit, "kind": kind, "year": int(year) if year else None,
        "period": period, "quote": quote, "source_url": url or None,
        "source_title": title, "retrieved_at": retrieved_at,
        "market": str(raw.get("market") or "").strip(),
        "geography": str(raw.get("geography") or "").strip(),
        "citation": citation, "low_confidence": low_confidence,
    }


def _label(key: str) -> str:
    return key.replace("_usd_b", "").replace("_pct", "").upper()


def _usable(metric: dict | None, currency: str, *, company_figure: bool) -> bool:
    return bool(metric and UNITS[metric["unit"]][0] == currency and metric["market"] and metric["geography"]
                and metric["kind"].startswith("company_") == company_figure)


def _period_years(metric: dict) -> set[str]:
    return set(re.findall(r"\b(?:19|20|21)\d{2}\b", metric["period"]))


def _cross_check(claim: dict, sourced: dict | None, source_value: float | None) -> dict:
    """Compare a deck claim with the sourced figure for the same market metric."""
    if sourced is None or source_value is None:
        return {"status": "unverified"}
    same_period = (_period_years(claim) == _period_years(sourced) if claim["unit"] == "%"
                   else claim["year"] == sourced["year"])
    if not same_period:
        return {"status": "different_period", "source_value": source_value}
    if math.isclose(claim["normalised"], source_value, rel_tol=0.05):
        return {"status": "consistent", "source_value": source_value}
    return {"status": "differs", "source_value": source_value,
            "ratio": round(claim["normalised"] / source_value, 2) if source_value else None}


def normalise_financials(raw: dict, sources: list[dict], company: CompanyEvidence | str = "") -> dict:
    if isinstance(company, str):
        company = CompanyEvidence(profile_text=company)
    source_map = {s["url"]: s for s in source_catalog(sources)}
    market_raw = raw.get("market_sizing")
    market_raw = market_raw if isinstance(market_raw, dict) else {}
    claims_raw = raw.get("deck_market_claims")
    claims_raw = claims_raw if isinstance(claims_raw, dict) else {}
    market: dict = {key: None for key in MARKET_KEYS}
    market.update({"evidence": {}, "claims": {}, "trend": [],
                   "basis": "Only figures traceable to retrieved search excerpts are plotted as market data."})
    gaps = []
    for key in MARKET_KEYS:
        currency = "%" if key == "cagr_pct" else "USD"
        divisor = 1 if key == "cagr_pct" else 1e9
        metric = _metric(market_raw.get(key), source_map, company, company_allowed=True)
        claim = _metric(claims_raw.get(key), source_map, company, company_allowed=True)
        if _usable(metric, currency, company_figure=False):
            market[key] = metric["value"] * UNITS[metric["unit"]][1] / divisor
            market["evidence"][key] = metric
        elif _usable(metric, currency, company_figure=True) and not _usable(claim, currency, company_figure=True):
            claim = metric  # the deck's own figure, filed under market data
        if _usable(claim, currency, company_figure=True):
            # The deck's own figure: an unverified claim with its slide citation, never plotted as market data.
            market["claims"][key] = {**claim, "normalised": claim["value"] * UNITS[claim["unit"]][1] / divisor}
        elif market[key] is None:
            gaps.append(f"{_label(key)}: no usable source excerpt with value, unit and period.")

    # Reject inconsistent sizes; never silently clamp one number to another.
    for larger, smaller in (("tam_usd_b", "sam_usd_b"), ("sam_usd_b", "som_usd_b"), ("tam_usd_b", "som_usd_b")):
        if market[larger] is not None and market[smaller] is not None and market[smaller] > market[larger]:
            market[smaller] = None
            market["evidence"].pop(smaller, None)
            gaps.append(f"{smaller[:3].upper()} omitted: exceeds the reported {larger[:3].upper()}.")

    for key, claim in market["claims"].items():
        claim["check"] = _cross_check(claim, market["evidence"].get(key), market[key])
        page = (claim.get("citation") or {}).get("page_no")
        claimed = f"the deck claims {claim['value']:g} {claim['unit']}" + (f" (p.{page})" if page else "")
        sourced = market["evidence"].get(key)
        status = claim["check"]["status"]
        if status == "unverified":
            gaps.append(f"{_label(key)}: no independent source found; {claimed}.")
        elif status == "differs":
            gaps.append(f"{_label(key)}: {claimed}, but the retrieved source reports {sourced['value']:g} "
                        f"{sourced['unit']} for the same period.")
        elif status == "different_period":
            gaps.append(f"{_label(key)}: {claimed}; the retrieved source covers a different period, so the two "
                        "were not compared.")

    scope = None
    seen_years = set()
    for row in market_raw.get("trend") or []:
        metric = _metric(row, source_map, company)
        if not metric or not metric["unit"].startswith("USD") or not metric["market"] or not metric["geography"]:
            continue
        row_scope = (_text(metric["market"]), _text(metric["geography"]))
        if scope is not None and row_scope != scope:
            gaps.append("Market trend: incompatible market scopes were omitted.")
            continue
        scope = row_scope
        if metric["year"] in seen_years:
            continue
        seen_years.add(metric["year"])
        market["trend"].append({**metric, "size_usd_b": metric["value"] * UNITS[metric["unit"]][1] / 1e9})
    market["trend"].sort(key=lambda p: p["year"])
    if not market["trend"]:
        gaps.append("Market trend unavailable: no sourced annual observations or publisher forecasts. No years were interpolated.")

    revenue, currency, revenue_metric = [], None, None
    seen_years = set()
    for row in raw.get("projected_revenue") or []:
        metric = _metric(row, source_map, company, company_allowed=True)
        if not metric or metric["unit"] == "%" or row.get("metric") not in ("Revenue", "ARR"):
            continue
        if metric["low_confidence"]:
            gaps.append(f"Revenue {metric['year']}: read from a low-confidence OCR region, so it is not charted.")
            continue
        row_currency, multiplier = UNITS[metric["unit"]]
        if (currency and currency != row_currency) or (revenue_metric and revenue_metric != row["metric"]):
            gaps.append("Revenue chart: incompatible currencies or revenue/ARR measures were omitted.")
            continue
        if metric["year"] in seen_years:
            continue
        seen_years.add(metric["year"])
        currency, revenue_metric = row_currency, row["metric"]
        revenue.append({**metric, "revenue": metric["value"] * multiplier / 1e6, "metric": revenue_metric})
    revenue.sort(key=lambda p: p["year"])
    if not revenue:
        gaps.append("Revenue chart unavailable: no dated revenue or ARR figures with supporting evidence. No growth assumptions were applied.")
    return {
        "evidence_version": EVIDENCE_VERSION, "market_sizing": market,
        "projected_revenue": revenue, "revenue_currency": currency, "revenue_metric": revenue_metric,
        "data_gaps": list(dict.fromkeys(gaps)),
    }


def report_snapshot(analysis: dict) -> dict:
    """Hide unsupported financials in reports created before evidence was stored."""
    if analysis.get("evidence_version") in SUPPORTED_EVIDENCE_VERSIONS:
        market = analysis.get("market_sizing") or {}
        return analysis if "claims" in market else {**analysis, "market_sizing": {**market, "claims": {}}}
    return {
        **analysis, **normalise_financials({}, []), "evidence_version": 0,
        "data_gaps": ["This saved report predates source-linked charts. Refresh research to replace its earlier estimates."],
    }
