"""Artwork drawn into slides as PNGs: the market slide's nested rings, rendered with anti-aliased masks and no
metadata, so the bytes are identical on every run. No text is drawn into images (OCR would read it)."""

import io
import math
from functools import cache

import numpy as np
from PIL import Image, ImageDraw

from aura.decks.theme import RGB

SCALE = 4


def _png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _gradient(size: int, stops: list[RGB], angle_deg: float = 45) -> np.ndarray:
    """An RGB gradient across a square, from the top-left corner to the bottom-right at 45°."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / max(1, size - 1)
    a = math.radians(angle_deg)
    t = np.clip((xx * math.cos(a) + yy * math.sin(a)) / (math.cos(a) + math.sin(a)), 0, 1)
    out = np.zeros((size, size, 3), dtype=np.float32)
    positions = np.linspace(0, 1, len(stops))
    for channel in range(3):
        out[..., channel] = np.interp(t, positions, [s[channel] for s in stops])
    return out


def _compose(size: int, layers: list[tuple[Image.Image, np.ndarray | RGB]]) -> Image.Image:
    """Paint each (mask, colour or gradient) layer in order onto a transparent square."""
    colour_acc = np.zeros((size, size, 3), dtype=np.float32)  # premultiplied
    alpha_acc = np.zeros((size, size, 1), dtype=np.float32)
    for mask, paint in layers:
        alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255
        colour = paint if isinstance(paint, np.ndarray) else np.broadcast_to(np.array(paint, np.float32), (size, size, 3))
        colour_acc = colour * alpha + colour_acc * (1 - alpha)
        alpha_acc = alpha + alpha_acc * (1 - alpha)
    straight = np.where(alpha_acc > 0, colour_acc / np.maximum(alpha_acc, 1e-6), 0)
    rgba = np.concatenate([straight, alpha_acc * 255], axis=-1)
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")


def _mask(px: int, draw) -> Image.Image:
    """A shape drawn at SCALE× and box-filtered down: an anti-aliased mask."""
    big = Image.new("L", (px * SCALE, px * SCALE), 0)
    draw(ImageDraw.Draw(big), px * SCALE)
    return big.resize((px, px), Image.Resampling.BOX)


RING_FRACTIONS = (1.0, 0.66, 0.36)  # TAM, SAM, SOM radii, as fractions of the outer radius


@cache
def market_rings(soft: tuple[RGB, RGB, RGB], soft_warm: tuple[RGB, RGB], px: int = 640) -> bytes:
    """Three nested circles sharing their lowest point: TAM, SAM, SOM, in a palette's pale tints. The innermost
    stays pale too: a solid dark disc is read by OCR as a bullet glyph."""
    fills: list[np.ndarray | RGB] = [soft[0], soft[1], soft_warm[0]]
    edges: list[RGB | None] = [soft[2], soft[2], soft_warm[1]]
    layers: list[tuple[Image.Image, np.ndarray | RGB]] = []
    for fraction, fill, edge in zip(RING_FRACTIONS, fills, edges, strict=True):
        def box(size: int, fraction: float = fraction) -> list[float]:
            pad = size * 0.02
            r = (size - 2 * pad) / 2 * fraction
            return [size / 2 - r, size - pad - 2 * r, size / 2 + r, size - pad]
        layers.append((_mask(px, lambda d, size, box=box: d.ellipse(box(size), fill=255)), fill))
        if edge:
            layers.append((_mask(px, lambda d, size, box=box: d.ellipse(box(size), outline=255, width=round(size * 0.004))), edge))
    return _png(_compose(px, layers))
