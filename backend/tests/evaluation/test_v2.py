"""Evaluation v2: deck provenance, fiscal years, claims, citations, rubric scoring, registry, research replay."""

import asyncio
import json
from unittest.mock import patch

import pytest

from aura.evaluation import mca, scoring
from aura.evaluation.evidence import CompanyEvidence, normalise_financials
from aura.evaluation.graph import validate_citations
from aura.evaluation.report import printable_citations
from aura.evaluation.research import ResearchProvider

DECK = [
    {"cid": "c:market1", "chunk_id": "k1", "document_id": "d1", "doc_name": "deck.pdf", "page_no": 4,
     "bbox": [0.07, 0.06, 0.79, 0.44], "review": False, "conf_min": 1.0,
     "text": "TAM — India Agriculture IoT market: USD 82.3M in 2025, projected USD 154.8M by 2030 at 13.5%"},
    {"cid": "c:tract01", "chunk_id": "k2", "document_id": "d1", "doc_name": "deck.pdf", "page_no": 6,
     "bbox": [0.07, 0.06, 0.56, 0.37], "review": False, "conf_min": 1.0,
     "text": "ARR: Rs 3.1 crore in FY2025 (68% subscription, 32% sensor sales)."},
    {"cid": "c:scan001", "chunk_id": "k3", "document_id": "d2", "doc_name": "scan.pdf", "page_no": 2,
     "bbox": [0.1, 0.1, 0.9, 0.3], "review": True, "conf_min": 0.71,
     "text": "Revenue was Rs 0.9 crore in FY2024."},
]
COMPANY = CompanyEvidence(profile_text="KrishiMitra AI · Agritech", chunks=DECK)


def company_metric(**kw):
    return {"kind": "company_reported", "source_url": None, "market": "India agriculture IoT",
            "geography": "India", **kw}


def test_fiscal_year_revenue_is_charted_with_its_deck_citation():
    raw = {"projected_revenue": [company_metric(value=3.1, unit="INR crore", year=2025, metric="ARR",
                                                quote="ARR: Rs 3.1 crore in FY2025")]}
    result = normalise_financials(raw, [], COMPANY)
    row = result["projected_revenue"][0]
    assert row["year"] == 2025 and row["revenue"] == 31
    assert row["citation"] == {"cid": "c:tract01", "chunk_id": "k2", "document_id": "d1", "page_no": 6,
                               "bbox": [0.07, 0.06, 0.56, 0.37]}
    assert row["source_title"] == "deck.pdf, p.6"


def test_deck_market_size_is_a_claim_not_market_data():
    raw = {"market_sizing": {"tam_usd_b": company_metric(value=82.3, unit="USD million", year=2025,
                                                         quote="India Agriculture IoT market: USD 82.3M in 2025")}}
    result = normalise_financials(raw, [], COMPANY)
    market = result["market_sizing"]
    assert market["tam_usd_b"] is None and "tam_usd_b" not in market["evidence"]
    claim = market["claims"]["tam_usd_b"]
    assert claim["citation"]["page_no"] == 4 and round(claim["normalised"], 4) == 0.0823
    assert any("the deck claims 82.3 USD million (p.4)" in gap for gap in result["data_gaps"])


def test_low_confidence_ocr_figures_stay_out_of_charts():
    raw = {"projected_revenue": [company_metric(value=0.9, unit="INR crore", year=2024, metric="Revenue",
                                                quote="Revenue was Rs 0.9 crore in FY2024")]}
    result = normalise_financials(raw, [], COMPANY)
    assert result["projected_revenue"] == []
    assert any("low-confidence OCR" in gap for gap in result["data_gaps"])


def test_publisher_figures_quoted_from_the_deck_are_claims():
    # The deck names MarketsandMarkets, so the model labels the figure as sourced; no web excerpt contains it.
    raw = {"market_sizing": {"tam_usd_b": {
        "kind": "reported", "source_url": "https://www.marketsandmarkets.com/x", "value": 82.3,
        "unit": "USD million", "year": 2025, "quote": "India Agriculture IoT market: USD 82.3M in 2025",
        "market": "India agriculture IoT", "geography": "India"}}}
    market = normalise_financials(raw, [], COMPANY)["market_sizing"]
    assert market["tam_usd_b"] is None
    claim = market["claims"]["tam_usd_b"]
    assert claim["kind"] == "company_reported" and claim["source_url"] is None
    assert claim["citation"]["page_no"] == 4 and claim["check"] == {"status": "unverified"}


WEB = [{"title": "Agri IoT report", "url": "https://example.org/agri-iot", "retrieved_at": "2026-10-26T00:00:00Z",
        "snippet": "The India agriculture IoT market was valued at USD 82.3 million in 2025.", "query": "q"}]


def deck_claim(value: float) -> dict:
    return company_metric(value=value, unit="USD million", year=2025,
                          quote=f"India Agriculture IoT market: USD {value:g}M in 2025")


def web_tam(value: float = 82.3) -> dict:
    return {"kind": "reported", "source_url": "https://example.org/agri-iot", "value": value, "unit": "USD million",
            "year": 2025, "quote": f"India agriculture IoT market was valued at USD {value:g} million in 2025",
            "market": "India agriculture IoT", "geography": "India"}


def test_deck_claim_is_cross_checked_against_the_sourced_figure():
    result = normalise_financials({"market_sizing": {"tam_usd_b": web_tam()},
                                   "deck_market_claims": {"tam_usd_b": deck_claim(82.3)}}, WEB, COMPANY)
    market = result["market_sizing"]
    assert round(market["tam_usd_b"], 4) == 0.0823 and market["evidence"]["tam_usd_b"]["kind"] == "reported"
    claim = market["claims"]["tam_usd_b"]
    assert claim["citation"]["page_no"] == 4
    assert claim["check"]["status"] == "consistent"
    assert not any(gap.startswith("TAM") for gap in result["data_gaps"])


def test_a_deck_claim_that_differs_from_its_source_is_called_out():
    deck = CompanyEvidence(chunks=[{**DECK[0], "text": "India Agriculture IoT market: USD 120M in 2025"}])
    result = normalise_financials({"market_sizing": {"tam_usd_b": web_tam()},
                                   "deck_market_claims": {"tam_usd_b": deck_claim(120)}}, WEB, deck)
    claim = result["market_sizing"]["claims"]["tam_usd_b"]
    assert claim["check"] == {"status": "differs", "source_value": 0.0823, "ratio": 1.46}
    assert any("the deck claims 120 USD million (p.4), but the retrieved source reports 82.3 USD million"
               in gap for gap in result["data_gaps"])


def test_quotes_must_come_from_the_startups_own_material():
    raw = {"projected_revenue": [company_metric(value=9.9, unit="INR crore", year=2025, metric="ARR",
                                                quote="ARR: Rs 9.9 crore in FY2025")]}
    assert normalise_financials(raw, [], COMPANY)["projected_revenue"] == []


def test_citation_validation_keeps_only_retrieved_ids():
    text, used, removed = validate_citations(
        "Claim [c:abcdefg] and [c:zzzzzzz]; web [w:1] [w:3].", {"c:abcdefg"}, web_count=2
    )
    assert "[c:abcdefg]" in text and "[w:1]" in text
    assert "[c:zzzzzzz]" not in text and "[w:3]" not in text
    assert used == ["c:abcdefg", "w:1"] and removed == ["c:zzzzzzz", "w:3"]


def test_citation_validation_repairs_slips_and_removes_the_rest():
    text, used, removed = validate_citations(
        "ARR [c:6]. TAM [c:abcdefg, w:2; c:nope]. Growth [W: 02] [w:1-2] [w:1, 3] [c:abcdefg p.4] [c:9].",
        {"c:abcdefg"}, web_count=2, pages={6: "c:abcdefg"},
    )
    assert text == "ARR [c:abcdefg]. TAM [c:abcdefg][w:2]. Growth [w:2] [w:1][w:2] [w:1] [c:abcdefg]."
    assert removed == ["c:nope", "3", "c:9"]
    assert validate_citations("Revenue grew [c:6].", {"c:abcdefg"}, 0)[0] == "Revenue grew."


def test_printable_citations():
    analysis = {"citations": {"c:abcdefg": {"page_no": 4}}}
    assert printable_citations("TAM [c:abcdefg] per [w:2].", analysis) == "TAM (deck p.4) per [2]."


def test_overall_is_the_weighted_mean_and_labels_follow_thresholds():
    all_eight = {k: 8.0 for k in scoring.dimensions()}
    assert scoring.overall_score(all_eight) == 8.0 and scoring.label_for(8.0, []) == "Strong Buy"
    assert scoring.label_for(6.5, []) == "Buy" and scoring.label_for(5.0, []) == "Hold"
    assert scoring.label_for(4.9, []) == "Pass"
    assert scoring.overall_score({"product": 9, "market": 9}) is None
    assert scoring.label_for(None, []) == "Insufficient data"


def test_compliance_flags_cap_the_label():
    assert scoring.label_for(8.5, ["COMPANY_STATUS_STRUCK_OFF"]) == "Pass"
    assert scoring.label_for(8.5, ["NAME_MISMATCH"]) == "Hold"
    assert scoring.label_for(4.0, ["NAME_MISMATCH"]) == "Pass"  # a cap never raises a label
    assert scoring.label_for(7.0, ["SANDBOX_REGISTRY", "DECK_HIDDEN_INSTRUCTIONS"]) == "Buy"


def test_scores_are_a_trimmed_mean_of_five_samples():
    samples = iter([
        {"product": (6.0, "a"), "market": (5.0, "a")},
        {"product": (8.0, "b"), "market": (5.5, "b")},
        {"product": (7.0, "c"), "market": (9.0, "c")},
        {"product": (7.0, "d"), "market": (6.0, "d")},
        {"product": (2.0, "e"), "market": (6.0, "e")},
    ])

    async def fake_once(evidence):
        return next(samples)

    with patch("aura.evaluation.scoring._score_once", side_effect=fake_once):
        result = asyncio.run(scoring.score("evidence"))
    # product: drop 2 and 8, mean(6, 7, 7); market: drop 5 and 9, mean(5.5, 6, 6)
    assert result["category_scores"] == {"product": 6.7, "market": 5.8}
    assert result["rationales"] == {"product": "c", "market": "d"}
    assert result["score_spread"] == {"product": 6.0, "market": 4.0}
    assert result["samples"] == 5


@pytest.fixture
def registry():
    mca.registry_fixtures.clear()
    mca.registry_fixtures["U72900KA2022PTC123450"] = {
        "status": "STRUCK_OFF", "registered_name": "PORTPULSE PRIVATE LIMITED", "directors": ["A"],
        "incorporation_year": 2022, "state": "Karnataka"}
    mca.registry_fixtures["U66000MH2023PTC234567"] = {
        "status": "ACTIVE", "registered_name": "RAKSHA DIGITAL SERVICES PRIVATE LIMITED", "directors": ["B"],
        "incorporation_year": 2023, "state": "Maharashtra"}
    yield
    mca.registry_fixtures.clear()


def test_registry_outcomes(app_env, registry):
    struck = mca.verify("U72900KA2022PTC123450", legal_name="PortPulse Private Limited")
    assert not struck["mca_verified"] and struck["source"] == "registry_fixture"
    assert mca.consistency_flags(struck, legal_name="PortPulse Private Limited") == ["COMPANY_STATUS_STRUCK_OFF"]

    mismatch = mca.verify("U66000MH2023PTC234567", legal_name="Suraksha Insure Private Limited")
    assert mca.consistency_flags(mismatch, legal_name="Suraksha Insure Private Limited") == ["NAME_MISMATCH"]

    malformed = mca.verify("U12345MH2024PTC12345", legal_name="Tattva Foods")
    assert not malformed["mca_verified"]
    assert mca.consistency_flags(malformed, legal_name="Tattva Foods") == ["INVALID_CIN_FORMAT"]

    unknown = mca.verify("U62099MH2024PTC999999", legal_name="New Co Private Limited", claimed_directors=["X"])
    assert unknown["mca_verified"] and unknown["source"] == "sandbox" and unknown["state"] == "Maharashtra"
    assert mca.consistency_flags(unknown, legal_name="New Co Private Limited") == ["SANDBOX_REGISTRY"]
    assert mca.consistency_flags({"cin": None}, legal_name="x") == ["MCA_NOT_VERIFIED"]


def test_research_record_then_replay(tmp_path):
    cassette = tmp_path / "research.json"
    results = [{"title": "T", "url": "https://example.org/a", "snippet": "S"}]
    with patch("aura.evaluation.research.web_search", return_value=results) as live:
        recorder = ResearchProvider("record", cassette)
        first = asyncio.run(recorder.search("India agritech market  size"))
        recorder.save()
        assert live.call_count == 1
    saved = json.loads(cassette.read_text())["queries"]
    assert list(saved) == ["india agritech market size"]
    with patch("aura.evaluation.research.web_search") as live:
        replay = ResearchProvider("replay", cassette)
        again = asyncio.run(replay.search("India agritech market size"))
        missing = asyncio.run(replay.search("something never recorded"))
        assert live.call_count == 0
    assert again == first and missing == []


def test_replay_answers_a_reworded_query_from_the_closest_recording(tmp_path):
    cassette = tmp_path / "research.json"
    recorded = {
        "india agriculture iot market size 2025 2026 cagr forecast": {
            "query": "q1", "retrieved_at": "t1", "results": [{"title": "IoT", "url": "https://a.example/1", "snippet": "s"}]},
        "agritech competitors india funding": {
            "query": "q2", "retrieved_at": "t2", "results": [{"title": "Comp", "url": "https://a.example/2", "snippet": "s"}]},
    }
    cassette.write_text(json.dumps({"queries": recorded}))
    replay = ResearchProvider("replay", cassette)
    reworded = asyncio.run(replay.search("India agriculture IoT market size 2025 2030 CAGR forecasts"))
    assert [r["url"] for r in reworded] == ["https://a.example/1"] and reworded[0]["retrieved_at"] == "t1"
    assert asyncio.run(replay.search("main competitors of agritech startups in India")) [0]["url"] == "https://a.example/2"
    assert asyncio.run(replay.search("dairy cooperative milk procurement Gujarat")) == []


def test_rupee_market_claims_are_kept_and_never_converted():
    deck = CompanyEvidence(chunks=[{**DECK[0], "text": "TAM: India agriculture IoT market Rs 700 crore in 2025"}])
    claim = company_metric(value=700, unit="INR crore", year=2025, quote="India agriculture IoT market Rs 700 crore in 2025")
    result = normalise_financials({"market_sizing": {"tam_usd_b": web_tam()}, "deck_market_claims": {"tam_usd_b": claim}},
                                  WEB, deck)
    kept = result["market_sizing"]["claims"]["tam_usd_b"]
    assert kept["currency"] == "INR" and kept["normalised"] == 7.0 and kept["citation"]["page_no"] == 4
    assert kept["check"]["status"] == "different_currency"
    assert any("a different currency, so the two were not compared" in gap for gap in result["data_gaps"])
