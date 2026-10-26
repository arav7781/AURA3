"""Slides → a 16:9 PowerPoint deck with the same content as the PDF. Output is byte-stable: core
properties carry a fixed date and every zip entry a fixed timestamp."""

import io
import zipfile
from datetime import datetime

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Emu, Inches, Pt

from aura.decks.charts import bar_chart
from aura.decks.palettes import palette
from aura.decks.render_pdf import fit
from aura.decks.slides import Slide, build_slides
from aura.decks.spec import StartupSpec

FIXED_DATE = datetime(2026, 1, 1)


def _rgb(colour: tuple[int, int, int]) -> RGBColor:
    return RGBColor(*colour)


def _paragraph(frame, text: str, *, size: float, colour, first: bool, italic: bool = False, bold: bool = False):
    p = frame.paragraphs[0] if first else frame.add_paragraph()
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = colour
    p.font.italic = italic
    p.font.bold = bold
    p.space_after = Pt(size * 0.45)
    return p


def _stable_zip(data: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for entry in source.infolist():  # keeps [Content_Types].xml first
            fixed = zipfile.ZipInfo(entry.filename, date_time=(1980, 1, 1, 0, 0, 0))
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = 0o644 << 16
            target.writestr(fixed, source.read(entry.filename))
    return out.getvalue()


def render_pptx(spec: StartupSpec, slides: list[Slide] | None = None) -> bytes:
    slides = slides or build_slides(spec)
    colours = palette(spec.deck.palette)
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)
    width = deck.slide_width
    blank = deck.slide_layouts[6]
    dark, white = _rgb(colours.dark), RGBColor(255, 255, 255)

    for number, slide in enumerate(slides, start=1):
        page = deck.slides.add_slide(blank)
        page.background.fill.solid()
        page.background.fill.fore_color.rgb = _rgb(colours.light)

        band = page.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, width, Inches(1.25))
        band.fill.solid()
        band.fill.fore_color.rgb = _rgb(colours.primary)
        band.line.fill.background()
        band.text_frame.margin_left = Inches(0.6)
        _paragraph(band.text_frame, slide.title, size=30, colour=white, first=True, bold=True)

        size = fit(slide).size + 2  # PowerPoint renders a little smaller than the PDF at the same size
        body_width = Inches(7.4) if slide.chart else Inches(12.1)
        body = page.shapes.add_textbox(Inches(0.6), Inches(1.55), body_width, Inches(3.4 if slide.table else 5.3))
        frame = body.text_frame
        frame.word_wrap = True
        first = True
        if slide.subtitle:
            _paragraph(frame, slide.subtitle, size=size + 2, colour=dark, first=True, italic=True)
            first = False
        for bullet in slide.bullets:
            _paragraph(frame, f"•  {bullet}", size=size, colour=dark, first=first)
            first = False

        if slide.table:
            rows, cols = len(slide.table), len(slide.table[0])
            shape = page.shapes.add_table(rows, cols, Inches(0.6), Inches(5.0) if slide.bullets else Inches(1.6),
                                          body_width, Inches(0.36) * rows)
            table = shape.table
            table.columns[0].width = Emu(int(body_width * (0.3 if cols == 2 else 1 / cols)))
            if cols == 2:
                table.columns[1].width = Emu(int(body_width - table.columns[0].width))
            for r, row in enumerate(slide.table):
                for c, value in enumerate(row):
                    cell = table.cell(r, c)
                    cell.text = value
                    font = cell.text_frame.paragraphs[0].font
                    font.size = Pt(size - 2)
                    font.bold = r == 0
                    font.color.rgb = white if r == 0 else dark
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = _rgb(colours.primary) if r == 0 else (
                        RGBColor(255, 255, 255) if r % 2 else _rgb(colours.light))

        if slide.chart:
            png = bar_chart(slide.chart, colours)
            page.shapes.add_picture(io.BytesIO(png), Inches(8.3), Inches(1.55), width=Inches(4.4))

        if slide.hidden:  # adversarial decks: white text a reader cannot see, plus the same in the notes
            hidden = page.shapes.add_textbox(Inches(0.6), Inches(6.45), Inches(12.1), Inches(0.3))
            hidden.text_frame.word_wrap = True
            _paragraph(hidden.text_frame, slide.hidden, size=8, colour=white, first=True)
        if slide.notes:
            page.notes_slide.notes_text_frame.text = slide.notes

        footer = page.shapes.add_textbox(Inches(0.6), Inches(6.95), Inches(12.1), Inches(0.35))
        _paragraph(footer.text_frame, f"{spec.legal_name}  ·  CIN {spec.mca.cin}  ·  {number} / {len(slides)}",
                   size=9, colour=_rgb(colours.primary), first=True)

    props = deck.core_properties
    props.title = f"{spec.name} — pitch deck"
    props.author = props.last_modified_by = spec.legal_name
    props.created = props.modified = FIXED_DATE
    props.revision = 1
    buf = io.BytesIO()
    deck.save(buf)
    return _stable_zip(buf.getvalue())
