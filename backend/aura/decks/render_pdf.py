"""Slides → a landscape A4 PDF with a real text layer, drawn from ``design.lay_out``. The same spec always gives
the same bytes (reportlab ``invariant`` mode: no timestamps or random document ids)."""

import io

from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import FILL_NON_ZERO

from aura.decks.design import Brand, Disc, Fill, H, Line, Page, Picture, Shadow, W, lay_out
from aura.decks.slides import Slide, build_slides
from aura.decks.spec import StartupSpec
from aura.decks.theme import JADE_900, PAPER, RGB, WASH, register_fonts, unit


def _colour(rgb: RGB) -> Color:
    return Color(*unit(rgb))


def _gradient_clip(c: canvas.Canvas, path, x0: float, y0: float, x1: float, y1: float, stops: list[RGB]) -> None:
    c.saveState()
    c.clipPath(path, stroke=0, fill=0, fillMode=FILL_NON_ZERO)  # overlapping parts (an arc and its round end) add up
    c.linearGradient(x0, y0, x1, y1, [_colour(s) for s in stops], extend=False)
    c.restoreState()


def _background(c: canvas.Canvas) -> None:
    # A solid sheet first: the hidden-text check compares text with the fills behind it.
    c.setFillColorRGB(*unit(PAPER))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    path = c.beginPath()
    path.rect(0, 0, W, H)
    _gradient_clip(c, path, 0, H, W, 0, WASH)


def _fill(c: canvas.Canvas, s: Fill) -> None:
    def outline():
        path = c.beginPath()
        if s.radius:
            path.roundRect(s.x, s.y, s.w, s.h, min(s.radius, s.w / 2, s.h / 2))
        else:
            path.rect(s.x, s.y, s.w, s.h)
        return path

    if s.colour is not None:
        c.setFillColorRGB(*unit(s.colour))
        c.drawPath(outline(), fill=1, stroke=0)
    if s.gradient:
        end = (s.x, s.y + s.h) if s.vertical else (s.x + s.w, s.y)
        _gradient_clip(c, outline(), s.x, s.y, *end, s.gradient)
    if s.stroke is not None:
        c.setStrokeColorRGB(*unit(s.stroke))
        c.setLineWidth(s.stroke_width)
        c.drawPath(outline(), fill=0, stroke=1)


def _disc(c: canvas.Canvas, s: Disc) -> None:
    c.setFillColorRGB(*unit(s.colour))
    c.circle(s.cx, s.cy, s.r, fill=1, stroke=0)
    if s.gradient:
        path = c.beginPath()
        path.circle(s.cx, s.cy, s.r)
        _gradient_clip(c, path, s.cx - s.r, s.cy + s.r, s.cx + s.r, s.cy - s.r, s.gradient)


def _shadow(c: canvas.Canvas, s: Shadow) -> None:
    c.saveState()
    c.setFillColorRGB(*unit(JADE_900))
    for i, alpha in enumerate((0.018, 0.016, 0.014, 0.012, 0.01)):
        spread, drop = 0.8 + i * 1.3, 1.2 + i * 1.2  # reaches at most ~11pt below a card
        c.setFillAlpha(alpha)
        c.roundRect(s.x - spread, s.y - drop - spread, s.w + 2 * spread, s.h + 2 * spread, s.radius + spread, fill=1, stroke=0)
    c.restoreState()


def _line(c: canvas.Canvas, s: Line) -> None:
    x = s.x - (s.width if s.align == "right" else s.width / 2 if s.align == "center" else 0)
    text = c.beginText(x, s.y)
    text.setCharSpace(s.tracking)
    for span in s.spans:
        text.setFont(span.font, span.size)
        text.setFillColorRGB(*unit(span.colour))
        text.textOut(span.text)
    c.drawText(text)


def _picture(c: canvas.Canvas, s: Picture) -> None:
    c.drawImage(ImageReader(io.BytesIO(s.png)), s.x, s.y, s.w, s.h, mask="auto")


def draw_page(c: canvas.Canvas, page: Page) -> None:
    _background(c)
    for shape in page.shapes:
        if isinstance(shape, Fill):
            _fill(c, shape)
        elif isinstance(shape, Disc):
            _disc(c, shape)
        elif isinstance(shape, Shadow):
            _shadow(c, shape)
        elif isinstance(shape, Line):
            _line(c, shape)
        elif isinstance(shape, Picture):
            _picture(c, shape)
    for line in page.hidden:
        _line(c, line)


def render_slides_pdf(brand: Brand, slides: list[Slide]) -> bytes:
    register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H), invariant=1, pageCompression=1)
    c.setTitle(f"{brand.name} — pitch deck")
    c.setAuthor(brand.legal_name)
    c.setCreator("AURA-3 deck builder")
    c.setProducer("AURA-3 deck builder")
    for number, slide in enumerate(slides, start=1):
        draw_page(c, lay_out(brand, slide, number, len(slides)))
        c.showPage()
    c.save()
    return buf.getvalue()


def render_pdf(spec: StartupSpec, slides: list[Slide] | None = None) -> bytes:
    return render_slides_pdf(Brand.from_spec(spec), slides or build_slides(spec))
