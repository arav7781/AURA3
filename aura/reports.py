"""Investor PDF report: ReportLab layout with Matplotlib charts built from the analysis."""

import io
import re
from datetime import datetime
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from aura.evaluation import SCORE_DIMENSIONS, SECTION_TITLES
from aura.mca import consistency_flags

INK, ACCENT, MUTED, LINE = "#0f172a", "#0f6b5f", "#64748b", "#e2e8f0"
CHART_BG, BAR_COLORS = "#ffffff", ["#0f6b5f", "#2a9d8f", "#8ecae6"]


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


def market_opportunity_chart(analysis: Dict[str, Any], domain: str) -> io.BytesIO:
    m = analysis["market_sizing"]
    values = [m["tam_usd_b"], m["sam_usd_b"], m["som_usd_b"]]
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=CHART_BG)
    bars = ax.bar(["TAM", "SAM", "SOM"], values, color=BAR_COLORS, width=0.55)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"${value:,.2f}B",
                ha="center", va="bottom", color=INK, fontsize=10, fontweight="bold")
    ax.set_ylabel("USD billions", color=MUTED, fontsize=9)
    ax.set_ylim(0, max(values) * 1.2 or 1)
    _style_axes(ax, f"Market opportunity — {domain}")
    return _png(fig)


def scorecard_chart(analysis: Dict[str, Any]) -> io.BytesIO:
    scores = analysis["category_scores"]
    labels = [SCORE_DIMENSIONS[k] for k in SCORE_DIMENSIONS]
    values = [scores[k] for k in SCORE_DIMENSIONS]
    fig, ax = plt.subplots(figsize=(7, 3.8), facecolor=CHART_BG)
    bars = ax.barh(labels[::-1], values[::-1], color=ACCENT, height=0.55)
    for bar, value in zip(bars, values[::-1]):
        ax.text(value + 0.12, bar.get_y() + bar.get_height() / 2, f"{value:.1f}/10",
                va="center", color=INK, fontsize=9, fontweight="bold")
    ax.set_xlim(0, 10.8)
    _style_axes(ax, f"AI evaluation scorecard — overall {analysis['overall_score']:.1f}/10")
    return _png(fig)


def market_trend_chart(analysis: Dict[str, Any], domain: str) -> io.BytesIO:
    m = analysis["market_sizing"]
    years = [p["year"] for p in m["trend"]]
    sizes = [p["size_usd_b"] for p in m["trend"]]
    base = datetime.utcnow().year
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=CHART_BG)
    hist = [(y, s) for y, s in zip(years, sizes) if y <= base]
    proj = [(y, s) for y, s in zip(years, sizes) if y >= base]
    ax.plot(*zip(*hist), color=ACCENT, linewidth=2.4, marker="o", label="Historical (est.)")
    ax.plot(*zip(*proj), color=ACCENT, linewidth=2.4, marker="o", linestyle="--", label="Projected")
    ax.fill_between(years, sizes, alpha=0.08, color=ACCENT)
    ax.set_ylabel("USD billions", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, labelcolor=MUTED)
    _style_axes(ax, f"Market growth — {domain} ({m['cagr_pct']:.1f}% CAGR)")
    return _png(fig)


def revenue_chart(analysis: Dict[str, Any]) -> io.BytesIO:
    rows = analysis["projected_revenue"]
    fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=CHART_BG)
    ax.bar([str(r["year"]) for r in rows], [r["revenue_musd"] for r in rows], color="#2a9d8f", width=0.55)
    ax.set_ylabel("USD millions", color=MUTED, fontsize=9)
    _style_axes(ax, "Projected revenue (analyst estimate)")
    return _png(fig)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"<link href='\2' color='#0f6b5f'>\1</link>", text)


def _markdown_flowables(md: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    flowables: List[Any] = []
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


def build_pdf_report(startup: Dict[str, Any], analysis: Dict[str, Any]) -> bytes:
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
    flags = consistency_flags(startup)
    domain = startup.get("domain") or "Industry"

    story: List[Any] = [
        Spacer(1, 0.6 * cm),
        Paragraph("AURA-3 Startup Evaluation", styles["title"]),
        Paragraph(
            f"{_escape(startup.get('name', 'Startup'))} &nbsp;·&nbsp; generated "
            f"{datetime.utcnow().strftime('%d %B %Y')} &nbsp;·&nbsp; LangGraph multi-agent pipeline",
            styles["subtitle"],
        ),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(ACCENT), spaceAfter=10),
    ]

    verdict = Table([[
        Paragraph(f"<b>{analysis['overall_score']:.1f}/10</b><br/>Overall score", styles["body"]),
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
    charts = [market_opportunity_chart(analysis, domain), market_trend_chart(analysis, domain), scorecard_chart(analysis)]
    if analysis["projected_revenue"]:
        charts.append(revenue_chart(analysis))
    for chart in charts:
        story += [RLImage(chart, width=15.5 * cm, height=8 * cm), Spacer(1, 0.3 * cm)]

    story.append(PageBreak())
    for number, (key, title) in enumerate(SECTION_TITLES.items(), start=1):
        story.append(Paragraph(f"{number}. {title}", styles["section"]))
        story += _markdown_flowables(analysis["sections"].get(key, ""), styles)

    if analysis.get("sources"):
        story.append(Paragraph("Sources", styles["section"]))
        for s in analysis["sources"]:
            story.append(Paragraph(
                f"• <link href='{_escape(s['url'])}' color='#0f6b5f'>{_escape(s['title'] or s['url'])}</link>",
                styles["bullet"],
            ))

    story += [
        Spacer(1, 0.6 * cm),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(LINE)),
        Paragraph(
            "Generated by the AURA-3 AI evaluation engine. Figures marked as estimates come from the model and "
            "public web sources; verify before making investment decisions. Not financial advice.",
            styles["small"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
