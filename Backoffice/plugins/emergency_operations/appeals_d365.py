"""Helpers for IFRC GO AppealsD365 API payloads (Fabric/ERP feed).

See ``Backoffice/tests/unit/test_plugins/test_appeals_d365_api.py`` for probe results
against the live endpoint and fixture-backed behaviour tests.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

# Observed on live API (Aug 2026): GEC_code can be ISO2 country tokens *or* regional
# cluster codes (e.g. CAR, EUR). Country-level filtering needs a mapping table for regions.
_REGION_GEC_CODES = frozenset(
    {
        "AFR",
        "AME",
        "APC",
        "ASI",
        "CAR",
        "EUR",
        "MENA",
    }
)


def parse_gec_code(raw: Optional[str]) -> List[str]:
    """Split ``GEC_code`` into non-empty tokens (semicolon-separated)."""
    if not raw:
        return []
    return [part.strip().upper() for part in str(raw).split(";") if part and part.strip()]


def is_region_gec_token(token: str) -> bool:
    token = (token or "").strip().upper()
    if not token:
        return False
    if token in _REGION_GEC_CODES:
        return True
    # Heuristic: 3-letter non-numeric tokens that are not ISO2 country codes we treat as region-ish.
    return len(token) == 3 and token.isalpha() and token not in _KNOWN_ISO2


def appeal_matches_country_iso(record: dict, iso: str) -> bool:
    """Return True when ``iso`` (ISO2 or ISO3) matches a GEC token on the appeal."""
    iso = (iso or "").strip().upper()
    if not iso or not record:
        return False
    tokens = parse_gec_code(record.get("GEC_code"))
    if not tokens:
        return False
    if len(iso) == 2:
        return iso in tokens
    if len(iso) == 3:
        return iso in tokens or (_ISO3_TO_ISO2.get(iso) in tokens)
    return iso in tokens


def classify_gec_tokens(tokens: Iterable[str]) -> dict:
    """Split GEC tokens into likely country vs region buckets (best-effort)."""
    countries: Set[str] = set()
    regions: Set[str] = set()
    for token in tokens:
        t = (token or "").strip().upper()
        if not t:
            continue
        if is_region_gec_token(t):
            regions.add(t)
        elif len(t) == 2 and t.isalpha():
            countries.add(t)
        else:
            regions.add(t)
    return {"countries": sorted(countries), "regions": sorted(regions)}


def normalize_appeal_record(raw: dict) -> dict:
    """Return a stable subset of AppealsD365 fields for list/display use."""
    code = (raw.get("APP_code") or raw.get("code") or "").strip()
    name = (raw.get("APP_name") or raw.get("name") or "").strip()
    return {
        "code": code,
        "name": name,
        "label": f"{name} ({code})" if code else name,
        "status": (raw.get("APP_status") or "").strip(),
        "start_date": (raw.get("APP_startDate") or "")[:10] or None,
        "end_date": (raw.get("APP_endDate") or "")[:10] or None,
        "source": (raw.get("source") or "").strip(),
        "gec_code": (raw.get("GEC_code") or "").strip(),
        "gec_tokens": parse_gec_code(raw.get("GEC_code")),
        "disaster_name": (raw.get("APP_DisasterCategorisationName") or "").strip(),
        "disaster_numeric": raw.get("APP_DisasterCategorisationNumeric"),
        "details_count": len(raw.get("Details") or []),
    }


# Minimal ISO3→ISO2 map for probe fixtures (extend when integrating fully).
_ISO3_TO_ISO2 = {
    "JAM": "JM",
    "TTO": "TT",
    "UKR": "UA",
    "HUN": "HU",
    "COD": "CD",
    "UGA": "UG",
    "MMR": "MM",
    "NGA": "NG",
}

_KNOWN_ISO2 = set(_ISO3_TO_ISO2.values())

MDR_CODE_RE = re.compile(r"^MDR[A-Z0-9]+$", re.IGNORECASE)
MGR_CODE_RE = re.compile(r"^MGR[A-Z0-9]+$", re.IGNORECASE)


def is_emergency_appeal_code(code: Optional[str]) -> bool:
    code = (code or "").strip().upper()
    return bool(MDR_CODE_RE.match(code) or MGR_CODE_RE.match(code))
