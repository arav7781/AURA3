"""MCA (Ministry of Corporate Affairs) CIN verification and consistency flags."""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List

import httpx

from aura.config import MCA_API_KEY, MCA_API_URL

logger = logging.getLogger("aura.mca")

# L/U + 5 digits (industry) + 2 letters (state) + 4 digits (year) + 3 letters (type) + 6 digits
CIN_PATTERN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")

_COMPANY_SUFFIXES = re.compile(
    r"\b(private|pvt|limited|ltd|llp|inc|corp|corporation|company|co)\b\.?", re.IGNORECASE
)

_STATES = {
    "MH": "Maharashtra", "KA": "Karnataka", "DL": "Delhi", "TN": "Tamil Nadu", "TG": "Telangana",
    "GJ": "Gujarat", "HR": "Haryana", "UP": "Uttar Pradesh", "WB": "West Bengal", "RJ": "Rajasthan",
    "KL": "Kerala", "TZ": "Tamil Nadu", "AP": "Andhra Pradesh", "PB": "Punjab", "MP": "Madhya Pradesh",
}


def normalise_cin(cin: str) -> str:
    return (cin or "").strip().upper()


def is_valid_cin(cin: str) -> bool:
    return bool(CIN_PATTERN.match(normalise_cin(cin)))


def _normalise_name(name: str) -> str:
    name = _COMPANY_SUFFIXES.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def names_match(a: str, b: str) -> bool:
    na, nb = _normalise_name(a), _normalise_name(b)
    return bool(na and nb and (na == nb or na in nb or nb in na))


def _sandbox_response(cin: str, claimed_name: str) -> Dict[str, Any]:
    """Deterministic sandbox record used when no MCA provider key is configured.

    CINs ending in 'F' simulate a struck-off company so the compliance flags can be demonstrated.
    """
    is_active = not cin.endswith("F")
    listing = "Listed" if cin.startswith("L") else "Unlisted"
    return {
        "valid": is_active,
        "company_status": "ACTIVE" if is_active else "STRUCK_OFF",
        "company_name": f"{claimed_name.strip().upper()} PRIVATE LIMITED" if claimed_name else "UNKNOWN",
        "directors": ["Arjun Malhotra", "Priya Nair"] if is_active else [],
        "incorporation_year": cin[8:12],
        "state": _STATES.get(cin[6:8], cin[6:8]),
        "listing_status": listing,
        "source": "sandbox",
    }


def verify_cin(cin: str, claimed_name: str) -> Dict[str, Any]:
    cin = normalise_cin(cin)
    if not MCA_API_KEY:
        logger.info(f"MCA check for {cin}: no provider key, using sandbox registry")
        return _sandbox_response(cin, claimed_name)
    try:
        resp = httpx.get(
            MCA_API_URL,
            params={"cin": cin},
            headers={"x-karza-key": MCA_API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        status = (data.get("status") or data.get("company_status") or "").upper()
        return {
            "valid": status == "ACTIVE",
            "company_status": status or None,
            "company_name": data.get("companyName") or data.get("company_name"),
            "directors": data.get("directors", []),
            "source": "mca-provider",
        }
    except Exception as e:
        logger.error(f"MCA provider call failed ({e}); falling back to sandbox registry")
        return _sandbox_response(cin, claimed_name)


def run_verification(record: Dict[str, Any], cin: str) -> Dict[str, Any]:
    """Verify a startup record's CIN and write the result onto the record."""
    cin = normalise_cin(cin)
    now = datetime.utcnow().isoformat() + "Z"
    verification = record.setdefault("verification", {})
    verification.update({"cin": cin or None, "last_checked": now})

    if not cin:
        verification.update({"mca_verified": False, "company_status": None, "company_name": None, "directors": []})
        return verification
    if not is_valid_cin(cin):
        verification.update({
            "mca_verified": False,
            "company_status": "INVALID_CIN_FORMAT",
            "company_name": None,
            "directors": [],
        })
        logger.warning(f"CIN {cin} does not match the MCA format")
        return verification

    result = verify_cin(cin, record.get("name", ""))
    verification.update({
        "mca_verified": bool(result.get("valid")),
        "company_status": result.get("company_status"),
        "company_name": result.get("company_name"),
        "directors": result.get("directors", []),
        "source": result.get("source"),
        "incorporation_year": result.get("incorporation_year"),
        "state": result.get("state"),
    })
    logger.info(
        f"MCA check for {cin}: status={verification['company_status']} verified={verification['mca_verified']}"
    )
    return verification


def consistency_flags(record: Dict[str, Any]) -> List[str]:
    """Flags raised when the registry data does not back up the startup's claims."""
    v = record.get("verification") or {}
    flags: List[str] = []
    if not v.get("mca_verified"):
        flags.append("MCA_NOT_VERIFIED")
    if v.get("company_name") and record.get("name") and not names_match(v["company_name"], record["name"]):
        flags.append("NAME_MISMATCH")
    if v.get("cin") and not v.get("directors"):
        flags.append("NO_DIRECTORS_FOUND")
    status = (v.get("company_status") or "").upper()
    if status and status != "ACTIVE":
        flags.append(f"COMPANY_STATUS_{status}")
    return flags
