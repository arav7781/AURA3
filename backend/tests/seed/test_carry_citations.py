"""Re-rendering a deck changes its passage ids; the seeder carries every citation over to the new passages."""

from types import SimpleNamespace

from aura.core.db import read_session, write_tx
from aura.models import Evaluation
from seed.run import carry_citations
from tests.conftest import register

OLD = [
    {"cid": "c:aaaaaaa", "id": "old-4", "document_id": "doc-old", "page_no": 4, "bbox": [0, 0, 1, 1], "slide_title": "Market",
     "text": "TAM — India agriculture IoT: USD 82.3M in 2025, projected USD 154.8M by 2030"},
    {"cid": "c:bbbbbbb", "id": "old-6", "document_id": "doc-old", "page_no": 6, "bbox": [0, 0, 1, 1], "slide_title": "Traction",
     "text": "ARR: Rs 3.1 crore in FY2025"},
]
NEW = [
    {"cid": "c:ccccccc", "id": "new-4a", "document_id": "doc-new", "page_no": 4, "bbox": [0.1, 0.2, 0.5, 0.4],
     "slide_title": "Market Opportunity", "text": "04 · MARKET\nMarket Opportunity\nTAM — India agriculture IoT: USD 82.3M in 2025,\nprojected USD 154.8M by 2030"},
    {"cid": "c:ddddddd", "id": "new-4b", "document_id": "doc-new", "page_no": 4, "bbox": [0.1, 0.5, 0.5, 0.7],
     "slide_title": "Market Opportunity", "text": "SOM — 3-year obtainable share"},
    {"cid": "c:eeeeeee", "id": "new-6", "document_id": "doc-new", "page_no": 6, "bbox": [0.1, 0.2, 0.9, 0.8],
     "slide_title": "Traction", "text": "Rs 3.1 crore ARR: Rs 3.1 crore in FY2025"},
]


def test_citations_follow_the_passage_on_the_same_page(client):
    register(client, role="startup", startup_name="Carry Test")
    startup_id = client.get("/api/me").json()["startup"]["id"]
    result = {
        "sections": {"market": "The TAM is USD 82.3M [c:aaaaaaa]; ARR Rs 3.1 crore [c:bbbbbbb]."},
        "citations": {"c:aaaaaaa": {"chunk_id": "old-4", "document_id": "doc-old", "page_no": 4, "bbox": [0, 0, 1, 1]}},
        "market_sizing": {"claims": {"tam": {"citation": {"cid": "c:aaaaaaa", "chunk_id": "old-4", "document_id": "doc-old",
                                                          "page_no": 4, "bbox": [0, 0, 1, 1]}}}},
    }
    with write_tx() as s:
        s.add(Evaluation(startup_id=startup_id, version=1, status="complete", result=result, input_hash="old-hash"))

    moved = carry_citations(SimpleNamespace(slug="no-cache-for-this-test"), startup_id, OLD, NEW)

    assert moved == 2
    with read_session() as s:
        evaluation = s.query(Evaluation).filter_by(startup_id=startup_id).one()
        carried = evaluation.result
    assert carried["sections"]["market"] == "The TAM is USD 82.3M [c:ccccccc]; ARR Rs 3.1 crore [c:eeeeeee]."
    assert carried["citations"] == {"c:ccccccc": {"chunk_id": "new-4a", "document_id": "doc-new", "page_no": 4,
                                                  "bbox": [0.1, 0.2, 0.5, 0.4]}}
    assert carried["market_sizing"]["claims"]["tam"]["citation"]["cid"] == "c:ccccccc"
    assert carried["carried_from_input_hash"] == "old-hash" and evaluation.input_hash == carried["input_hash"] != "old-hash"
