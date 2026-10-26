"""Investor PDF report: ReportLab layout with Matplotlib charts built from the analysis."""

import io
import re
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

from aura.core import clock
from aura.evaluation.evidence import KIND_LABELS, report_snapshot
from aura.evaluation.graph import DECK_CITATION, SCORE_DIMENSIONS, SECTION_TITLES, WEB_CITATION

INK, ACCENT, MUTED, LINE = "#0f172a", "#0f6b5f", "#64748b", "#e2e8f0"
CHART_BG, BAR_COLORS = "#ffffff", ["#0f6b5f", "#2a9d8f", "#8ecae6"]
CLAIM_CHECKS = {
    "unverified": "not independently sourced",
    "consistent": "matches the retrieved source",
    "differs": "differs from the retrieved source",
    "different_period": "the retrieved source covers a different period",
}


def _unavailable_chart(title: str, message: str) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7, 2), facecolor=CHART_BG)
    ax.axis("off")
    ax.set_title(title, color=INK, fontsize=12, fontweight="bold", loc="left")
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=10, wrap=True)
    return _png(fig)


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=CHART_BG)
    plt.close(fig)
    buf.seek(0)
    return buf


def _style_axes(ax, title: str) -> None:
    ax.set_title(title, color=INK, fontsize=12, fontweight="bold", pad=10, loc="left")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(LINE)
    ax.set_facecolor(CHART_BG)


def market_opportunity_chart(analysis: dict[str, Any], domain: str) -> io.BytesIO:
    m = analysis["market_sizing"]
    rows = [(k[:3].upper(), m[k]) for k in ("tam_usd_b", "sam_usd_b", "som_usd_b") if m[k] is not None]
    if not rows:
        return _unavailable_chart("Market opportunity", "No source-supported market sizing available.")
    labels, values = zip(*rows, strict=True)
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=CHART_BG)
    bars = ax.bar(labels, values, color=BAR_COLORS[:len(rows)], width=0.55)
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"${value:,.4g}B",
                ha="center", va="bottom", color=INK, fontsize=10, fontweight="bold")
    ax.set_ylabel("USD billions", color=MUTED, fontsize=9)
    ax.set_ylim(0, max(values) * 1.2 or 1)
    _style_axes(ax, f"Market opportunity — {domain}")
    return _png(fig)


def scorecard_chart(analysis: dict[str, Any]) -> io.BytesIO:
    scores = analysis["category_scores"]
    labels = [SCORE_DIMENSIONS[k] for k in SCORE_DIMENSIONS if k in scores]
    values = [scores[k] for k in SCORE_DIMENSIONS if k in scores]
    if not values:
        return _unavailable_chart("AI evaluation scorecard", "No analytical scores available.")
    fig, ax = plt.subplots(figsize=(7, 3.8), facecolor=CHART_BG)
    bars = ax.barh(labels[::-1], values[::-1], color=ACCENT, height=0.55)
    for bar, value in zip(bars, values[::-1], strict=True):
        ax.text(value + 0.12, bar.get_y() + bar.get_height() / 2, f"{value:.1f}/10",
                va="center", color=INK, fontsize=9, fontweight="bold")
    ax.set_xlim(0, 10.8)
    _style_axes(ax, "AI evaluation scorecard (analytical judgment)")
    return _png(fig)


def market_trend_chart(analysis: dict[str, Any], domain: str) -> io.BytesIO:
    m = analysis["market_sizing"]
    if not m["trend"]:
        return _unavailable_chart("Published market data", "No dated market observations or publisher forecasts available.")
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=CHART_BG)
    for kind, color, marker in (("reported", ACCENT, "o"), ("source_forecast", "#d97706", "D")):
        points = [p for p in m["trend"] if p["kind"] == kind]
        if points:
            ax.scatter([p["year"] for p in points], [p["size_usd_b"] for p in points],
                       color=color, marker=marker, label=KIND_LABELS[kind], s=45)
    ax.set_xticks([p["year"] for p in m["trend"]])
    ax.set_ylabel("USD billions", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=MUTED)
    _style_axes(ax, f"Published market data — {domain}")
    return _png(fig)


def revenue_chart(analysis: dict[str, Any]) -> io.BytesIO:
    rows = analysis["projected_revenue"]
    if not rows:
        return _unavailable_chart("Revenue / ARR", "No dated company figures or explicit forecasts available.")
    fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=CHART_BG)
    ax.bar([f"{r['year']}\n{KIND_LABELS[r['kind']].replace(' (unverified)', '')}" for r in rows],
           [r["revenue"] for r in rows],
           color=["#d97706" if "forecast" in r["kind"] else ACCENT for r in rows], width=0.55)
    ax.set_ylabel(f"{analysis['revenue_currency']} millions", color=MUTED, fontsize=9)
    _style_axes(ax, f"{analysis['revenue_metric']} — reported figures and explicit forecasts")
    return _png(fig)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;")


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"<link href='\2' color='#0f6b5f'>\1</link>", text)


def _markdown_flowables(md: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append([Paragraph(_inline(c), styles["cell"]) for c in cells])
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [Paragraph("", styles["cell"])] * (width - len(r)) for r in rows]
                table = Table(rows, colWidths=[16.5 * cm / width] * width, repeatRows=1)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                flowables += [table, Spacer(1, 6)]
            continue
        heading = re.match(r"^#{1,6}\s+(.*)", stripped)
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)", stripped)
        if heading:
            flowables.append(Paragraph(_inline(heading.group(1)), styles["subheading"]))
        elif bullet:
            flowables.append(Paragraph(f"• {_inline(bullet.group(1))}", styles["bullet"]))
        else:
            flowables.append(Paragraph(_inline(stripped), styles["body"]))
        i += 1
    return flowables


def printable_citations(text: str, analysis: dict[str, Any]) -> str:
    """Turn [c:…] deck citations into "(deck p.N)" and [w:n] web citations into "[n]" for print."""
    citations = analysis.get("citations") or {}

    def deck(match: "re.Match[str]") -> str:
        page = (citations.get(match.group(1)) or {}).get("page_no")
        return f"(deck p.{page})" if page else ""

    return WEB_CITATION.sub(lambda m: f"[{m.group(1)}]", DECK_CITATION.sub(deck, text))


def build_pdf_report(startup: dict[str, Any], analysis: dict[str, Any]) -> bytes:
    analysis = report_snapshot(analysis)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"AURA-3 Evaluation — {startup.get('name', 'Startup')}", author="AURA-3",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=24, textColor=colors.HexColor(INK),
                                alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=10, textColor=colors.HexColor(MUTED),
                                   alignment=TA_CENTER, spaceAfter=10),
        "section": ParagraphStyle("s", parent=base["Heading2"], fontSize=14, textColor=colors.HexColor(ACCENT),
                                  spaceBefore=14, spaceAfter=6),
        "subheading": ParagraphStyle("sh", parent=base["Heading4"], fontSize=11, textColor=colors.HexColor(INK),
                                     spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=10, leading=15, alignment=TA_JUSTIFY,
                               textColor=colors.HexColor("#1e293b"), spaceAfter=5),
        "bullet": ParagraphStyle("bl", parent=base["Normal"], fontSize=10, leading=14, leftIndent=12,
                                 textColor=colors.HexColor("#1e293b"), spaceAfter=3),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.5, leading=11),
        "label": ParagraphStyle("l", parent=base["Normal"], fontSize=9, textColor=colors.HexColor(ACCENT),
                                fontName="Helvetica-Bold"),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, textColor=colors.HexColor(MUTED),
                                alignment=TA_CENTER, spaceBefore=8),
    }

    v = startup.get("verification") or {}
    flags = list(startup.get("compliance_flags") or [])
    domain = startup.get("domain") or "Industry"

    story: list[Any] = [
        Spacer(1, 0.6 * cm),
        Paragraph("AURA-3 Startup Evaluation", styles["title"]),
        Paragraph(
            f"{_escape(startup.get('name', 'Startup'))}<br/>Research snapshot: "
            f"{_escape(str(analysis.get('generated_at') or 'Unknown'))}<br/>"
            f"PDF exported {clock.now().strftime('%d %B %Y')}",
            styles["subtitle"],
        ),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(ACCENT), spaceAfter=10),
    ]

    verdict = Table([[
        Paragraph(f"<b>{str(analysis['overall_score']) + '/10' if analysis['overall_score'] is not None else 'Unavailable'}</b><br/>AI score", styles["body"]),
        Paragraph(f"<b>{analysis['recommendation_label']}</b><br/>Recommendation", styles["body"]),
        Paragraph(
            f"<b>{'MCA VERIFIED' if v.get('mca_verified') else 'MCA NOT VERIFIED'}</b><br/>"
            f"{_escape(', '.join(flags)) if flags else 'No compliance flags'}",
            styles["body"],
        ),
    ]], colWidths=[5.5 * cm] * 3)
    verdict.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#ecfdf5" if v.get("mca_verified") else "#fef2f2")),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [verdict, Spacer(1, 0.4 * cm)]

    info = [
        ("Startup", startup.get("name")), ("Domain", domain), ("Stage", startup.get("stage")),
        ("Funding ask", startup.get("funding_required")), ("Team", startup.get("team")),
        ("CIN", v.get("cin")), ("Registered name", v.get("company_name")),
        ("Company status", v.get("company_status")),
        ("Directors", ", ".join(v.get("directors") or [])), ("Startup ID", startup.get("startup_id")),
    ]
    info_table = Table(
        [[Paragraph(k, styles["label"]), Paragraph(_escape(str(val)), styles["body"])] for k, val in info if val],
        colWidths=[4 * cm, 12.5 * cm],
    )
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [info_table, Spacer(1, 0.3 * cm)]
    story.append(Paragraph("Product", styles["section"]))
    story.append(Paragraph(_inline(startup.get("description") or "N/A"), styles["body"]))

    story += [PageBreak(), Paragraph("Market & scoring visuals", styles["section"])]
    story.append(Paragraph(_inline(analysis["market_sizing"].get("basis", "")), styles["body"]))
    story.append(Paragraph(
        "Source-reported figures and publisher forecasts retain their original dates. Company figures are "
        "unverified claims. Search excerpts provide traceability, not independent verification. "
        "AI scores are analytical judgments. Missing figures and years are not synthesized.", styles["body"],
    ))
    for gap in analysis["data_gaps"]:
        story.append(Paragraph(_escape(gap), styles["bullet"]))

    def evidence_notes(label: str, metric: dict) -> None:
        source = _escape(metric["source_title"] or metric.get("source_url") or "Company documents")
        if metric.get("source_url"):
            source = f"<link href='{_escape(metric['source_url'])}' color='{ACCENT}'>{source}</link>"
        scope = " · ".join(filter(None, [metric.get("market"), metric.get("geography")]))
        story.append(Paragraph(
            f"<b>{_escape(label)}</b>: {metric['value']:,.8g} {_escape(metric['unit'])} · "
            f"{_escape(str(metric.get('year') or metric.get('period')))} · {KIND_LABELS[metric['kind']]}<br/>"
            f"{_escape(scope)}<br/>Source: {source}"
            + (f" · retrieved {_escape(metric['retrieved_at'])}" if metric.get("retrieved_at") else "")
            + f"<br/>Evidence excerpt: {_escape(metric['quote'])}", styles["body"],
        ))

    def chart_image(chart: io.BytesIO) -> None:
        picture = RLImage(chart)
        picture.drawWidth = 15.5 * cm
        picture.drawHeight = picture.imageHeight * picture.drawWidth / picture.imageWidth
        story.extend([picture, Spacer(1, 0.3 * cm)])

    chart_image(market_opportunity_chart(analysis, domain))
    for key, metric in analysis["market_sizing"]["evidence"].items():
        evidence_notes(key.replace("_usd_b", "").replace("_pct", "").upper(), metric)
    for key, metric in (analysis["market_sizing"].get("claims") or {}).items():
        check = CLAIM_CHECKS.get((metric.get("check") or {}).get("status"), CLAIM_CHECKS["unverified"])
        evidence_notes(key.replace("_usd_b", "").replace("_pct", "").upper() + f" — deck claim, {check}", metric)
    chart_image(market_trend_chart(analysis, domain))
    for metric in analysis["market_sizing"]["trend"]:
        evidence_notes(f"Market {metric['year']}", metric)
    chart_image(scorecard_chart(analysis))
    chart_image(revenue_chart(analysis))
    for metric in analysis["projected_revenue"]:
        evidence_notes(f"{metric['metric']} {metric['year']}", metric)

    story.append(PageBreak())
    for number, (key, title) in enumerate(SECTION_TITLES.items(), start=1):
        story.append(Paragraph(f"{number}. {title}", styles["section"]))
        story += _markdown_flowables(printable_citations(analysis["sections"].get(key, ""), analysis), styles)

    if analysis.get("sources"):
        story.append(Paragraph("Research sources", styles["section"]))
        for s in analysis["sources"]:
            story.append(Paragraph(
                f"• <link href='{_escape(s['url'])}' color='#0f6b5f'>{_escape(s['title'] or s['url'])}</link>"
                + (f" · retrieved {_escape(s['retrieved_at'])}" if s.get("retrieved_at") else ""),
                styles["bullet"],
            ))

    story += [
        Spacer(1, 0.6 * cm),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(LINE)),
        Paragraph(
            "Generated by the AURA-3 AI evaluation engine from the saved research snapshot. "
            "Forecasts are not actual results. Source excerpts and company claims are not independently audited. "
            "Not financial advice.",
            styles["small"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
