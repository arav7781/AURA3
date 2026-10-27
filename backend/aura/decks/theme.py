"""AURA3's deck theme: the platform's own palette and type, so every seeded pitch deck looks like it belongs to
the product. Colours are (r, g, b) 0-255; fonts are Geist (SIL OFL, vendored in ``fonts/``).

The slide background stays near white (luminance > 0.9) so hidden-text checks behave like real decks: white
text on it is invisible, white text on a jade badge is not. Every shape that carries white text has a solid
jade fill under its gradient for the same reason.
"""

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
