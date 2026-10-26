"""Offline regressions for financial evidence and the shared PDF/dashboard snapshot (ported to v2)."""

import asyncio
import copy
import io
import math
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from pypdf import PdfReader

from aura.evaluation import scoring
from aura.evaluation.context import StartupContext
from aura.evaluation.evidence import normalise_financials, report_snapshot, source_catalog
from aura.evaluation.graph import SECTION_TITLES, run_evaluation, to_frontend
from aura.evaluation.report import build_pdf_report
from aura.evaluation.search import format_results

SOURCE = {
    "title": "Example research publisher", "url": "https://example.org/market",
    "snippet": "The India irrigation market was USD 850 million in 2023. "
               "The India irrigation market is forecast to reach USD 2.4 billion in 2027. "
               "The forecast CAGR is 12.5% for 2023-2027.",
    "retrieved_at": "2026-09-24T10:00:00Z", "query": "India irrigation market report",
}
COMPANY_TEXT = "In 2024, ARR was Rs 3.1 crore. In 2025, revenue was Rs 2 crore."
STARTUP = {"startup_id": "evidence-test", "name": "Irrigation Example", "domain": "Agritech",
           "description": COMPANY_TEXT, "team": "Example team", "verification": {}, "compliance_flags": []}


def metric(**overrides):
    return {
        "value": 850, "unit": "USD million", "year": 2023, "period": "2023",
        "kind": "reported", "source_url": SOURCE["url"],
        "quote": "The India irrigation market was USD 850 million in 2023.",
        "market": "irrigation", "geography": "India", **overrides,
    }


def raw_report():
    return {
        "market_sizing": {
            "tam_usd_b": metric(),
            "cagr_pct": metric(value=12.5, unit="%", year=None, period="2023-2027", kind="source_forecast",
                               quote="The forecast CAGR is 12.5% for 2023-2027."),
            "trend": [metric(), metric(value=2.4, unit="USD billion", year=2027, period="2027",
                                       kind="source_forecast",
                                       quote="The India irrigation market is forecast to reach USD 2.4 billion in 2027.")],
        },
        "projected_revenue": [metric(value=3.1, unit="INR crore", year=2024, period="2024",
                                     kind="company_reported", source_url=None,
                                     quote="In 2024, ARR was Rs 3.1 crore.", metric="ARR")],
    }


def scored(category_scores: dict[str, float], flags: list[str] | None = None) -> dict:
    overall = scoring.overall_score(category_scores)
    return {"overall_score": overall, "recommendation_label": scoring.label_for(overall, flags or []),
            "category_scores": category_scores}


def snapshot():
    return {**normalise_financials(raw_report(), [SOURCE], COMPANY_TEXT),
            **scored({"product": 6.7, "market": 6.5, "team": 6.0, "business_model": 6.2, "traction": 5.9}),
            "sections": {key: "Evidence-based test report." for key in SECTION_TITLES},
            "sources": [SOURCE], "generated_at": "2026-09-24T10:00:00Z", "compliance_flags": []}


def empty_report():
    return {**normalise_financials({}, []), **scored({}), "sections": {key: "" for key in SECTION_TITLES},
            "sources": [], "compliance_flags": []}


class FinancialEvidenceTests(unittest.TestCase):
    def test_missing_data_has_no_market_revenue_or_default_scores(self):
        result = empty_report()
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["category_scores"], {})
        self.assertEqual(result["recommendation_label"], "Insufficient data")
        self.assertIsNone(result["market_sizing"]["tam_usd_b"])
        self.assertIsNone(result["market_sizing"]["cagr_pct"])
        self.assertEqual(result["market_sizing"]["trend"], [])
        self.assertEqual(result["projected_revenue"], [])

    def test_only_published_years_and_native_currency_reach_frontend(self):
        frontend = to_frontend(snapshot())
        self.assertEqual(frontend["marketSizing"]["tam_usd_b"], 0.85)
        self.assertIsNone(frontend["marketSizing"]["sam_usd_b"])
        self.assertEqual([r["year"] for r in frontend["marketSizing"]["trend"]], [2023, 2027])
        self.assertEqual(frontend["marketSizing"]["trend"][1]["kind"], "source_forecast")
        self.assertEqual(frontend["revenueCurrency"], "INR")
        self.assertEqual(frontend["revenueMetric"], "ARR")
        self.assertEqual(frontend["projectedRevenue"][0]["revenue"], 31)
        self.assertEqual(frontend["projectedRevenue"][0]["quote"], "In 2024, ARR was Rs 3.1 crore.")

    def test_new_search_results_change_values_and_sources(self):
        changed_source = {**SOURCE, "url": "https://example.org/new-market",
                          "snippet": "The India irrigation market was USD 920 million in 2024."}
        raw = {"market_sizing": {"tam_usd_b": metric(value=920, year=2024, period="2024",
               quote=changed_source["snippet"], source_url=changed_source["url"])}}
        first = snapshot()["market_sizing"]
        second = normalise_financials(raw, [changed_source])["market_sizing"]
        self.assertEqual(second["tam_usd_b"], 0.92)
        self.assertNotEqual(first["tam_usd_b"], second["tam_usd_b"])
        self.assertEqual(second["evidence"]["tam_usd_b"]["source_url"], changed_source["url"])

    def test_unsubstantiated_values_units_quotes_urls_and_dates_are_omitted(self):
        invalid = [
            {"value": 99}, {"value": 85, "unit": "USD"}, {"value": math.nan}, {"value": math.inf}, {"value": True},
            {"unit": "USD billion"}, {"unit": "INR million"}, {"year": 2024},
            {"quote": "The market was USD 850 million in 2023 according to an invented source."},
            {"source_url": "https://example.org/not-retrieved"}, {"kind": "analyst_estimate"},
            {"year": None}, {"value": -850},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                result = normalise_financials({"market_sizing": {"tam_usd_b": metric(**overrides)}}, [SOURCE])
                self.assertIsNone(result["market_sizing"]["tam_usd_b"])

    def test_source_forecast_in_past_does_not_become_historical_actual(self):
        source = {**SOURCE, "snippet": "In 2020, this market was forecast at USD 850 million for 2023."}
        raw = {"market_sizing": {"trend": [metric(kind="source_forecast", quote=source["snippet"])]}}
        result = normalise_financials(raw, [source])
        self.assertEqual(result["market_sizing"]["trend"][0]["kind"], "source_forecast")

    def test_company_claims_require_dated_quotes_and_keep_arr_separate(self):
        raw = raw_report()
        raw["projected_revenue"].append(metric(value=2, unit="INR crore", year=2025, period="2025",
            source_url=None, kind="company_reported", quote="In 2025, revenue was Rs 2 crore.", metric="Revenue"))
        result = normalise_financials(raw, [SOURCE], COMPANY_TEXT)
        self.assertEqual(len(result["projected_revenue"]), 1)
        self.assertTrue(any("revenue/ARR" in gap for gap in result["data_gaps"]))
        raw["projected_revenue"][0]["quote"] = "ARR was Rs 3.1 crore."
        result = normalise_financials(raw, [SOURCE], "ARR was Rs 3.1 crore.")
        self.assertEqual(result["projected_revenue"], [])

    def test_conflicting_sizes_are_removed_without_clamping(self):
        raw = raw_report()
        raw["market_sizing"]["sam_usd_b"] = raw["market_sizing"]["trend"][1]
        result = normalise_financials(raw, [SOURCE])
        self.assertIsNone(result["market_sizing"]["sam_usd_b"])
        self.assertEqual(result["market_sizing"]["tam_usd_b"], 0.85)

    def test_duplicate_sources_preserve_all_excerpts(self):
        catalog = source_catalog([SOURCE, {**SOURCE, "snippet": "Another retrieved excerpt."}])
        self.assertEqual(len(catalog), 1)
        self.assertIn("Another retrieved excerpt.", catalog[0]["snippet"])

    def test_legacy_report_hides_generated_series_without_mutating_saved_data(self):
        old = snapshot()
        old.pop("evidence_version")
        original = copy.deepcopy(old)
        frontend = to_frontend(old)
        self.assertEqual(frontend["marketSizing"]["trend"], [])
        self.assertIsNone(frontend["marketSizing"]["tam_usd_b"])
        self.assertEqual(frontend["evidenceVersion"], 0)
        self.assertEqual(old, original)
        self.assertEqual(report_snapshot(old)["projected_revenue"], [])


class ReportIntegrationTests(unittest.TestCase):
    def test_pdf_contains_snapshot_source_quotes_dates_currency_and_gaps(self):
        pdf = build_pdf_report(STARTUP, snapshot())
        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("2026-09-24T10:00:00Z", text)
        self.assertIn("USD 850 million in 2023", text)
        self.assertIn("INR crore", text)
        self.assertIn("Company-reported (unverified)", text)
        self.assertIn("SAM: no usable source excerpt", text)
        uris = [str(annotation.get_object().get('/A', {}).get('/URI', ''))
                for page in reader.pages for annotation in page.get('/Annots', [])]
        self.assertIn(SOURCE["url"], uris)

    def test_empty_report_pdf_renders_without_invented_charts(self):
        pdf = build_pdf_report(STARTUP, empty_report())
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("Unavailable", text)
        self.assertIn("No years were interpolated", " ".join(text.split()))
        self.assertNotIn("Historical (est.)", text)

    def test_search_is_attempted_even_when_model_skips_tools(self):
        context = StartupContext(
            startup_id="evidence-test", name="Irrigation Example", legal_name="Irrigation Example Pvt Ltd",
            domain="Agritech", stage="seed", profile={"one_liner": "Drip irrigation for small farms"},
            verification={}, flags=[],
            chunks=[{"cid": "c:aaaaaaa", "chunk_id": "chunk-1", "document_id": "doc-1", "doc_name": "deck.pdf",
                     "page_no": 6, "bbox": [0.1, 0.1, 0.9, 0.4], "text": COMPANY_TEXT, "slide_title": "Traction",
                     "review": False, "conf_min": 1.0, "injection_suspected": False, "n_tokens": 20}],
        )

        class CountingResearch:
            def __init__(self):
                self.calls: list[str] = []

            async def search(self, query, max_results=5):
                self.calls.append(query)
                return []

            def save(self):
                pass

        class FakeModel:
            def bind_tools(self, tools):
                return self

            async def ainvoke(self, messages):
                return AIMessage(content="Ready")

        async def fake_json(system, user, **kwargs):
            if "Extract the financial evidence" in system:
                return {**raw_report(), "market_sizing": {}}
            return {key: "No external evidence is available. ARR was Rs 3.1 crore in 2024 [c:aaaaaaa] [c:zzzzzzz]."
                    for key in SECTION_TITLES}

        async def fake_score(evidence, samples=3):
            return {"category_scores": {"product": 6.0, "market": 5.0, "team": 6.0, "business_model": 6.0,
                                        "traction": 6.0}, "rationales": {}, "score_spread": {}, "samples": 3,
                    "rubric_version": "r1"}

        research = CountingResearch()
        with patch("aura.evaluation.graph.chat_model", return_value=FakeModel()), \
             patch("aura.evaluation.graph.ainvoke_json", side_effect=fake_json), \
             patch("aura.evaluation.graph.scoring.score", side_effect=fake_score):
            result = asyncio.run(run_evaluation(context, research=research, progress=lambda *a: None))
        self.assertEqual(len(research.calls), 2)
        self.assertIn("Agritech", research.calls[0])
        self.assertEqual(result["sources"], [])
        self.assertIsNone(result["market_sizing"]["tam_usd_b"])
        self.assertEqual(result["revenue_currency"], "INR")
        self.assertEqual(result["projected_revenue"][0]["citation"]["page_no"], 6)
        self.assertEqual(result["overall_score"], 5.8)  # weighted mean computed in code
        self.assertEqual(result["recommendation_label"], "Hold")
        self.assertIn("[c:aaaaaaa]", result["sections"]["executive_summary"])
        self.assertNotIn("[c:zzzzzzz]", result["sections"]["executive_summary"])  # unknown citation stripped
        self.assertEqual(result["citations"]["c:aaaaaaa"]["page_no"], 6)
        self.assertEqual(result["citations_removed"], len(SECTION_TITLES))
        self.assertNotIn("pre-trained knowledge", format_results([], "example"))


if __name__ == "__main__":
    unittest.main()
