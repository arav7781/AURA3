"""Golden tests for the chunker on a real TitanOCR IR of the KrishiMitra deck (tests/fixtures)."""

import json
from pathlib import Path

import pytest

from aura.ingest.chunker import DocMeta, chunk_ir, running_keys, table_markdown

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
