"""Slide design: lays every slide out as a list of shapes (cards, gradients, text lines, pictures) that the PDF
and PPTX renderers both draw, so the two formats always match.

The look follows a modern product deck: a soft jade-to-marigold wash, the startup's mark in the corner, a
letter-spaced section label over a heavy title, and content in white cards with gradient accents, big
figures and a tranche timeline. Each slide type gets its own composition.

Layouts are also built to be read back by TitanOCR: prose sits in stacked full-width cards (side-by-side
prose columns get merged into one block or mistaken for a table), grids hold only short stat tiles with wide
gutters, figures stay smaller than the title (the chunker takes the tallest header line as the title), and
there are no round glyph-like badges that OCR would read as "o".

Text is never rewritten: every bullet appears whole, in reading order, so extraction and citations see the
same sentences as before (figures pulled out for stat cards are repeated, not moved). Coordinates are PDF
points with the origin at the bottom left.
"""

import math
import re
from contextvars import ContextVar
from dataclasses import dataclass, field

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth

from aura.decks import art
from aura.decks.slides import STAGE_LABELS, Slide
from aura.decks.spec import StartupSpec
from aura.decks.theme import (
    AURA,
    BLACK,
    BOLD,
    LIGHT,
    MEDIUM,
    MONO,
    REGULAR,
    RGB,
    SEMIBOLD,
    WHITE,
    Palette,
    register_fonts,
)

W, H = landscape(A4)
M = 50  # side margin
BOTTOM = 58  # lowest point of the body
GAP = 16
TILE_GAP = 30  # wide enough that OCR keeps neighbouring tiles' figures on separate lines
SECTIONS = {
    "title": "Pitch deck", "problem": "The problem", "solution": "Our solution", "market": "Market",
    "business_model": "Business model", "traction": "Traction", "unit_economics": "Unit economics",
    "competition": "Competition", "gtm": "Go-to-market", "team": "The team", "ask": "The ask",
    "roadmap": "Roadmap", "custom": "Highlights",
}
FIGURE = re.compile(r"(?:Rs|USD|INR)\s?\d[\d,]*(?:\.\d+)?\s?(?:crore|lakh|million|billion|[MBK]\b)?"
                    r"|\d[\d,]*(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?(?:x\b|months?\b|days?\b|years?\b|lakh\b|crore\b)"
                    r"|\d[\d,]*(?:\.\d+)?")
BODY_SIZES = (14, 13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5)
_PALETTE: ContextVar[Palette] = ContextVar("deck_palette", default=AURA)


def pal() -> Palette:
    """The colours of the deck being laid out (set by ``lay_out``)."""
    return _PALETTE.get()


# ── whose deck ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Brand:
    """Who a deck belongs to: what its logo, footer, cover and ask slide show."""
    name: str
    legal_name: str
    stage: str
    domain: str
    cin: str | None = None
    city: str | None = None
    ask_inr: int | None = None
    pre_money_inr: int | None = None
    min_raise_pct: int | None = None

    @classmethod
    def from_spec(cls, spec: StartupSpec) -> "Brand":
        return cls(spec.name, spec.legal_name, spec.stage, spec.domain, spec.mca.cin, spec.hq.city,
                   spec.round.ask_inr, spec.round.pre_money_inr, spec.round.min_raise_pct)


# ── shapes ──────────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Fill:
    """A rectangle (rounded with ``radius``). With ``gradient`` the colours run left to right (or bottom to top
    when ``vertical``) over a solid ``colour`` base."""
    x: float
    y: float
    w: float
    h: float
    colour: RGB | None = None
    radius: float = 0
    gradient: list[RGB] | None = None
    vertical: bool = False
    stroke: RGB | None = None
    stroke_width: float = 0.75


@dataclass
class Disc:
    cx: float
    cy: float
    r: float
    colour: RGB
    gradient: list[RGB] | None = None


@dataclass
class Shadow:
    """A soft drop shadow under a card (PDF only: stacked translucent shapes)."""
    x: float
    y: float
    w: float
    h: float
    radius: float


@dataclass
class Span:
    text: str
    font: str
    size: float
    colour: RGB


@dataclass
class Line:
    """One line of text; ``y`` is the baseline."""
    x: float
    y: float
    spans: list[Span]
    tracking: float = 0
    align: str = "left"

    @property
    def width(self) -> float:
        return sum(measure(s.text, s.font, s.size, self.tracking) for s in self.spans)


@dataclass
class Picture:
    x: float
    y: float
    w: float
    h: float
    png: bytes


Shape = Fill | Disc | Shadow | Line | Picture


@dataclass
class Page:
    shapes: list[Shape] = field(default_factory=list)
    palette: Palette = AURA
    hidden: list[Line] = field(default_factory=list)  # adversarial decks: drawn white on the background
    notes: str | None = None

    def add(self, *shapes: Shape) -> None:
        self.shapes.extend(shapes)


@dataclass
class Area:
    x: float
    top: float
    w: float
    h: float


# ── text ────────────────────────────────────────────────────────────────────────────────────────────────

Runs = list[tuple[str, str]]  # (text, font)


def measure(text: str, font: str, size: float, tracking: float = 0) -> float:
    register_fonts()
    return stringWidth(text, font, size) + tracking * len(text)


def wrap(runs: Runs, size: float, width: float) -> list[Runs]:
    """Greedy word wrap across font runs. Each line is a list of (text, font) segments with their spaces."""
    words = [(word, font) for text, font in runs for word in text.split()]
    lines: list[list[tuple[str, str]]] = []
    line: list[tuple[str, str]] = []
    used = 0.0
    for word, font in words:
        w = measure(word, font, size)
        gap = measure(" ", line[-1][1], size) if line else 0.0
        if line and used + gap + w > width:
            lines.append(line)
            line, used, gap = [], 0.0, 0.0
        line.append((word, font))
        used += gap + w
    if line:
        lines.append(line)
    out: list[Runs] = []
    for words_on_line in lines:
        segments: Runs = []
        for i, (word, font) in enumerate(words_on_line):
            text = word + (" " if i < len(words_on_line) - 1 else "")
            if segments and segments[-1][1] == font:
                segments[-1] = (segments[-1][0] + text, font)
            else:
                segments.append((text, font))
        out.append(segments)
    return out or [[("", REGULAR)]]


def labelled(text: str, font: str = REGULAR) -> Runs:
    """Bold the label of 'Label: …' or 'Label — …' lines."""
    for sep in (" — ", ": "):
        at = text.find(sep)
        if 0 < at <= 42:
            return [(text[: at + len(sep)], BOLD), (text[at + len(sep):], font)]
    return [(text, font)]


def block_height(runs: Runs, size: float, width: float, leading: float = 1.38) -> float:
    return len(wrap(runs, size, width)) * size * leading


def text_block(page: Page, x: float, top: float, width: float, runs: Runs, size: float, *, colour: RGB | None = None,
               strong: RGB | None = None, leading: float = 1.38) -> float:
    """Wrapped text whose first line's cap height sits at ``top``. Returns the y below the block."""
    colour, strong = colour or pal().ink_2, strong or pal().ink
    y = top - size * 0.78
    for segments in wrap(runs, size, width):
        page.add(Line(x, y, [Span(t, f, size, strong if f in (BOLD, BLACK, SEMIBOLD) else colour) for t, f in segments]))
        y -= size * leading
    return top - len(wrap(runs, size, width)) * size * leading


def fit_size(text: str, font: str, width: float, start: float, smallest: float) -> float:
    size = start
    while measure(text, font, size) > width and size > smallest:
        size -= 0.5
    return size


def figure(text: str) -> str | None:
    match = FIGURE.search(text)
    return match.group(0).strip() if match else None


# ── components ──────────────────────────────────────────────────────────────────────────────────────────

def card(page: Page, x: float, y: float, w: float, h: float, *, bar: bool = False, side: bool = False,
         warm: bool = False) -> None:
    page.add(Shadow(x, y, w, h, 12), Fill(x, y, w, h, pal().card, radius=12, stroke=pal().card_edge, stroke_width=0.6))
    colours = pal().warm if warm else pal().gradient
    if bar:
        page.add(Fill(x + 18, y + h - 3.4, w - 36, 3.4, colours[0], radius=1.7, gradient=colours))
    if side:
        page.add(Fill(x, y + h * 0.18, 3.6, h * 0.64, colours[0], radius=1.8, gradient=colours[::-1], vertical=True))


def logo(page: Page, spec: Brand) -> None:
    """The startup's mark and name, and its round, in the top band (repeated on every slide, so ingestion
    treats it as a running header)."""
    y = H - 48
    page.add(Fill(M, y, 20, 20, pal().primary, radius=6, gradient=pal().gradient), Disc(M + 10, y + 10, 3.4, pal().on_primary))
    page.add(Line(M + 28, y + 6, [Span(spec.name, SEMIBOLD, 10.5, pal().ink)]))
    tag = f"{STAGE_LABELS[spec.stage]} round  ·  {spec.domain}"
    width = measure(tag, MEDIUM, 7.5) + 20
    page.add(Fill(W - M - width, y + 1, width, 18, None, radius=9, stroke=pal().line, stroke_width=0.7),
             Line(W - M - 10, y + 7, [Span(tag, MEDIUM, 7.5, pal().ink_3)], align="right"))


def footer(page: Page, spec: Brand, number: int, total: int) -> None:
    page.add(Line(M, 24, [Span(f"{spec.legal_name}  ·  CIN {spec.cin}" if spec.cin else spec.legal_name, REGULAR, 7.5,
                               pal().ink_3)]),
             Line(W - M, 24, [Span(f"{number:02d} / {total:02d}", MONO, 7.5, pal().ink_3)], align="right"))


def header(page: Page, slide: Slide, number: int) -> float:
    """Section label, title and subtitle. Returns the top of the body."""
    page.add(Line(M, H - 86, [Span(f"{number:02d}  ·  {SECTIONS.get(slide.key, slide.key).upper()}", SEMIBOLD, 9,
                                   pal().primary)], tracking=1.8))
    size = fit_size(slide.title, BLACK, W - 2 * M, 31, 18)
    page.add(Line(M, H - 118, [Span(slide.title, BLACK, size, pal().ink)]))
    top = H - 134
    if slide.subtitle:
        width = 700
        sub = next(s for s in (14, 13, 12, 11, 10) if len(wrap([(slide.subtitle, LIGHT)], s, width)) <= 2 or s == 10)
        top = text_block(page, M, top, width, [(slide.subtitle, LIGHT)], sub, colour=pal().ink_2, strong=pal().ink_2,
                         leading=1.36) - 4
    return top - 18


def balanced(area: Area, height: float) -> float:
    """Where a block of ``height`` starts so it sits a little above the middle of ``area``."""
    return area.top - max(0.0, area.h - height) * 0.38


def stack(page: Page, items: list[Runs], area: Area, *, min_h: float = 0, gap: float = 12, centre: bool = True,
          sizes: tuple[float, ...] = BODY_SIZES) -> float:
    """One full-width card per item, stacked, with a gradient side bar; text as large as fits. Tightens when
    space runs short (no minimum height, thinner padding), and past that puts every item in one list card,
    so nothing ever runs off the slide. Returns the y below the stack."""
    if not items:
        return area.top
    pad_x = 24
    width = area.w - pad_x * 2 - 6
    fit: tuple[float, list[float], float, float] | None = None
    for floor, pad_y, spacing in ((min_h, 15, gap), (0, 9, 7)):
        for size in sizes:
            heights = [max(block_height(item, size, width, 1.36) + 2 * pad_y, floor) for item in items]
            if sum(heights) + spacing * (len(items) - 1) <= area.h:
                fit = (size, heights, pad_y, spacing)
                break
        if fit:
            break
    if fit is None:
        return list_card(page, items, area)
    size, heights, _pad, spacing = fit
    total = sum(heights) + spacing * (len(items) - 1)
    y = balanced(area, total) if centre else area.top
    for item, h in zip(items, heights, strict=True):
        card(page, area.x, y - h, area.w, h, side=True)
        text_h = block_height(item, size, width, 1.36)
        text_block(page, area.x + pad_x + 6, y - (h - text_h) / 2, width, item, size, leading=1.36)
        y -= h + spacing
    return y + spacing


def list_card(page: Page, items: list[Runs], area: Area) -> float:
    """Every item in one card, separated by a little space: the most compact way to show many points."""
    pad = 18
    width = area.w - 2 * pad - 6
    size = 7.5
    for size in (*BODY_SIZES, 8, 7.5):
        if sum(block_height(item, size, width, 1.32) for item in items) + 6 * (len(items) - 1) + 2 * pad <= area.h:
            break
    h = min(area.h, sum(block_height(item, size, width, 1.32) for item in items) + 6 * (len(items) - 1) + 2 * pad)
    card(page, area.x, area.top - h, area.w, h, side=True)
    y = area.top - pad
    for item in items:
        y = text_block(page, area.x + pad + 6, y, width, item, size, leading=1.32) - 6
    return area.top - h


def stat_cards(page: Page, stats: list[tuple[str, Runs]], area: Area, *, cols: int, warm_last: bool = False,
               min_h: float = 0, centre: bool = False) -> float:
    """Big figure over its caption, like a dashboard tile. Returns the y below."""
    rows = math.ceil(len(stats) / cols)
    gutter = TILE_GAP
    width = (area.w - gutter * (cols - 1)) / cols
    pad = 20
    big_size = 26
    caption = 12.5
    for big_size, caption in ((26, 12.5), (25, 12), (24, 11.5), (22, 11), (21, 10.5), (20, 10), (18, 9.5), (17, 9), (16, 8.5)):
        tallest = max(block_height(runs, caption, width - 2 * pad, 1.34) for _, runs in stats)
        h = 22 + big_size * 1.25 + 8 + tallest + pad
        if rows * h + GAP * (rows - 1) <= area.h:
            break
    h = min(max(h, min_h), (area.h - GAP * (rows - 1)) / rows)
    y = balanced(area, rows * h + GAP * (rows - 1)) if centre else area.top
    for i, (big, runs) in enumerate(stats):
        r, c = divmod(i, cols)
        x = area.x + c * (width + gutter)
        top = y - r * (h + GAP)
        warm = warm_last and i == len(stats) - 1
        card(page, x, top - h, width, h, bar=True, warm=warm)
        size = fit_size(big, BLACK, width - 2 * pad, big_size, 14)
        page.add(Line(x + pad, top - 22 - size * 0.8, [Span(big, BLACK, size, pal().warm_figure if warm else pal().figure)]))
        text_block(page, x + pad, top - 22 - big_size * 1.25 - 4, width - 2 * pad, runs, caption, leading=1.34)
    return y - rows * (h + GAP) + GAP


def stat_rows(page: Page, stats: list[tuple[str, Runs]], area: Area, *, gap: float = 12) -> float:
    """Stacked cards with the figure on the left and its caption beside it. Returns the y below."""
    figure_w = min(150, area.w * 0.36)
    pad = 20
    text_w = area.w - figure_w - 2 * pad - 12
    size = BODY_SIZES[-1]
    for size in BODY_SIZES:
        heights = [max(block_height(runs, size, text_w, 1.34), 26) + 2 * 16 for _, runs in stats]
        if sum(heights) + gap * (len(stats) - 1) <= area.h:
            break
    y = area.top
    for (big, runs), h in zip(stats, heights, strict=True):
        card(page, area.x, y - h, area.w, h, side=True)
        big_size = fit_size(big, BLACK, figure_w - 8, 24, 13)
        page.add(Line(area.x + pad + 4, y - h / 2 - big_size * 0.35, [Span(big, BLACK, big_size, pal().figure)]))
        text_h = block_height(runs, size, text_w, 1.34)
        text_block(page, area.x + pad + figure_w + 12, y - (h - text_h) / 2, text_w, runs, size, leading=1.34)
        y -= h + gap
    return y + gap


def table(page: Page, rows: list[list[str]], x: float, top: float, w: float, size: float) -> float:
    """A header row in jade and banded body rows. Returns the y below."""
    cols = len(rows[0])
    if cols == 2:
        first = 0.3 if max(len(r[1]) for r in rows) > 30 else 0.45
        widths = [w * first, w * (1 - first)]
    else:
        widths = [w / cols] * cols
    y = top
    for i, row in enumerate(rows):
        font = SEMIBOLD if i == 0 else REGULAR
        cells = [wrap([(cell, font)], size, cw - 16) for cell, cw in zip(row, widths, strict=True)]
        h = max(len(lines) for lines in cells) * size * 1.32 + 12
        # Every cell is outlined: ruled cells are what lets OCR recognise this as a table rather than prose.
        cx = x
        for cw in widths:
            page.add(Fill(cx, y - h, cw, h, pal().header if i == 0 else pal().card_alt if i % 2 == 0 else pal().card,
                          stroke=pal().line,
                          stroke_width=0.8))
            cx += cw
        cx = x
        for lines, cw in zip(cells, widths, strict=True):
            ty = y - 6 - size * 0.8
            for segments in lines:
                page.add(Line(cx + 8, ty, [Span(t, f, size, pal().on_primary if i == 0 else pal().ink_2) for t, f in segments]))
                ty -= size * 1.32
            cx += cw
        y -= h
    return y


def table_height(rows: list[list[str]], w: float, size: float) -> float:
    cols = len(rows[0])
    widths = [w * (0.3 if max(len(r[1]) for r in rows) > 30 else 0.45), 0] if cols == 2 else [w / cols] * cols
    if cols == 2:
        widths[1] = w - widths[0]
    total = 0.0
    for i, row in enumerate(rows):
        font = SEMIBOLD if i == 0 else REGULAR
        total += max(len(wrap([(cell, font)], size, cw - 16)) for cell, cw in zip(row, widths, strict=True)) * size * 1.32 + 12
    return total


# ── slide compositions ──────────────────────────────────────────────────────────────────────────────────

def aura(page: Page, cx: float, cy: float, r: float) -> None:
    """The cover's mark: AURA3's aura as nested discs round a jade core, with a marigold point in orbit. Flat
    discs on purpose: thick curved strokes make OCR flag the page as handwriting, and a picture makes it scan
    the page for text."""
    soft = pal().soft
    page.add(Disc(cx, cy, r, soft[0]), Disc(cx, cy, r * 0.78, soft[1]), Disc(cx, cy, r * 0.56, soft[2]),
             Disc(cx, cy, r * 0.34, pal().primary, gradient=pal().gradient),
             Disc(cx + r * 0.52, cy + r * 0.52, r * 0.12, pal().warm[0], gradient=pal().warm))


def bar_chart(page: Page, chart: dict, x: float, y: float, w: float, h: float) -> None:
    """Bars as shapes with their values and labels as text, so OCR reads the numbers exactly (a chart picture
    gets scanned and flagged for review). The latest bar is marigold."""
    values = chart["values"]
    top = max(values) or 1
    slot = w / len(values)
    bar_w = min(slot * 0.56, 64)
    room = h - 40  # value labels above, year labels below
    base = y + 20
    page.add(Fill(x, base, w, 0.8, pal().line))
    for i, (label, value) in enumerate(zip(chart["labels"], values, strict=True)):
        cx = x + slot * (i + 0.5)
        bar_h = max(2.0, room * value / top)
        colours = pal().warm if i == len(values) - 1 else pal().gradient
        page.add(Fill(cx - bar_w / 2, base, bar_w, bar_h, colours[0], radius=4, gradient=colours[::-1], vertical=True),
                 Line(cx, base + bar_h + 6, [Span(f"{value:g}", SEMIBOLD, 10.5, pal().figure)], align="center"),
                 Line(cx, base - 13, [Span(str(label), REGULAR, 9, pal().ink_3)], align="center"))


def cover(page: Page, spec: Brand, slide: Slide) -> None:
    column = 430
    tag = "  ·  ".join(t for t in (f"{STAGE_LABELS[spec.stage]} round", spec.domain, spec.city) if t).upper()
    size = fit_size(slide.title, BLACK, column, 54, 30)
    sub = [(slide.subtitle, LIGHT)] if slide.subtitle else []
    first, rest = (slide.bullets[0], slide.bullets[1:]) if slide.bullets else ("", [])
    inner = column - 52
    card_h = 24 + block_height([(first, BOLD)], 15, inner, 1.3) + 6 + sum(
        block_height(labelled(b), 11.5, inner, 1.45) for b in rest) + 20
    total = 26 + 30 + size * 1.05 + 14 + (block_height(sub, 16, column, 1.32) if sub else 0) + 28 + card_h
    top = (H + total) / 2 + 6

    width = measure(tag, SEMIBOLD, 9, 1.6) + 32
    page.add(Fill(M, top - 26, width, 26, pal().primary, radius=13, gradient=pal().gradient),
             Line(M + 16, top - 17, [Span(tag, SEMIBOLD, 9, pal().on_primary)], tracking=1.6))
    top -= 26 + 30
    page.add(Line(M, top - size * 0.8, [Span(slide.title, BLACK, size, pal().ink)]))
    top -= size * 1.05 + 14
    if sub:
        top = text_block(page, M, top, column, sub, 16, colour=pal().ink_2, strong=pal().ink_2, leading=1.32)
    top -= 28
    card(page, M, top - card_h, column, card_h, side=True)
    y = text_block(page, M + 28, top - 24, inner, [(first, BOLD)], 15, leading=1.3) - 6
    for bullet in rest:
        y = text_block(page, M + 28, y, inner, labelled(bullet), 11.5, leading=1.45)
    aura(page, W - M - 155 + 18, H / 2 - 4, 155)


def market(page: Page, slide: Slide, top: float) -> None:
    ring = min(top - BOTTOM - 10, 260)
    left = W - 2 * M - ring - 56
    items = [labelled(b) for b in slide.bullets]
    stack(page, items, Area(M, top, left, top - BOTTOM), min_h=56)
    x = W - M - ring
    bottom = top - ring - (top - BOTTOM - ring) / 2
    page.add(Picture(x, bottom, ring, ring, art.market_rings(pal().soft, pal().soft_warm)))
    # The rings carry no labels: OCR would read them into the cards' sentences. Each card names its ring.


def traction(page: Page, slide: Slide, top: float) -> None:
    right = 300 if slide.chart else 0
    left_w = W - 2 * M - (right + 24 if right else 0)
    with_figures: list[int] = []
    for i, b in enumerate(slide.bullets):  # up to three tiles, each a different figure
        if (f := figure(b)) and f not in {figure(slide.bullets[j]) for j in with_figures} and len(with_figures) < 3:
            with_figures.append(i)
    stats = [(figure(slide.bullets[i]) or "", labelled(slide.bullets[i])) for i in with_figures]
    rest = [labelled(b) for i, b in enumerate(slide.bullets) if i not in with_figures]
    y = top
    if stats:
        y = stat_rows(page, stats, Area(M, top, left_w, (top - BOTTOM) * (0.66 if rest else 1))) - 12
    if rest:
        y = stack(page, rest, Area(M, y, left_w, y - BOTTOM), min_h=48, centre=False, gap=12) - GAP
    if slide.chart:
        chart_card(page, slide.chart, slide.table or [], W - M - right, top, right, top - BOTTOM)
    elif slide.table:
        table(page, slide.table, M, y, left_w, 10)


def chart_card(page: Page, chart: dict, rows: list[list[str]], x: float, top: float, w: float, h: float) -> None:
    """A card with the chart's title, its bars and (if given) the table of its numbers."""
    card(page, x, top - h, w, h, bar=True)
    page.add(Line(x + 18, top - 30, [Span(chart["title"], SEMIBOLD, 11, pal().ink)]))
    chart_h = min(w * 3.1 / 4.2, h - 60) - 18
    if rows:
        chart_h = min(chart_h, h - 70 - table_height(rows, w - 32, 9.5))
    bar_chart(page, chart, x + 22, top - 44 - chart_h, w - 44, chart_h)
    if rows:
        table(page, rows, x + 16, top - 46 - chart_h, w - 32, 9.5)


def _bottom(shape: Shape) -> float:
    if isinstance(shape, Disc):
        return shape.cy - shape.r
    if isinstance(shape, Line):
        return shape.y - max(sp.size for sp in shape.spans) * 0.3
    return shape.y


def _lower(shapes: list[Shape], dy: float) -> None:
    for shape in shapes:
        if isinstance(shape, Disc):
            shape.cy -= dy
        else:
            shape.y -= dy


def generic(page: Page, slide: Slide, top: float) -> None:
    """Any mix of stat tiles, a table, a chart and bullet cards (slides the copilot writes), drawn from the top
    and then lowered so the block sits a little above the middle of the body."""
    first = len(page.shapes)
    y = top
    items = [labelled(b) for b in slide.bullets]
    stats = [(value, [(label, REGULAR)]) for value, label in slide.stats[:4]]
    if stats and len(stats) <= 2 and items and not slide.table and not slide.chart:
        # One or two figures: a column of tiles beside the bullets, not tiles stretched across the slide
        side = (W - 2 * M) * 0.34
        below = stat_cards(page, stats, Area(M, y, side, min(len(stats) * 130, top - BOTTOM)), cols=1)
        stack(page, items, Area(M + side + 24, y, W - 2 * M - side - 24, top - BOTTOM), min_h=52, centre=False)
        y = min(below, y)
    else:
        if stats:
            y = stat_cards(page, stats, Area(M, y, W - 2 * M, min(118, (top - BOTTOM) * 0.36)), cols=len(stats)) - GAP
        right = 300 if slide.chart else 0
        left_w = W - 2 * M - (right + 24 if right else 0)
        if slide.chart:
            chart_card(page, slide.chart, [], W - M - right, y, right, min(y - BOTTOM, 300))
        if slide.table:
            room = (y - BOTTOM) * (0.6 if items else 1)
            size = next(s for s in (12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5)
                        if table_height(slide.table, left_w - 40, s) + 40 <= room or s == 8.5)
            h = table_height(slide.table, left_w - 40, size) + 40
            card(page, M, y - h, left_w, h)
            table(page, slide.table, M + 20, y - 20, left_w - 40, size)
            y -= h + GAP
        if items:
            stack(page, items, Area(M, y, left_w, y - BOTTOM), min_h=52, centre=False)
    drawn = page.shapes[first:]
    if drawn:
        free = min(_bottom(sh) for sh in drawn) - BOTTOM
        if free > 0:
            _lower(drawn, free * 0.38)


# What each composition can show besides bullets; anything else goes to ``generic``.
EXTRAS = {"market": set(), "traction": {"table", "chart"}, "unit_economics": set(), "competition": {"table"},
          "gtm": set(), "team": set(), "ask": set(), "problem": set(), "solution": set(), "business_model": set()}


def unit_economics(page: Page, slide: Slide, top: float) -> None:
    stats = [(f, labelled(b)) for b in slide.bullets if (f := figure(b))]
    rest = [labelled(b) for b in slide.bullets if not figure(b)]
    area_h = (top - BOTTOM) * (0.72 if rest else 1)
    cols = 3 if len(stats) > 4 or len(stats) == 3 else max(1, len(stats))
    rows = math.ceil(len(stats) / cols) if stats else 1
    y = stat_cards(page, stats, Area(M, top, W - 2 * M, area_h), cols=cols, warm_last=True,
                   min_h=(area_h - GAP * (rows - 1)) / rows * 0.8, centre=not rest) - GAP
    if rest:
        stack(page, rest, Area(M, y, W - 2 * M, y - BOTTOM), min_h=48, centre=False)


def competition(page: Page, slide: Slide, top: float) -> None:
    """The table across the page, our edges in cards under it (beside it, OCR reads them as a third column)."""
    edges = [labelled(b) for b in slide.bullets]
    w = W - 2 * M
    edge_h = sum(block_height(e, 12, w - 54, 1.36) + 30 for e in edges) + 12 * max(0, len(edges) - 1)
    room = top - BOTTOM - (edge_h + 22 if edges else 0)
    y = top
    if slide.table:
        size = next(s for s in (13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5)
                    if table_height(slide.table, w - 40, s) + 40 <= room or s == 8.5)
        h = table_height(slide.table, w - 40, size) + 40
        card(page, M, y - h, w, h)
        table(page, slide.table, M + 20, y - 20, w - 40, size)
        y -= h + 22
    if edges:
        stack(page, edges, Area(M, y, w, y - BOTTOM), centre=False, gap=12)


def gtm(page: Page, slide: Slide, top: float) -> None:
    """How we reach customers, then what could go wrong: two full-width cards, one above the other (side by
    side, OCR reads their aligned bullets as one table)."""
    plan = [b for b in slide.bullets if not b.startswith("Risk:")]
    risks = [b for b in slide.bullets if b.startswith("Risk:")]
    columns = [c for c in (("How we reach customers", plan, False), ("What could go wrong", risks, True)) if c[1]]
    pad, gap, head = 24, 14, 44
    width = W - 2 * M - 2 * pad
    size = BODY_SIZES[-1]
    for size in BODY_SIZES:
        heights = [head + sum(block_height(labelled(b), size, width) + 7 for b in items) + pad - 7
                   for _, items, _ in columns]
        if sum(heights) + gap * (len(columns) - 1) <= top - BOTTOM:
            break
    y = balanced(Area(M, top, W - 2 * M, top - BOTTOM), sum(heights) + gap * (len(columns) - 1))
    for (heading, items, warm), h in zip(columns, heights, strict=True):
        card(page, M, y - h, W - 2 * M, h, bar=True, warm=warm)
        page.add(Line(M + pad, y - 30, [Span(heading, BOLD, 14, pal().ink)]))
        ty = y - head
        for bullet in items:  # no bullet dots: once a deck is scanned, OCR tries to read them
            ty = text_block(page, M + pad, ty, width, labelled(bullet), size) - 7
        y -= h + gap


def team(page: Page, slide: Slide, top: float) -> None:
    items = [labelled(b) for b in slide.bullets]
    stack(page, items, Area(M, top, W - 2 * M, top - BOTTOM), min_h=58)


def ask(page: Page, spec: Brand, slide: Slide, top: float) -> None:
    crore = lambda rupees: f"{rupees / 1e7:g}"  # noqa: E731
    stats = [
        (f"Rs {crore(spec.ask_inr or 0)} crore", [(f"{STAGE_LABELS[spec.stage]} round", REGULAR)]),
        (f"Rs {crore(spec.pre_money_inr or 0)} crore", [("Pre-money valuation", REGULAR)]),
        (f"{spec.min_raise_pct}%", [("Minimum raise to close", REGULAR)]),
    ]
    y = stat_cards(page, stats, Area(M, top, W - 2 * M, 104), cols=3, warm_last=True) - GAP
    tranches = [b for b in slide.bullets if b.startswith("Tranche")]
    terms = [labelled(b) for b in slide.bullets if not b.startswith("Tranche")]
    left = (W - 2 * M - GAP) * 0.5 if tranches else W - 2 * M
    stack(page, terms, Area(M, y, left, y - BOTTOM), min_h=52, centre=False)
    if tranches:
        x = M + left + GAP
        w = W - M - x
        h = y - BOTTOM
        card(page, x, y - h, w, h, bar=True)
        page.add(Line(x + 22, y - 32, [Span("Released in tranches, on milestones", BOLD, 13, pal().ink)]))
        size = next(s for s in (11, 10.5, 10, 9.5, 9, 8.5)
                    if sum(block_height(labelled(t), s, w - 70) + 14 for t in tranches) <= h - 66 or s == 8.5)
        ty = y - 52
        nodes = []
        for text in tranches:
            nodes.append(ty)
            ty = text_block(page, x + 50, ty + size * 0.15, w - 70, labelled(text), size) - 14
        page.add(Fill(x + 29, nodes[-1] - 5, 2.4, nodes[0] - nodes[-1], pal().gradient[0], gradient=pal().gradient[::-1],
                      vertical=True))
        for i, ny in enumerate(nodes):
            colours = pal().warm if i == len(nodes) - 1 else pal().gradient
            page.add(Disc(x + 30.2, ny - 5, 7.5, pal().card), Disc(x + 30.2, ny - 5, 5.5, colours[0], gradient=colours))


def lay_out(spec: Brand, slide: Slide, number: int, total: int, palette: Palette = AURA) -> Page:
    """One slide as shapes, in ``palette``'s colours."""
    token = _PALETTE.set(palette)
    try:
        return _lay_out(spec, slide, number, total, palette)
    finally:
        _PALETTE.reset(token)


def _lay_out(spec: Brand, slide: Slide, number: int, total: int, palette: Palette) -> Page:
    page = Page(notes=slide.notes, palette=palette)
    logo(page, spec)
    footer(page, spec, number, total)
    extras = {kind for kind, present in (("table", slide.table), ("chart", slide.chart)) if present}
    if slide.key == "title":
        cover(page, spec, slide)
    else:
        top = header(page, slide, number)
        body = Area(M, top, W - 2 * M, top - BOTTOM)
        if (slide.stats or slide.key not in EXTRAS or extras - EXTRAS[slide.key]
                or (slide.key == "ask" and spec.ask_inr is None)):
            generic(page, slide, top)
        elif slide.key == "market":
            market(page, slide, top)
        elif slide.key == "traction":
            traction(page, slide, top)
        elif slide.key == "unit_economics":
            unit_economics(page, slide, top)
        elif slide.key == "competition":
            competition(page, slide, top)
        elif slide.key == "gtm":
            gtm(page, slide, top)
        elif slide.key == "team":
            team(page, slide, top)
        elif slide.key == "ask":
            ask(page, spec, slide, top)
        else:
            items = [labelled(b) for b in slide.bullets]
            stack(page, items, body, min_h=60 if len(items) <= 4 else 48)
    if slide.hidden:
        # Adversarial decks only: white text on the plain background between the cards' shadows and the footer,
        # where a reader cannot see it but text extraction (and so an evaluator) still reads it.
        y = 38.0
        for segments in wrap([(slide.hidden, REGULAR)], 7, W - 2 * M):
            page.hidden.append(Line(M, y, [Span(t, f, 7, WHITE) for t, f in segments]))
            y -= 8.5
    return page
