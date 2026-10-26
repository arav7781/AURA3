"""Evidence checks shared by evaluation, dashboard responses and PDF exports.

Search excerpts establish traceability, not independent verification. Never fill
missing years, infer market shares or turn a publisher's forecast into an actual.
"""

import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

EVIDENCE_VERSION = 1
MARKET_KEYS = ("tam_usd_b", "sam_usd_b", "som_usd_b", "cagr_pct")
KINDS = ("reported", "source_forecast", "company_reported", "company_forecast")
KIND_LABELS = {
    "reported": "Source-reported",
    "source_forecast": "Source forecast",
    "company_reported": "Company-reported (unverified)",
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


def _has_number(quote: str, value: float) -> bool:
    return any(
        math.isclose(float(token.replace(",", "")), value, rel_tol=1e-10, abs_tol=1e-10)
        for token in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?!\d|\.\d)", quote)
    )


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


def _metric(raw: Any, sources: dict[str, dict], company_text: str, *, company: bool = False) -> dict | None:
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
    if kind.startswith("company_"):
        if not company or _text(quote) not in _text(company_text):
            return None
        title, retrieved_at = "Startup profile / uploaded documents", None
        url = ""
    else:
        if not source or _text(quote) not in _text(source["snippet"]):
            return None
        title, retrieved_at = source["title"], source["retrieved_at"]
    # Require a period present in the evidence, rather than assigning today's year.
    year = finite_number(raw.get("year"))
    period = str(raw.get("period") or "").strip()
    if unit == "%":
        years = re.findall(r"\b(?:19|20|21)\d{2}\b", period)
        if len(years) < 2 or not all(y in quote for y in years):
            return None
        year = None
    elif year is None or not year.is_integer() or not 1900 <= year <= 2199 or not _has_number(quote, year):
        return None
    elif kind in ("reported", "company_reported") and year > datetime.now(timezone.utc).year:
        return None
    return {
        "value": value, "unit": unit, "kind": kind, "year": int(year) if year else None,
        "period": period, "quote": quote, "source_url": url or None,
        "source_title": title, "retrieved_at": retrieved_at,
        "market": str(raw.get("market") or "").strip(),
        "geography": str(raw.get("geography") or "").strip(),
    }


def normalise_financials(raw: dict, sources: list[dict], company_text: str = "") -> dict:
    source_map = {s["url"]: s for s in source_catalog(sources)}
    market_raw = raw.get("market_sizing")
    market_raw = market_raw if isinstance(market_raw, dict) else {}
    market: dict = {key: None for key in MARKET_KEYS}
    market.update({"evidence": {}, "trend": [], "basis": "Only figures traceable to retrieved search excerpts are plotted."})
    gaps = []
    for key in MARKET_KEYS:
        metric = _metric(market_raw.get(key), source_map, company_text)
        expected_currency = "%" if key == "cagr_pct" else "USD"
        if metric and UNITS[metric["unit"]][0] == expected_currency and metric["market"] and metric["geography"]:
            divisor = 1 if key == "cagr_pct" else 1e9
            market[key] = metric["value"] * UNITS[metric["unit"]][1] / divisor
            market["evidence"][key] = metric
        else:
            gaps.append(f"{key.replace('_usd_b', '').replace('_pct', '').upper()}: no usable source excerpt with value, unit and period.")

    # Reject inconsistent sizes; never silently clamp one number to another.
    for larger, smaller in (("tam_usd_b", "sam_usd_b"), ("sam_usd_b", "som_usd_b"), ("tam_usd_b", "som_usd_b")):
        if market[larger] is not None and market[smaller] is not None and market[smaller] > market[larger]:
            market[smaller] = None
            market["evidence"].pop(smaller, None)
            gaps.append(f"{smaller[:3].upper()} omitted: exceeds the reported {larger[:3].upper()}.")

    scope = None
    seen_years = set()
    for row in market_raw.get("trend") or []:
        metric = _metric(row, source_map, company_text)
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
        market["trend"].append({
            **metric, "size_usd_b": metric["value"] * UNITS[metric["unit"]][1] / 1e9,
        })
    market["trend"].sort(key=lambda p: p["year"])
    if not market["trend"]:
        gaps.append("Market trend unavailable: no sourced annual observations or publisher forecasts. No years were interpolated.")

    revenue, currency, revenue_metric = [], None, None
    seen_years = set()
    for row in raw.get("projected_revenue") or []:
        metric = _metric(row, source_map, company_text, company=True)
        if not metric or metric["unit"] == "%" or row.get("metric") not in ("Revenue", "ARR"):
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
    if analysis.get("evidence_version") == EVIDENCE_VERSION:
        return analysis
    return {
        **analysis, **normalise_financials({}, []), "evidence_version": 0,
        "data_gaps": ["This saved report predates source-linked charts. Refresh research to replace its earlier estimates."],
    }
