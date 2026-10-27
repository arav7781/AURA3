"""AURA3's deck theme: the platform's own palette and type, so every seeded pitch deck looks like it belongs to
the product. Colours are (r, g, b) 0-255; fonts are Geist (SIL OFL, vendored in ``fonts/``).

The slide background stays near white (luminance > 0.9) so hidden-text checks behave like real decks: white
text on it is invisible, white text on a jade badge is not. Every shape that carries white text has a solid
jade fill under its gradient for the same reason.
"""

import re
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

RGB = tuple[int, int, int]

INK: RGB = (0x0F, 0x1A, 0x16)
INK_2: RGB = (0x3C, 0x4A, 0x44)
INK_3: RGB = (0x66, 0x75, 0x6E)
PAPER: RGB = (0xFB, 0xFA, 0xF6)
LINE: RGB = (0xE2, 0xDD, 0xD0)
WHITE: RGB = (0xFF, 0xFF, 0xFF)
JADE_50: RGB = (0xEC, 0xF7, 0xF2)
JADE_100: RGB = (0xD4, 0xEE, 0xE3)
JADE_200: RGB = (0xA8, 0xDC, 0xC6)
JADE_400: RGB = (0x3F, 0xAE, 0x84)
JADE_500: RGB = (0x1F, 0x96, 0x70)
JADE_600: RGB = (0x15, 0x7B, 0x5B)
JADE_700: RGB = (0x11, 0x62, 0x48)
JADE_900: RGB = (0x0A, 0x35, 0x28)
MARIGOLD_50: RGB = (0xFD, 0xF6, 0xE8)
MARIGOLD_100: RGB = (0xFB, 0xE8, 0xC3)
MARIGOLD_300: RGB = (0xF3, 0xC2, 0x6B)
MARIGOLD_400: RGB = (0xEE, 0xAA, 0x3E)
MARIGOLD_500: RGB = (0xDB, 0x8E, 0x1D)

# The signature gradient (evergreen → jade), its warm counterpart for highlights, and the wash behind slides.
# Jade and marigold are never blended into one gradient: the midpoint is a muddy olive.
GRADIENT: list[RGB] = [JADE_700, JADE_500, JADE_400]
WARM: list[RGB] = [MARIGOLD_400, MARIGOLD_500]
WASH: list[RGB] = [(0xE2, 0xF2, 0xEA), PAPER, (0xFC, 0xEE, 0xD6)]

FONT_DIR = Path(__file__).parent / "fonts"
LIGHT, REGULAR, MEDIUM, SEMIBOLD, BOLD, BLACK = (
    "Geist-Light", "Geist-Regular", "Geist-Medium", "Geist-SemiBold", "Geist-Bold", "Geist-Black")
MONO = "GeistMono-Medium"
FONTS = (LIGHT, REGULAR, MEDIUM, SEMIBOLD, BOLD, BLACK, MONO)
# How PowerPoint names each face: (family, bold)
PPTX_FONTS: dict[str, tuple[str, bool]] = {
    LIGHT: ("Geist Light", False), REGULAR: ("Geist", False), MEDIUM: ("Geist Medium", False),
    SEMIBOLD: ("Geist SemiBold", False), BOLD: ("Geist", True), BLACK: ("Geist Black", False),
    MONO: ("Geist Mono Medium", False),
}


@cache
def register_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name in FONTS:
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))


def unit(rgb: RGB) -> tuple[float, float, float]:
    return rgb[0] / 255, rgb[1] / 255, rgb[2] / 255


def hex_colour(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ── palettes: every colour a slide uses, by role ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Palette:
    """A deck design's colours by role. ``aura`` is AURA3's own; the others are alternatives a founder can
    choose, and ``with_brand`` derives one from a brand colour."""
    name: str
    label: str
    base: RGB  # the slide behind everything (solid, under the wash)
    wash: list[RGB]  # the background gradient, top left to bottom right
    ink: RGB  # titles, bold labels
    ink_2: RGB  # body text
    ink_3: RGB  # footers, captions
    card: RGB
    card_alt: RGB  # banded table rows
    card_edge: RGB
    line: RGB  # rules and table borders
    primary: RGB  # section labels, logo, side bars
    figure: RGB  # big numbers, chart values
    header: RGB  # table header fill
    on_primary: RGB  # text on primary fills
    gradient: list[RGB]
    warm: list[RGB]  # the accent gradient (last bar, last tile, orbit dot)
    warm_figure: RGB
    soft: tuple[RGB, RGB, RGB]  # pale tints: aura discs, market rings
    soft_warm: tuple[RGB, RGB]  # pale accent tint and its edge (innermost ring)
    shadow: RGB


def _hex(value: str) -> RGB:
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(f"not a hex colour: #{value}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    """``a`` moved a fraction ``t`` towards ``b``."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def luminance(rgb: RGB) -> float:
    def channel(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


AURA = Palette(
    "aura", "AURA3", PAPER, WASH, INK, INK_2, INK_3, WHITE, PAPER, (0xEA, 0xE6, 0xDC), LINE, JADE_600, JADE_700,
    JADE_700, WHITE, GRADIENT, WARM, MARIGOLD_500, (JADE_50, JADE_100, JADE_200), (MARIGOLD_100, MARIGOLD_300),
    JADE_900)
AURA_DARK = Palette(
    "aura_dark", "Evergreen night", (0x0A, 0x17, 0x12), [(0x10, 0x26, 0x1D), (0x0A, 0x17, 0x12), (0x17, 0x15, 0x0C)],
    (0xEE, 0xF5, 0xF1), (0xB9, 0xCB, 0xC2), (0x86, 0x9F, 0x94), (0x11, 0x26, 0x1E), (0x0D, 0x1F, 0x18),
    (0x1F, 0x3D, 0x31), (0x25, 0x45, 0x3A), JADE_400, (0x73, 0xC4, 0xA3), JADE_600, WHITE,
    [JADE_600, JADE_500, JADE_400], WARM, MARIGOLD_300, ((0x10, 0x2A, 0x20), (0x14, 0x37, 0x2A), (0x1B, 0x48, 0x37)),
    ((0x3A, 0x2C, 0x12), (0x8D, 0x5A, 0x0F)), (0x00, 0x00, 0x00))
OCEAN = Palette(
    "ocean", "Ocean", (0xF7, 0xFA, 0xFC), [(0xE3, 0xEE, 0xFB), (0xF7, 0xFA, 0xFC), (0xE4, 0xF5, 0xF7)],
    (0x0F, 0x17, 0x2A), (0x33, 0x41, 0x55), (0x64, 0x74, 0x8B), WHITE, (0xF1, 0xF5, 0xF9), (0xE3, 0xE9, 0xF1),
    (0xE2, 0xE8, 0xF0), (0x1D, 0x4E, 0xD8), (0x1E, 0x3A, 0x8A), (0x1E, 0x40, 0xAF), WHITE,
    [(0x1E, 0x3A, 0x8A), (0x25, 0x63, 0xEB), (0x0E, 0xA5, 0xE9)], [(0xF5, 0x9E, 0x0B), (0xD9, 0x77, 0x06)],
    (0xB4, 0x53, 0x09), ((0xE8, 0xF0, 0xFE), (0xD6, 0xE4, 0xFD), (0xB9, 0xCF, 0xFB)),
    ((0xFD, 0xF0, 0xD5), (0xF8, 0xC7, 0x6B)), (0x0B, 0x1D, 0x3A))
VIBRANT = Palette(
    "vibrant", "Vibrant", (0xFB, 0xF9, 0xFF), [(0xEF, 0xE7, 0xFF), (0xFB, 0xF9, 0xFF), (0xFF, 0xEE, 0xE4)],
    (0x17, 0x11, 0x2B), (0x46, 0x3E, 0x5C), (0x77, 0x6F, 0x8C), WHITE, (0xF6, 0xF3, 0xFB), (0xEB, 0xE5, 0xF5),
    (0xE7, 0xE1, 0xF2), (0x7C, 0x3A, 0xED), (0x6D, 0x28, 0xD9), (0x5B, 0x21, 0xB6), WHITE,
    [(0x7C, 0x3A, 0xED), (0xDB, 0x27, 0x77), (0xF9, 0x73, 0x16)], [(0xF9, 0x73, 0x16), (0xEA, 0x58, 0x0C)],
    (0xEA, 0x58, 0x0C), ((0xF1, 0xEA, 0xFF), (0xE4, 0xD6, 0xFF), (0xCD, 0xB4, 0xFE)),
    ((0xFF, 0xE9, 0xDC), (0xFD, 0xBA, 0x8C)), (0x2E, 0x10, 0x65))
GRAPHITE = Palette(
    "graphite", "Graphite", (0xFA, 0xFA, 0xFA), [(0xF0, 0xF0, 0xF0), (0xFA, 0xFA, 0xFA), (0xF4, 0xF3, 0xF0)],
    (0x11, 0x11, 0x11), (0x3F, 0x3F, 0x46), (0x71, 0x71, 0x7A), WHITE, (0xF4, 0xF4, 0xF5), (0xE7, 0xE7, 0xEA),
    (0xE4, 0xE4, 0xE7), (0x18, 0x18, 0x1B), (0x18, 0x18, 0x1B), (0x18, 0x18, 0x1B), WHITE,
    [(0x18, 0x18, 0x1B), (0x3F, 0x3F, 0x46), (0x71, 0x71, 0x7A)], [(0xEF, 0x44, 0x44), (0xDC, 0x26, 0x26)],
    (0xDC, 0x26, 0x26), ((0xF4, 0xF4, 0xF5), (0xE4, 0xE4, 0xE7), (0xD4, 0xD4, 0xD8)),
    ((0xFE, 0xE2, 0xE2), (0xFC, 0xA5, 0xA5)), (0x00, 0x00, 0x00))
PALETTES: dict[str, Palette] = {p.name: p for p in (AURA, AURA_DARK, OCEAN, VIBRANT, GRAPHITE)}


def with_brand(base: Palette, colour: str, accent: str | None = None) -> Palette:
    """``base`` recoloured around a brand colour (and optionally an accent): its gradient, labels, figures,
    table headers and tints. Colours too light to read as text are darkened for text and figures."""
    brand = _hex(colour)
    dark = base.base[0] < 128
    readable = brand if (luminance(brand) < 0.35 or dark) else _mix(brand, (0, 0, 0), 0.35)
    figure = _mix(brand, (255, 255, 255), 0.35) if dark else _mix(readable, (0, 0, 0), 0.2)
    tint = (0, 0, 0) if dark else (255, 255, 255)
    soft = tuple(_mix(brand, tint, t) for t in ((0.9, 0.84, 0.72) if dark else (0.93, 0.86, 0.72)))
    changes: dict = dict(
        name=f"{base.name}+brand", label=f"{base.label}, brand colour", primary=brand if dark else readable,
        figure=figure, header=_mix(readable, (0, 0, 0), 0.15), gradient=[_mix(brand, (0, 0, 0), 0.3), brand,
                                                                          _mix(brand, (255, 255, 255), 0.25)],
        soft=soft, wash=[_mix(base.base, brand, 0.12), base.base, base.wash[2]])
    if accent:
        warm = _hex(accent)
        changes.update(warm=[warm, _mix(warm, (0, 0, 0), 0.15)], warm_figure=_mix(warm, (0, 0, 0), 0.2),
                       soft_warm=(_mix(warm, tint, 0.85), _mix(warm, tint, 0.45)))
    return replace(base, **changes)
