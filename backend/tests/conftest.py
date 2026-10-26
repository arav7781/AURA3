"""Shared fixtures.

Every test that touches the database gets its own data directory (under $HOME, because Colima can only
mount paths there into sandbox containers) and its own throwaway Qdrant collection prefix. The embedding
cache and local retrieval models are shared with the dev environment (content-addressed, safe to share).
"""

import shutil
import uuid
import warnings
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from aura.core.config import BACKEND_DIR, Settings

TEST_ROOT = Path.home() / ".cache" / "aura-tests"


def _drop_qdrant_collections(prefix: str) -> None:
    try:
        from qdrant_client import QdrantClient

        from aura.core.config import get_settings

        settings = get_settings()
        key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        warnings.filterwarnings("ignore", message="Api key is used with an insecure connection")
        with QdrantClient(url=settings.qdrant_url, api_key=key, timeout=5) as qc:
            for collection in qc.get_collections().collections:  # aliases go with their collection
                if collection.name.startswith(prefix + "_"):
                    qc.delete_collection(collection.name)
    except Exception:  # Qdrant not running: nothing was created
        pass


@pytest.fixture
def app_env(monkeypatch) -> Iterator[Settings]:
    data_dir = TEST_ROOT / uuid.uuid4().hex
    prefix = "t" + uuid.uuid4().hex[:10]
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CACHE_DIR", str(BACKEND_DIR / "data" / "cache"))
    monkeypatch.setenv("QDRANT_PREFIX", prefix)
    monkeypatch.setenv("OCR_AUTOSTART", "false")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    from aura.core import clock, db, migrate
    from aura.core.config import get_settings

    get_settings.cache_clear()
    clock.unfreeze()
    clock.set_offset(timedelta(0))
    migrate.upgrade()
    db.init_engines()
    try:
        yield get_settings()
    finally:
        db.dispose_engines()
        clock.unfreeze()
        clock.set_offset(timedelta(0))
        _drop_qdrant_collections(prefix)
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient

    from aura.api.app import create_app

    with TestClient(create_app(), base_url="http://testserver", headers={"X-Aura-CSRF": "1"}) as test_client:
        yield test_client


def register(client, *, role: str = "investor", plan: str = "scout", email: str | None = None, **extra):
    body = {
        "email": email or f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        "password": "correct-horse-battery",
        "name": extra.pop("name", "Test User"),
        "role": role,
        "plan": plan,
        **extra,
    }
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201, response.text
    return body, response.json()


def idem() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}
