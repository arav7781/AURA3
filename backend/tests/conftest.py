"""Shared fixtures: every test that touches the database gets its own temporary data directory."""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest

from aura.core.config import Settings


@pytest.fixture
def app_env(tmp_path, monkeypatch) -> Iterator[Settings]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
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
        get_settings.cache_clear()


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
