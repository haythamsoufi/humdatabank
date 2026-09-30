"""Unified Plan / UPL document identity helpers.

Title year, MAA-code country, and document-type classification live here so
core ingest and search only call the plugin.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# "UPL-2024-...", "Country 2025 Unified Plan (UPL-2025-...)"
_UPL_YEAR_RE = re.compile(r"UPL-(\d{4})|(\d{4})\s+Unified\s+Plan", re.IGNORECASE)

# UPL codes often embed ISO2 after "MAA", e.g. UPL-2025-MAASS001 -> ISO2 "SS"
_UPL_MAA_ISO2_RE = re.compile(r"\bUPL-\d{4}-MAA([A-Z]{2})[A-Z0-9]*\b", re.IGNORECASE)

_UNIFIED_PLAN_TYPE_RE = re.compile(r"\bunified\s+plan|\bupl\b|\bupr\b", re.IGNORECASE)


def extract_upl_year_from_title(title: str) -> Optional[int]:
    """Extract the plan year from a Unified Plan (UPL) document title.

    Matches patterns such as:
    - "Vietnam 2024 Unified Plan (UPL-2024-MAAVN002)"
    - "Estonia 2025 Unified Plan (UPL-2025-MAAEE001)"
    - "UPL_SYRIA_2023 (UPL-2023-MAASY002)"

    Returns the four-digit year as int, or None if no year is found.
    """
    if not title or not isinstance(title, str):
        return None
    m = _UPL_YEAR_RE.search(title)
    if not m:
        return None
    for g in m.groups():
        if g:
            y = int(g)
            if 2000 <= y <= 2100:
                return y
    return None


def detect_country_from_upl_code(*sources: str | None) -> tuple[int, str] | None:
    """Detect country from a UPL code that includes ISO2 after "MAA".

    Example: "UPL-2025-MAASS001" -> ISO2 "SS" -> South Sudan.
    """
    try:
        from app.models import Country

        for src in sources:
            t = (src or "").strip()
            if not t:
                continue
            m = _UPL_MAA_ISO2_RE.search(t)
            if not m:
                continue
            iso2 = (m.group(1) or "").strip().upper()
            if not iso2:
                continue
            c = Country.query.filter(Country.iso2 == iso2).first()
            if c and getattr(c, "id", None) and getattr(c, "name", None):
                return int(c.id), str(c.name)
    except Exception as e:
        logger.debug("UPL/MAA ISO2 heuristic failed: %s", e)
        return None
    return None


def upr_document_type_key(combined_text: str) -> str | None:
    """Return ``unified_plan`` when title/filename/category looks like a UPL/UPR document."""
    if not combined_text:
        return None
    if _UNIFIED_PLAN_TYPE_RE.search(combined_text):
        return "unified_plan"
    return None
