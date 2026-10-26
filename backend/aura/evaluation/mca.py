"""Company-registry checks against India's Ministry of Corporate Affairs (MCA) data.

Lookup order: a real provider (when ``MCA_API_KEY`` is set), then the fixture registry built from the seed
specs (``registry_fixtures``), then a clearly labelled sandbox record for unknown but well-formed CINs (so
demo founders are not blocked). Malformed CINs are never "verified".
"""

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from aura.core import clock
from aura.core.config import get_settings

logger = logging.getLogger("aura.mca")

# L/U + 5 digits (industry) + 2 letters (state) + 4 digits (year) + 3 letters (type) + 6 digits
CIN_PATTERN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")

_STATES = {
    "MH": "Maharashtra", "KA": "Karnataka", "DL": "Delhi", "TN": "Tamil Nadu", "TG": "Telangana",
    "GJ": "Gujarat", "HR": "Haryana", "UP": "Uttar Pradesh", "WB": "West Bengal", "RJ": "Rajasthan",
    "KL": "Kerala", "AP": "Andhra Pradesh", "PB": "Punjab", "MP": "Madhya Pradesh",
}

# CIN -> registry record, filled by the seeder from seed/specs (status, registered_name, directors, ...).
registry_fixtures: dict[str, dict[str, Any]] = {}


def normalise_cin(cin: str) -> str:
    return re.sub(r"\s+", "", cin or "").upper()


def is_valid_cin(cin: str) -> bool:
    return bool(CIN_PATTERN.match(normalise_cin(cin)))


def _normalise_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    name = re.sub(r"\b(private|pvt|limited|ltd|llp|inc|corp|corporation|company|co|the)\b", " ", name)
    return " ".join(name.split())


def names_match(a: str, b: str) -> bool:
    na, nb = _normalise_name(a), _normalise_name(b)
    return bool(na and nb) and (na == nb or na in nb or nb in na)


def _provider_lookup(cin: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.mca_api_key:
        return None
    try:
        response = httpx.post(
            settings.mca_api_url,
            json={"id": cin, "consent": "Y"},
            headers={"x-karza-key": settings.mca_api_key.get_secret_value()},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json().get("result") or {}
        return {
            "status": str(data.get("companyStatus") or data.get("status") or "").upper() or None,
            "registered_name": data.get("companyName"),
            "directors": [d.get("name") for d in data.get("directors", []) if d.get("name")],
            "incorporation_year": str(data.get("dateOfIncorporation", ""))[:4] or None,
            "state": data.get("state"),
            "source": "provider",
        }
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("MCA provider lookup failed for %s: %s", cin, exc)
        return None


def load_registry_fixtures(specs_dir: Path) -> int:
    """Demo registry: the MCA record each seed spec declares (active, struck off, renamed, ...)."""
    from aura.decks.spec import load_specs

    loaded = 0
    for spec in load_specs(specs_dir):
        if spec.mca.registry is not None:
            registry_fixtures[normalise_cin(spec.mca.cin)] = spec.mca.registry.model_dump()
            loaded += 1
    return loaded


def verify(cin: str | None, *, legal_name: str, claimed_directors: list[str] | None = None) -> dict[str, Any]:
    """Return a verification record for a startup's CIN."""
    record: dict[str, Any] = {"cin": normalise_cin(cin or "") or None, "last_checked": clock.iso(clock.now())}
    if not record["cin"]:
        return record | {"mca_verified": False, "company_status": None, "source": None, "reason": "no CIN supplied"}
    if not is_valid_cin(record["cin"]):
        return record | {"mca_verified": False, "company_status": None, "source": None, "reason": "malformed CIN"}
    found = _provider_lookup(record["cin"])
    if found is None and record["cin"] in registry_fixtures:
        found = dict(registry_fixtures[record["cin"]]) | {"source": "registry_fixture"}
    if found is None:
        found = {
            "status": "ACTIVE",
            "registered_name": legal_name.upper(),
            "directors": list(claimed_directors or []),
            "incorporation_year": record["cin"][8:12],
            "state": _STATES.get(record["cin"][6:8]),
            "source": "sandbox",
        }
    return record | {
        "mca_verified": found.get("status") == "ACTIVE",
        "company_status": found.get("status"),
        "company_name": found.get("registered_name"),
        "directors": found.get("directors") or [],
        "incorporation_year": found.get("incorporation_year"),
        "state": found.get("state"),
        "source": found.get("source"),
    }


def consistency_flags(verification: dict[str, Any], *, legal_name: str) -> list[str]:
    """Flags raised when the registry does not back up the startup's claims."""
    cin = verification.get("cin")
    if not cin:
        return ["MCA_NOT_VERIFIED"]
    if not is_valid_cin(cin):
        return ["INVALID_CIN_FORMAT"]
    flags: list[str] = []
    status = (verification.get("company_status") or "").upper()
    if status and status != "ACTIVE":
        flags.append(f"COMPANY_STATUS_{status}")
    if verification.get("company_name") and not names_match(verification["company_name"], legal_name):
        flags.append("NAME_MISMATCH")
    if not verification.get("directors"):
        flags.append("NO_DIRECTORS_FOUND")
    if verification.get("source") == "sandbox":
        flags.append("SANDBOX_REGISTRY")
    return flags


# Flags that block opening a funding round; informational flags only appear as chips.
BLOCKING_FLAGS = {"INVALID_CIN_FORMAT", "MCA_NOT_VERIFIED", "NAME_MISMATCH"} | {
    f"COMPANY_STATUS_{s}" for s in ("STRUCK_OFF", "UNDER_LIQUIDATION", "DORMANT")
}
INFO_FLAGS = {"SANDBOX_REGISTRY", "NO_DIRECTORS_FOUND", "DECK_HIDDEN_INSTRUCTIONS", "OCR_REVIEW_REQUIRED"}
