import os
from pathlib import Path

import truststore
from dotenv import load_dotenv

# Verify TLS against the OS trust store (works behind corporate TLS-inspecting proxies).
truststore.inject_into_ssl()

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ─── LLM gateway (OpenAI-compatible) ──────────────────────────────────────────
LLM_BASE_URL    = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY     = os.getenv("LLM_API_KEY", "")
CHAT_MODEL      = os.getenv("CHAT_MODEL", "azure/deepSeek-V4-Flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

# ─── Optional integrations ────────────────────────────────────────────────────
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
MCA_API_KEY  = os.getenv("MCA_API_KEY", "")
MCA_API_URL  = os.getenv("MCA_API_URL", "https://api.karza.in/v3/company-master")

# ─── Service ──────────────────────────────────────────────────────────────────
PORT            = int(os.getenv("PORT", "8010"))
DATA_DIR        = (ROOT_DIR / os.getenv("DATA_DIR", "data")).resolve()
DOCLING_ENABLED = os.getenv("DOCLING_ENABLED", "true").lower() in ("1", "true", "yes")
CORS_ORIGINS    = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

DATA_DIR.mkdir(parents=True, exist_ok=True)

if not LLM_BASE_URL or not LLM_API_KEY:
    raise RuntimeError("LLM_BASE_URL and LLM_API_KEY must be set (see .env)")
