"""Tiny JSON-file persistence so startups, analyses and chat sessions survive restarts."""

import json
import logging
import os
import threading
from typing import Any, Dict

from aura.config import DATA_DIR

logger = logging.getLogger("aura.store")

_STORE_PATH = DATA_DIR / "store.json"
_lock = threading.RLock()

startups_db: Dict[str, Dict[str, Any]] = {}
analysis_results: Dict[str, Dict[str, Any]] = {}
finscope_sessions: Dict[str, Dict[str, Any]] = {}


def load() -> None:
    if not _STORE_PATH.exists():
        return
    try:
        data = json.loads(_STORE_PATH.read_text())
    except Exception as e:
        logger.error(f"Could not read {_STORE_PATH}: {e}")
        return
    with _lock:
        startups_db.update(data.get("startups", {}))
        analysis_results.update(data.get("analyses", {}))
        finscope_sessions.update(data.get("sessions", {}))
        # An analysis that was running when the server stopped will never finish.
        for record in analysis_results.values():
            if record.get("status") == "processing":
                record["status"] = "failed"
                record["error"] = "Server restarted during analysis. Please run it again."
    logger.info(f"Loaded {len(startups_db)} startups and {len(analysis_results)} analyses from disk")


def save() -> None:
    with _lock:
        payload = json.dumps(
            {"startups": startups_db, "analyses": analysis_results, "sessions": finscope_sessions},
            default=str,
        )
        tmp_path = _STORE_PATH.with_suffix(".tmp")
        tmp_path.write_text(payload)
        os.replace(tmp_path, _STORE_PATH)
