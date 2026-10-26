"""Run Alembic migrations programmatically (app startup, tests, seeder)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from aura.core.config import BACKEND_DIR, get_settings


def upgrade(database_url: str | None = None) -> None:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")
