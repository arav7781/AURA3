"""Pitch decks the copilot writes. The model fills in a draft (validated slide content, never code) and it is
rendered with the same design as the seeded decks, so a founder's new deck looks like the rest of AURA3 and
reads back cleanly through TitanOCR."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from aura.decks.design import Brand
from aura.decks.slides import Slide
from aura.decks.theme import PALETTES, Palette, with_brand

Kind = Literal["cover", "problem", "solution", "market", "business_model", "traction", "unit_economics",
               "competition", "gtm", "roadmap", "team", "ask", "custom"]

# A figure as founders write it: an amount with its currency and scale, a percentage, a multiple, a count.
FIGURE = re.compile(r"(?:Rs\.?|USD|INR|₹|\$)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:crore|cr|lakh|million|billion|[MBK]\b))?"
                    r"|\d[\d,]*(?:\.\d+)?\s?(?:%|x\b)|\b\d{1,3}(?:,\d{2,3})+\b|\b\d+\.\d+\b")


class DraftStat(BaseModel):
    value: str = Field(max_length=24, description="The figure, e.g. 'Rs 1.6 crore', '4.0x', '3.1%'")
    label: str = Field(max_length=80, description="What it measures, e.g. 'ARR, FY2026'")


class DraftChart(BaseModel):
    title: str = Field(max_length=60, description="e.g. 'ARR (Rs crore)'")
    labels: list[str] = Field(min_length=2, max_length=8, description="e.g. ['FY2024', 'FY2025', 'FY2026']")
    values: list[float] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _same_length(self) -> "DraftChart":
        if len(self.labels) != len(self.values):
            raise ValueError("chart labels and values must have the same length")
        return self


class DraftSlide(BaseModel):
    kind: Kind = Field(description="cover first; 'custom' for anything else (e.g. a customer quote or roadmap)")
    title: str = Field(max_length=70, description="Short slide title, e.g. 'Traction'")
    subtitle: str | None = Field(default=None, max_length=220, description="One-sentence headline of the slide")
    bullets: list[str] = Field(default_factory=list, max_length=7,
                               description="'Label: detail' lines, each under 200 characters; the label is shown bold")
    stats: list[DraftStat] = Field(default_factory=list, max_length=4, description="Headline figures shown as big tiles")
    table: list[list[str]] | None = Field(default=None, description="First row is the header; at most 7 rows, 4 columns")
    chart: DraftChart | None = Field(default=None, description="A bar chart, e.g. ARR by year")

    @field_validator("bullets")
    @classmethod
    def _short_bullets(cls, bullets: list[str]) -> list[str]:
        if any(len(b) > 220 for b in bullets):
            raise ValueError("keep each bullet under 220 characters")
        return [b.strip() for b in bullets if b.strip()]

    @field_validator("table")
    @classmethod
    def _rectangular(cls, table: list[list[str]] | None) -> list[list[str]] | None:
        if not table:
            return None
        cols = min(4, max(len(row) for row in table))
        return [[str(cell) for cell in (row + [""] * cols)[:cols]] for row in table[:8]]


Theme = Literal["aura", "aura_dark", "ocean", "vibrant", "graphite"]
HEX = r"^#?[0-9a-fA-F]{6}$"


class DeckDesign(BaseModel):
    theme: Theme = Field(default="aura", description=(
        "aura: AURA3's light jade and marigold (default); aura_dark: evergreen night, light text on dark; ocean: "
        "light, blue to cyan; vibrant: light, purple to pink to orange; graphite: minimal black and grey, red accent"))
    brand_color: str | None = Field(default=None, pattern=HEX,
                                    description="The startup's brand colour, e.g. '#E11D48': recolours the theme around it")
    accent_color: str | None = Field(default=None, pattern=HEX, description="Optional second colour for highlights")

    def palette(self) -> Palette:
        base = PALETTES[self.theme]
        return with_brand(base, self.brand_color, self.accent_color) if self.brand_color else base

    def label(self) -> str:
        label = PALETTES[self.theme].label
        return f"{label}, brand {self.brand_color.lstrip('#').upper()}" if self.brand_color else label


class DeckDraft(BaseModel):
    slides: list[DraftSlide] = Field(min_length=3, max_length=14, description="The whole deck in order, cover first")
    design: DeckDesign = Field(default_factory=DeckDesign, description="The look; the content is the same in any design")


MARKER = re.compile(r"\s?\[(?:c|w)\s?:[^\]]{1,20}\]")


def clean(text: str) -> str:
    """Slide text without the chat's citation markers ([c:…], [w:3]), which mean nothing on a slide."""
    return MARKER.sub("", text).strip()


def draft_slides(brand: Brand, draft: DeckDraft) -> list[Slide]:
    """Draft → slides. The cover always carries the legal name and CIN (the footer does too)."""
    slides: list[Slide] = []
    for item in draft.slides:
        key = "title" if item.kind == "cover" else item.kind
        bullets = [clean(b) for b in item.bullets]
        if key == "title":
            where = " · ".join(t for t in (f"CIN {brand.cin}" if brand.cin else None, brand.city) if t)
            stated = any("CIN" in b for b in bullets)
            bullets = [brand.legal_name, *([where] if where and not stated else []),
                       *(b for b in bullets if b != brand.legal_name)]
        chart = ({"title": clean(item.chart.title), "labels": item.chart.labels, "values": item.chart.values}
                 if item.chart else None)
        table = [[clean(cell) for cell in row] for row in item.table] if item.table else None
        slides.append(Slide(key, brand.name if key == "title" else clean(item.title),
                            clean(item.subtitle) if item.subtitle else None, bullets, table, chart,
                            stats=[(clean(s.value), clean(s.label)) for s in item.stats]))
    if slides[0].key != "title":
        slides.insert(0, Slide("title", brand.name, None, [brand.legal_name]))
    return slides


def figures(draft: DeckDraft) -> list[str]:
    """Every figure the draft states, to check that it survives rendering and TitanOCR's read-back."""
    texts: list[str] = []
    for item in draft.slides:
        texts += [item.title, item.subtitle or "", *item.bullets, *(f"{s.value}" for s in item.stats)]
        texts += [cell for row in item.table or [] for cell in row]
    found = {normalise(m.group(0)) for text in texts for m in FIGURE.finditer(text)}
    return sorted(f for f in found if any(ch.isdigit() for ch in f))


def normalise(text: str) -> str:
    return re.sub(r"[\s,]", "", text).lower().replace("₹", "rs").replace("rs.", "rs")
