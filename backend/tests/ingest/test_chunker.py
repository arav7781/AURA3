"""Golden tests for the chunker on a real TitanOCR IR of the KrishiMitra deck (tests/fixtures)."""

import json
from pathlib import Path

import pytest

from aura.ingest.chunker import DocMeta, chunk_ir, reading_order, running_keys, table_markdown

FIXTURE = Path(__file__).parents[1] / "fixtures" / "krishimitra_ir.json"


@pytest.fixture(scope="module")
def fixture():
    return json.loads(FIXTURE.read_text())


def _chunks(fixture, **overrides):
    meta = dict(document_id="doc-1", startup_id="st-1", startup_name="KrishiMitra AI", domain="Agritech",
                stage="seed", doc_kind="deck", visibility="dao", content_hash=fixture["ir"]["content_hash"])
    meta.update(overrides)
    return chunk_ir(fixture["ir"], doc=DocMeta(**meta), verdicts=fixture["pages"])


def test_one_chunk_per_slide_with_titles(fixture):
    chunks = _chunks(fixture)
    assert len(chunks) == 11
    assert [c.page_no for c in chunks] == list(range(1, 12))
    assert chunks[3].slide_title == "Market Opportunity (TAM / SAM / SOM)"
    assert chunks[10].slide_title == "The Ask"


def test_market_slide_keeps_the_figure_and_context(fixture):
    market = _chunks(fixture)[3]
    assert "USD 82.3M in 2025" in market.text
    assert market.ctx == "KrishiMitra AI · Agritech · Seed · pitch deck p.4/11 · Market Opportunity (TAM / SAM / SOM)"
    assert market.embed_text.startswith(market.ctx)


def test_running_footer_and_page_numbers_are_removed(fixture):
    chunks = _chunks(fixture)
    assert "# / #" in running_keys(fixture["ir"]["pages"])
    assert not any("4 / 11" in c.text for c in chunks)
    # The CIN repeats in every footer but survives exactly once, on the title slide.
    assert sum(c.text.count("U62099MH2024PTC410567") for c in chunks) == 1


def test_provenance_is_normalised_and_complete(fixture):
    for chunk in _chunks(fixture):
        assert len(chunk.bbox) == 4 and all(0 <= v <= 1 for v in chunk.bbox)
        assert chunk.bbox[0] < chunk.bbox[2] and chunk.bbox[1] < chunk.bbox[3]
        assert chunk.geom_exact and chunk.origin == "digital" and not chunk.review
        assert chunk.lines and all(0 <= v <= 1 for line in chunk.lines for v in line["b"])
        assert chunk.cid.startswith("c:") and len(chunk.cid) == 9


def test_ids_are_stable_and_depend_on_content(fixture):
    first, second = _chunks(fixture), _chunks(fixture)
    assert [c.id for c in first] == [c.id for c in second]
    other = _chunks(fixture, content_hash="sha256:" + "0" * 64)
    assert first[0].id != other[0].id


def test_long_pages_split_at_block_boundaries(fixture):
    chunks = chunk_ir(fixture["ir"], doc=DocMeta("d", "s", "K", "A", "seed", "deck", "dao", "h"), max_tokens=40)
    assert len(chunks) > 11
    assert max(c.n_tokens for c in chunks) <= 140  # a single block may exceed the cap, never two


def test_table_markdown():
    table = {"n_rows": 3, "n_cols": 2, "header_rows": [0], "cells": [
        {"row": 0, "col": 0, "text": "Metric"}, {"row": 0, "col": 1, "text": "Value"},
        {"row": 1, "col": 0, "text": "TAM"}, {"row": 1, "col": 1, "text": "USD 82.3M"},
        {"row": 2, "col": 0, "text": "CAGR"}, {"row": 2, "col": 1, "text": "13.5%"},
    ]}
    assert table_markdown(table) == "| Metric | Value |\n|---|---|\n| TAM | USD 82.3M |\n| CAGR | 13.5% |"


# ── layouts with cards and columns (deck-2) ─────────────────────────────────────────────────────────────

def _line(text: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"text": text, "bbox": [x0, y0, x1, y1], "confidence": 1.0, "origin": "digital"}


def test_side_by_side_cards_are_read_one_card_at_a_time():
    lines = [_line("TAM — India agriculture", 100, 100, 500, 125), _line("SAM — Marathi/Hindi", 620, 100, 1000, 125),
             _line("IoT: USD 82.3M in 2025", 100, 133, 480, 158), _line("smallholder segment", 620, 133, 900, 158)]
    assert [ln["text"] for ln in reading_order(lines)] == [
        "TAM — India agriculture", "IoT: USD 82.3M in 2025", "SAM — Marathi/Hindi", "smallholder segment"]


def test_the_widest_gap_wins_over_a_narrow_band_that_crosses_two_columns():
    # Left: terms; right: a timeline. A thin strip of whitespace at y≈700 happens to cross both columns.
    lines = [_line("Raising Rs 12 crore", 167, 582, 704, 611), _line("pre-money", 167, 621, 675, 650),
             _line("Minimum raise: 60%", 167, 752, 639, 781), _line("Tranches", 939, 596, 1427, 623),
             _line("Tranche 1: 40%", 998, 657, 1333, 680), _line("Tranche 2: 30%", 998, 714, 1565, 737)]
    assert [ln["text"] for ln in reading_order(lines)] == [
        "Raising Rs 12 crore", "pre-money", "Minimum raise: 60%", "Tranches", "Tranche 1: 40%", "Tranche 2: 30%"]


def test_one_column_reads_top_to_bottom():
    lines = [_line("second line", 100, 140, 600, 165), _line("first line", 100, 100, 700, 125)]
    assert [ln["text"] for ln in reading_order(lines)] == ["first line", "second line"]


def _page(n: int, blocks: list[dict]) -> dict:
    return {"page_no": n, "width": 1754, "height": 1241, "origin": "digital", "blocks": blocks}


def _block(kind: str, order: int, *lines: dict) -> dict:
    boxes = [ln["bbox"] for ln in lines]
    return {"type": kind, "reading_order": order, "lines": list(lines),
            "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]}


def test_titles_cover_and_glyph_noise_in_a_card_deck():
    logo = lambda: _block("header", 0, _line("Acme AI", 162, 66, 308, 88))  # noqa: E731 — running header
    pages = [
        _page(1, [logo(), _block("header", 1, _line("Acme AI", 104, 300, 700, 400)),
                  _block("paragraph", 2, _line("Soil sensors for farmers", 104, 420, 900, 450)),
                  _block("paragraph", 3, _line("o", 1300, 500, 1330, 530))]),
        _page(2, [logo(), _block("header", 1, _line("02 · THE PROBLEM", 104, 160, 352, 180)),
                  _block("paragraph", 2, _line("Problem", 104, 181, 400, 245)),
                  _block("paragraph", 3, _line("Farmers lack soil data", 104, 300, 900, 330))]),
        _page(3, [logo(), _block("paragraph", 1, _line("03 · TEAM", 104, 160, 300, 180)),
                  _block("paragraph", 2, _line("Team", 104, 181, 300, 245))]),
    ]
    ir = {"pages": pages, "page_count": 3}
    chunks = chunk_ir(ir, doc=DocMeta("d", "s", "Acme AI", "Agritech", "seed", "deck", "dao", "h"))
    assert [c.slide_title for c in chunks] == ["Acme AI", "Problem", "Team"]
    # The logo repeats at the top edge and is dropped; the same words as the cover title are kept.
    assert chunks[0].text.splitlines() == ["Acme AI", "Soil sensors for farmers"]
    assert "Acme AI" not in chunks[1].text


CARDS = Path(__file__).parents[1] / "fixtures" / "krishimitra_cards_ir.json"


def test_a_card_layout_deck_reads_like_its_slides():
    """Golden test on TitanOCR's real IR of the seeded deck (stacked cards, stat tiles, a table, two columns)."""
    fixture = json.loads(CARDS.read_text())
    chunks = _chunks(fixture)
    assert [c.slide_title for c in chunks] == [
        "KrishiMitra AI", "Problem", "Solution", "Market Opportunity (TAM / SAM / SOM)", "Business Model",
        "Traction (as of FY2025)", "Unit Economics", "Competitive Landscape", "Go-to-Market & Key Risks", "Team",
        "The Ask"]
    text = {c.page_no: c.text for c in chunks}
    assert "TAM — India agriculture IoT: USD 82.3M in 2025,\nprojected USD 154.8M by 2030" in text[4]
    assert text[4].index("TAM —") < text[4].index("SAM —") < text[4].index("SOM —")
    assert "| Fasal | IoT sensors + AI for horticulture, premium farms |" in text[8]
    assert text[11].index("Use of funds") < text[11].index("Tranche 1") < text[11].index("Tranche 3")
    assert not any(len(line.strip()) <= 1 for t in text.values() for line in t.splitlines())
    assert all("01 / 11" not in t and "U62099MH2024PTC410567" not in t for p, t in text.items() if p > 1)
