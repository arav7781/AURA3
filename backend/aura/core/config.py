"""Application settings, read from the environment and ``backend/.env``.

LLM credentials are validated lazily (``require_llm``) so migrations, tests and the seeder can import
the package without a gateway configured.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import truststore
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Verify TLS against the OS trust store (the gateway sits behind TLS inspection).
truststore.inject_into_ssl()

BACKEND_DIR = Path(__file__).resolve().parents[2]


class LLMNotConfigured(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    demo_mode: bool = True

    # LLM gateway (OpenAI-compatible)
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    model_agent: str = "azure/deepSeek-V4-Flash"
    model_util: str = "gpt-4o-mini"
    model_judge: str = "gpt-5-nano"
    embed_model: str = "text-embedding-3-large"
    embed_dims: int = 1024
    llm_timeout_s: float = 120.0
    llm_concurrency: int = 6

    # Storage
    data_dir: Path = Path("data")
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_prefix: str = "aura"  # collection name prefix; tests use a throwaway prefix

    # Security
    session_secret: SecretStr = SecretStr("")
    session_days: int = 7
    cookie_secure: bool = False
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # OCR and sandbox
    ocr_workers: int = 2
    ocr_max_docs: int = 2
    ocr_autostart: bool = True  # start TitanOCR at boot (tests start it lazily on first ingestion)
    ocr_models_dir: Path | None = None
    docker_host: str = "unix:///var/run/docker.sock"
    sandbox_image: str = "aura-sandbox:1"
    sandbox_max_concurrent: int = 2

    # Optional integrations
    rapidapi_key: SecretStr | None = None
    mca_api_key: SecretStr | None = None
    mca_api_url: str = "https://api.karza.in/v3/company-master"

    @field_validator("data_dir", mode="before")
    @classmethod
    def _clean_data_dir(cls, value: object) -> Path:
        # An earlier .env used DATA_DIR=data\ which created a folder literally named "data\".
        raw = str(value or "data").strip().rstrip("\\/") or "data"
        path = Path(raw).expanduser()
        return (path if path.is_absolute() else BACKEND_DIR / path).resolve()

    cache_dir: Path | None = None  # embeddings cache + local models; defaults to <data_dir>/cache

    @property
    def cache_path(self) -> Path:
        return (self.cache_dir or self.data_dir / "cache").expanduser().resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'aura.db'}"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"

    def require_llm(self) -> None:
        if not self.llm_base_url or not self.llm_api_key.get_secret_value():
            raise LLMNotConfigured("LLM_BASE_URL and LLM_API_KEY must be set in backend/.env")

    def require_session_secret(self) -> str:
        secret = self.session_secret.get_secret_value()
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must be set (32+ chars) in backend/.env — run `make init`")
        return secret


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
