"""A module-scoped live environment: real TitanOCR, the LLM gateway (embeddings) and Qdrant.

Skipped unless Qdrant is reachable and the gateway is configured. One founder uploads the KrishiMitra deck
once per module; tests then query it.
"""

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from aura.core.config import BACKEND_DIR
from tests.conftest import TEST_ROOT, _drop_qdrant_collections

DECK = Path(__file__).parents[1] / "fixtures" / "krishimitra_deck.pdf"


def _services_available() -> str | None:
    from aura.core.config import get_settings

    settings = get_settings()
    if not settings.llm_base_url or not settings.llm_api_key.get_secret_value():
        return "LLM gateway not configured"
    try:
        key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else ""
        httpx.get(f"{settings.qdrant_url}/healthz", headers={"api-key": key}, timeout=2).raise_for_status()
    except httpx.HTTPError:
        return "Qdrant not reachable"
    return None


def read_sse(response) -> list[dict]:
    events, current = [], {}
    for line in response.iter_lines():
        if line.startswith("event: "):
            current["event"] = line.removeprefix("event: ")
        elif line.startswith("data: "):
            current["data"] = json.loads(line.removeprefix("data: "))["data"]
        elif line == "" and current:
            events.append(current)
            current = {}
    return events


def upload(client, startup_id: str, path: Path, filename: str | None = None):
    with path.open("rb") as fh:
        return client.post(f"/api/startups/{startup_id}/documents",
                           files={"file": (filename or path.name, fh, "application/octet-stream")},
                           data={"kind": "deck"})


@pytest.fixture(scope="module")
def live():
    from aura.core.config import get_settings

    get_settings.cache_clear()
    reason = _services_available()
    if reason:
        pytest.skip(reason)
    mp = pytest.MonkeyPatch()
    data_dir = TEST_ROOT / uuid.uuid4().hex
    prefix = "t" + uuid.uuid4().hex[:10]
    for key, value in {
        "DATA_DIR": str(data_dir), "CACHE_DIR": str(BACKEND_DIR / "data" / "cache"), "QDRANT_PREFIX": prefix,
        "OCR_AUTOSTART": "false", "SESSION_SECRET": "test-secret-" + "x" * 40, "APP_ENV": "test", "DEMO_MODE": "true",
    }.items():
        mp.setenv(key, value)
    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from aura.api.app import create_app

    try:
        with TestClient(create_app(), headers={"X-Aura-CSRF": "1"}) as client:
            reg = {"email": "founder@krishimitra.test", "password": "correct-horse-battery", "name": "Arav",
                   "role": "startup", "startup_name": "KrishiMitra AI"}
            assert client.post("/api/auth/register", json=reg).status_code == 201
            startup_id = client.get("/api/me").json()["startup"]["id"]
            response = upload(client, startup_id, DECK)
            assert response.status_code == 202, response.text
            accepted = response.json()
            with client.stream("GET", accepted["events_url"]) as stream:
                events = read_sse(stream)
            yield SimpleNamespace(client=client, startup_id=startup_id, founder=reg, events=events, **accepted)
    finally:
        _drop_qdrant_collections(prefix)
        get_settings.cache_clear()
        mp.undo()
        shutil.rmtree(data_dir, ignore_errors=True)
