"""Turn a rendered deck into a "scanned" one: every page becomes a grey, slightly skewed, noisy JPEG with
no text layer, so ingestion has to OCR it. Seeded, so the output is the same on every run."""

import io

import numpy as np
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from aura.decks.spec import Scan


def scan_pdf(pdf: bytes, settings: Scan) -> bytes:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf)
    out = io.BytesIO()
    c = canvas.Canvas(out, invariant=1, pageCompression=1)
    for index in range(len(document)):
        page = document[index]
        width, height = page.get_size()
        image = page.render(scale=settings.dpi / 72).to_pil().convert("L")
        rng = np.random.default_rng(settings.seed + index)
        # Pages of a real scan are not all tilted the same way.
        angle = settings.skew_deg * (1 if index % 2 == 0 else -0.6) * (0.8 + 0.4 * rng.random())
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        if settings.noise:
            pixels = np.asarray(image, dtype=np.float32)
            pixels += rng.normal(0.0, settings.noise * 255, pixels.shape)
            image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
        jpeg = io.BytesIO()
        image.save(jpeg, format="JPEG", quality=settings.jpeg_quality, optimize=False)
        c.setPageSize((width, height))
        c.drawImage(ImageReader(io.BytesIO(jpeg.getvalue())), 0, 0, width, height)
        c.showPage()
    c.save()
    return out.getvalue()
