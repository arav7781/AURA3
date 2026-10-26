"""Page images for the evidence viewer, rendered at the same pixel size as TitanOCR's page space so the
normalised boxes line up exactly. Saved as WebP to keep 25 decks' worth of pages small."""

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps


def render_pdf_pages(pdf_path: Path, out_dir: Path, sizes: dict[int, tuple[int, int]]) -> dict[int, Path]:
    """Render each page to ``out_dir/{n}.webp`` at the pixel size TitanOCR reported for that page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[int, Path] = {}
    document = pdfium.PdfDocument(pdf_path)
    try:
        for index in range(len(document)):
            page_no = index + 1
            page = document[index]
            width_pt = page.get_width()
            target = sizes.get(page_no)
            scale = (target[0] / width_pt) if target else 150 / 72
            image = page.render(scale=scale).to_pil().convert("RGB")
            if target and image.size != target:
                image = image.resize(target, Image.Resampling.LANCZOS)
            path = out_dir / f"{page_no}.webp"
            image.save(path, "WEBP", quality=82, method=4)
            written[page_no] = path
    finally:
        document.close()
    return written


def render_image_page(image_path: Path, out_dir: Path, size: tuple[int, int] | None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        if size and image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        path = out_dir / "1.webp"
        image.save(path, "WEBP", quality=82, method=4)
    return path
