"""Bounding boxes from TitanOCR pixel space to normalised page coordinates.

TitanOCR boxes are pixels of the *prepared* page. Digital PDF pages are rendered without any prep, so a
normalised box (x / width, y / height) overlays exactly on our own render of the same page. OCR pages may
be deskewed, cropped or perspective-corrected; their boxes are still normalised to the prepared page, but
flagged ``exact=False`` so the viewer can show them as approximate.
"""

from typing import Any

# Prep steps that do not move content relative to the page (pure pixel adjustments).
SAFE_PREP = {"grayscale", "exif_transpose", "dpi_normalise", "dpi_normalize"}

Box = tuple[float, float, float, float]


def page_exact(page: dict[str, Any]) -> bool:
    applied = set((page.get("prep") or {}).get("applied") or ())
    return applied <= SAFE_PREP


def to_norm(bbox: list[float] | tuple[float, ...], page: dict[str, Any]) -> Box:
    width = float(page.get("width") or 1)
    height = float(page.get("height") or 1)
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])

    def clamp(value: float) -> float:
        return round(min(1.0, max(0.0, value)), 5)

    return clamp(x0 / width), clamp(y0 / height), clamp(x1 / width), clamp(y1 / height)


def union(boxes: list[Box]) -> Box:
    if not boxes:
        return 0.0, 0.0, 0.0, 0.0
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
