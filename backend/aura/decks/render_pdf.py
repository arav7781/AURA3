"""Slides → a landscape A4 PDF with a real text layer. The same spec always gives the same bytes
(reportlab ``invariant`` mode: no timestamps or random document ids)."""

import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from aura.decks.charts import bar_chart
from aura.decks.palettes import Palette, palette, unit
from aura.decks.slides import Slide, build_slides
from aura.decks.spec import StartupSpec

WIDTH, HEIGHT = landscape(A4)
MARGIN = 57
BAND = 91
TOP = HEIGHT - BAND - 34
BOTTOM = 52
CHART_W, CHART_H = 290, 214
BODY, BOLD, ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if not line or stringWidth(trial, font, size) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


@dataclass
class Layout:
    size: float
    width: float  # text column width

    @property
    def leading(self) -> float:
        return self.size * 1.42


def _column_widths(table: list[list[str]], width: float) -> list[float]:
    if len(table[0]) == 2:
        first = 0.28 if max(len(row[1]) for row in table) > 30 else 0.45
        return [width * first, width * (1 - first)]
    return [width / len(table[0])] * len(table[0])


def _table_height(table: list[list[str]], layout: Layout) -> float:
    size = layout.size - 1
    widths = _column_widths(table, layout.width)
    total = 0.0
    for row in table:
        lines = max(len(wrap(cell, BOLD if row is table[0] else BODY, size, w - 12)) for cell, w in zip(row, widths, strict=True))
        total += lines * size * 1.35 + 10
    return total + 10


def _height(slide: Slide, layout: Layout) -> float:
    total = 0.0
    if slide.subtitle:
        total += len(wrap(slide.subtitle, ITALIC, layout.size + 2, layout.width)) * (layout.size + 2) * 1.4 + 10
    for bullet in slide.bullets:
        total += len(wrap(bullet, BODY, layout.size, layout.width - 22)) * layout.leading + layout.size * 0.5
    if slide.table:
        total += _table_height(slide.table, layout)
    return total


def fit(slide: Slide) -> Layout:
    width = WIDTH - 2 * MARGIN - (CHART_W + 24 if slide.chart else 0)
    for size in (19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8):
        layout = Layout(size, width)
        if _height(slide, layout) <= TOP - BOTTOM:
            return layout
    return Layout(8, width)


def _draw_table(c: canvas.Canvas, table: list[list[str]], x: float, y: float, layout: Layout, colours: Palette) -> float:
    size = layout.size - 1
    widths = _column_widths(table, layout.width)
    for r, row in enumerate(table):
        font = BOLD if r == 0 else BODY
        cells = [wrap(cell, font, size, w - 12) for cell, w in zip(row, widths, strict=True)]
        height = max(len(lines) for lines in cells) * size * 1.35 + 10
        fill = colours.primary if r == 0 else ((255, 255, 255) if r % 2 else colours.light)
        c.setFillColorRGB(*unit(fill))
        c.setStrokeColorRGB(*unit(colours.primary))
        c.setLineWidth(0.4)
        c.rect(x, y - height, layout.width, height, fill=1, stroke=1)
        cx = x
        for lines, w in zip(cells, widths, strict=True):
            c.setFillColorRGB(*((1, 1, 1) if r == 0 else unit(colours.dark)))
            c.setFont(font, size)
            ty = y - size - 4
            for line in lines:
                c.drawString(cx + 6, ty, line)
                ty -= size * 1.35
            cx += w
        y -= height
    return y


def draw_slide(c: canvas.Canvas, slide: Slide, number: int, total: int, spec: StartupSpec, colours: Palette,
               charts: dict[int, bytes]) -> None:
    c.setFillColorRGB(*unit(colours.light))
    c.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
    c.setFillColorRGB(*unit(colours.primary))
    c.rect(0, HEIGHT - BAND, WIDTH, BAND, fill=1, stroke=0)

    title_size = 26
    while stringWidth(slide.title, BOLD, title_size) > WIDTH - 2 * MARGIN and title_size > 16:
        title_size -= 1
    c.setFillColorRGB(1, 1, 1)
    c.setFont(BOLD, title_size)
    c.drawString(MARGIN, HEIGHT - 59, slide.title)

    layout = fit(slide)
    y = TOP
    if slide.subtitle:
        c.setFillColorRGB(*unit(colours.dark))
        c.setFont(ITALIC, layout.size + 2)
        for line in wrap(slide.subtitle, ITALIC, layout.size + 2, layout.width):
            c.drawString(MARGIN, y, line)
            y -= (layout.size + 2) * 1.4
        y -= 10
    for bullet in slide.bullets:
        c.setFillColorRGB(*unit(colours.accent))
        c.circle(MARGIN + 7, y + layout.size * 0.32, layout.size * 0.24, fill=1, stroke=0)
        c.setFillColorRGB(*unit(colours.dark))
        c.setFont(BODY, layout.size)
        for line in wrap(bullet, BODY, layout.size, layout.width - 22):
            c.drawString(MARGIN + 22, y, line)
            y -= layout.leading
        y -= layout.size * 0.5
    if slide.table:
        y = _draw_table(c, slide.table, MARGIN, y + layout.size * 0.6, layout, colours) - layout.size
    if slide.chart:
        image = ImageReader(io.BytesIO(charts[number]))
        c.drawImage(image, WIDTH - MARGIN - CHART_W, TOP - CHART_H + 14, CHART_W, CHART_H)
    if slide.hidden:
        # Adversarial decks only: white text on the near-white background, under the body text where a
        # reader cannot see it but text extraction (and so the evaluator) still reads it.
        c.setFillColorRGB(1, 1, 1)
        c.setFont(BODY, 8)
        for line in wrap(slide.hidden, BODY, 8, layout.width):
            y = max(y - 10, BOTTOM)
            c.drawString(MARGIN, y, line)

    c.setFillColorRGB(*unit(colours.primary))
    c.setFont(BODY, 9)
    c.drawString(MARGIN, 28, f"{spec.legal_name}  ·  CIN {spec.mca.cin}")
    c.drawRightString(WIDTH - MARGIN, 28, f"{number} / {total}")


def render_pdf(spec: StartupSpec, slides: list[Slide] | None = None) -> bytes:
    slides = slides or build_slides(spec)
    colours = palette(spec.deck.palette)
    charts = {i: bar_chart(s.chart, colours) for i, s in enumerate(slides, start=1) if s.chart}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(WIDTH, HEIGHT), invariant=1, pageCompression=1)
    c.setTitle(f"{spec.name} — pitch deck")
    c.setAuthor(spec.legal_name)
    c.setCreator("AURA-3 deck builder")
    c.setProducer("AURA-3 deck builder")
    for number, slide in enumerate(slides, start=1):
        draw_slide(c, slide, number, len(slides), spec, colours, charts)
        c.showPage()
    c.save()
    return buf.getvalue()
