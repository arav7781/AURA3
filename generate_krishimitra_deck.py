"""Generate a downloadable KrishiMitra AI pitch deck as both PDF and PPTX.

The deck embeds explicit, source-labelled market figures (TAM / SAM / SOM), dated
ARR/revenue numbers and unit economics so the AURA-3 evaluation engine can extract
real statistics into the investor report.

Run:  .venv/bin/python generate_krishimitra_deck.py
Output:  KrishiMitra_AI_Pitch_Deck.pdf  and  KrishiMitra_AI_Pitch_Deck.pptx
"""

from __future__ import annotations

import os

# ─── Deck content (single source of truth for both PDF and PPTX) ──────────────

COMPANY = "KrishiMitra AI Private Limited"
CIN = "U62099MH2024PTC410567"
TAGLINE = "Solar soil sensors + WhatsApp crop advisory for India's smallholder farmers"

# Real-world market anchors (dated, source-labelled)
# Source: MarketsandMarkets — India Agriculture IoT Market (2025-2030)
INDIA_AGRI_IOT_2025_USD_M = 82.3
INDIA_AGRI_IOT_2030_USD_M = 154.8
INDIA_AGRI_IOT_CAGR = 13.5

SLIDES = [
    {
        "title": "KrishiMitra AI",
        "subtitle": TAGLINE,
        "bullets": [
            f"{COMPANY}",
            f"CIN {CIN} · Pune, Maharashtra · Incorporated 2024",
            "Seed round: raising Rs 12 crore at Rs 60 crore pre-money",
            "Team: Arav · Mahi · Kartik · Adesh",
        ],
    },
    {
        "title": "Problem",
        "bullets": [
            "146 million agricultural holdings in India; ~86% are smallholders "
            "farming under 2 hectares (Source: Agriculture Census 2015-16).",
            "Smallholders lack affordable, real-time soil and irrigation data, "
            "leading to 20-30% avoidable input waste on water and fertiliser.",
            "Existing advisory apps are English/UI-heavy and priced for agri-businesses, "
            "not for a farmer earning Rs 8,000-12,000 per month.",
            "Language barrier: most advisory content is not available in Marathi or Hindi voice/text.",
        ],
    },
    {
        "title": "Solution",
        "bullets": [
            "Rs 1,499 solar-powered soil sensor: measures moisture, temperature and NPK proxy.",
            "WhatsApp crop-advisory subscription in Marathi and Hindi (text + voice notes).",
            "AI advisory tuned to local crop calendars: sowing, irrigation timing, pest alerts.",
            "No smartphone app install required — runs entirely inside WhatsApp.",
        ],
    },
    {
        "title": "Market Opportunity (TAM / SAM / SOM)",
        "bullets": [
            "TAM — India Agriculture IoT market: USD 82.3M in 2025, projected USD 154.8M by 2030 "
            "at 13.5% CAGR (Source: MarketsandMarkets, India Agriculture IoT Market 2025-2030).",
            "SAM — Marathi/Hindi smallholder segment (Maharashtra, Karnataka, MP): "
            "USD 24.7M in 2025 (~30% of India Agri-IoT TAM, company estimate).",
            "SOM — 3-year obtainable share of SAM: USD 3.7M in 2028 "
            "(~15% of SAM, company projection).",
            "India agri-IoT segment CAGR: 13.5% (2025-2030).",
        ],
    },
    {
        "title": "Business Model",
        "bullets": [
            "Hardware: Rs 1,499 one-time solar soil sensor (32% of revenue).",
            "Subscription: Rs 149/month WhatsApp advisory (68% of revenue).",
            "Subscription gross margin: 78%.",
            "Blended CAC: Rs 610 · Payback period: 4.1 months.",
        ],
    },
    {
        "title": "Traction (as of FY2025)",
        "bullets": [
            "12,400 paying farmers across 9 districts of Maharashtra.",
            "ARR: Rs 3.1 crore in FY2025 (68% subscription, 32% sensor sales).",
            "Net Revenue Retention (NRR): 121%.",
            "Monthly churn: 2.4%.",
        ],
    },
    {
        "title": "Unit Economics",
        "bullets": [
            "CAC: Rs 610 per farmer.",
            "Payback: 4.1 months.",
            "Subscription gross margin: 78%.",
            "NRR 121% with 2.4% monthly churn implies strong expansion within cohorts.",
        ],
    },
    {
        "title": "Competitive Landscape",
        "bullets": [
            "Fasal — IoT sensors + AI for horticulture (B2B/premium farms).",
            "Cropin — agritech SaaS, Rs 38.5 crore revenue FY25 (enterprise focus).",
            "DeHaat — full-stack agri platform (~USD 800M valuation reference).",
            "BharatAgri — B2C farm advisory, shut down 2025 amid funding crunch: "
            "our moat is low-cost hardware lock-in + vernacular WhatsApp distribution.",
        ],
    },
    {
        "title": "Go-to-Market & Expansion",
        "bullets": [
            "Proven in 9 Maharashtra districts via village-level agri-retailer partnerships.",
            "Seed capital funds expansion into Karnataka and Madhya Pradesh.",
            "Channel: agri-input dealers, FPOs (Farmer Producer Organisations), NABARD-linked programs.",
            "Target: 40,000 paying farmers across 3 states within 24 months.",
        ],
    },
    {
        "title": "Team",
        "bullets": [
            "Arav — Co-founder (Product & AI).",
            "Mahi — Co-founder (Field Operations & Distribution).",
            "Kartik — Co-founder (Hardware & Supply Chain).",
            "Adesh — Co-founder (Growth & Partnerships).",
        ],
    },
    {
        "title": "The Ask",
        "bullets": [
            "Raising Rs 12 crore seed at Rs 60 crore pre-money (Rs 72 crore post).",
            "Implied ~19x ARR multiple on Rs 3.1 crore ARR.",
            "Use of funds: 45% distribution/expansion, 30% product & AI, 15% hardware, 10% working capital.",
            "Milestone: 40,000 paying farmers and Rs 10 crore ARR within 24 months.",
        ],
    },
]

# ─── Colour palette ───────────────────────────────────────────────────────────
GREEN = (0x2E, 0x7D, 0x32)
DARK = (0x1B, 0x2A, 0x1B)
LIGHT = (0xF1, 0xF8, 0xE9)
ACCENT = (0xF9, 0xA8, 0x25)


def build_pdf(path: str) -> None:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    width, height = landscape(A4)
    c = canvas.Canvas(path, pagesize=landscape(A4))

    for i, slide in enumerate(SLIDES):
        # Background band
        c.setFillColorRGB(*[v / 255 for v in LIGHT])
        c.rect(0, 0, width, height, fill=1, stroke=0)
        c.setFillColorRGB(*[v / 255 for v in GREEN])
        c.rect(0, height - 3.2 * cm, width, 3.2 * cm, fill=1, stroke=0)

        # Title
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(2 * cm, height - 2.1 * cm, slide["title"])

        y = height - 4.8 * cm

        if "subtitle" in slide:
            c.setFillColorRGB(*[v / 255 for v in DARK])
            c.setFont("Helvetica-Oblique", 15)
            c.drawString(2 * cm, y, slide["subtitle"])
            y -= 1.3 * cm

        c.setFillColorRGB(*[v / 255 for v in DARK])
        for bullet in slide["bullets"]:
            c.setFillColorRGB(*[v / 255 for v in ACCENT])
            c.circle(2.3 * cm, y + 0.15 * cm, 0.12 * cm, fill=1, stroke=0)
            c.setFillColorRGB(*[v / 255 for v in DARK])
            c.setFont("Helvetica", 13)
            lines = _wrap(bullet, 95)
            for line in lines:
                c.drawString(2.8 * cm, y, line)
                y -= 0.75 * cm
            y -= 0.25 * cm

        # Footer
        c.setFillColorRGB(*[v / 255 for v in GREEN])
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, 1 * cm, f"{COMPANY}  ·  {CIN}")
        c.drawRightString(width - 2 * cm, 1 * cm, f"{i + 1} / {len(SLIDES)}")
        c.showPage()

    c.save()


def _wrap(text: str, max_chars: int):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_pptx(path: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    green = RGBColor(*GREEN)
    dark = RGBColor(*DARK)
    light = RGBColor(*LIGHT)
    accent = RGBColor(*ACCENT)

    for i, slide in enumerate(SLIDES):
        s = prs.slides.add_slide(blank)

        # Background
        bg = s.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = light

        # Title band
        band = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(1.5))
        band.fill.solid()
        band.fill.fore_color.rgb = green
        band.line.fill.background()
        tf = band.text_frame
        tf.margin_left = Inches(0.5)
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = slide["title"]
        p.font.size = Pt(30)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)

        # Body
        box = s.shapes.add_textbox(Inches(0.7), Inches(1.9), Inches(12), Inches(5.2))
        btf = box.text_frame
        btf.word_wrap = True

        first = True
        if "subtitle" in slide:
            p = btf.paragraphs[0]
            p.text = slide["subtitle"]
            p.font.size = Pt(18)
            p.font.italic = True
            p.font.color.rgb = green
            first = False

        for bullet in slide["bullets"]:
            p = btf.paragraphs[0] if first else btf.add_paragraph()
            first = False
            p.text = "•  " + bullet
            p.font.size = Pt(16)
            p.font.color.rgb = dark
            p.space_after = Pt(10)

        # Footer
        foot = s.shapes.add_textbox(Inches(0.5), Inches(7.0), Inches(12.3), Inches(0.4))
        ftf = foot.text_frame
        fp = ftf.paragraphs[0]
        fp.text = f"{COMPANY}  ·  {CIN}  ·  Slide {i + 1}/{len(SLIDES)}"
        fp.font.size = Pt(9)
        fp.font.color.rgb = green

    prs.save(path)


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(here, "KrishiMitra_AI_Pitch_Deck.pdf")
    pptx_path = os.path.join(here, "KrishiMitra_AI_Pitch_Deck.pptx")
    build_pdf(pdf_path)
    build_pptx(pptx_path)
    print(f"Wrote {pdf_path}")
    print(f"Wrote {pptx_path}")


if __name__ == "__main__":
    main()
