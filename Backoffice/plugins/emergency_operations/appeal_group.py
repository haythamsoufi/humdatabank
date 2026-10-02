"""IFRC GO appealgroupchild feed.

This catalogue includes standalone appeals and the country-level children of a
grouped appeal. Subtype labels are mapped onto the Emergency Appeal / DREF
names the form already filters on.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

APPEAL_GROUP_URL = "https://go-api.ifrc.org/api/appealgroupchild"
LEGACY_APPEAL_URL = "https://goadmin.ifrc.org/api/v2/appeal/"
LEGACY_APPEAL_URL_MARKER = "goadmin.ifrc.org/api/v2/appeal"
CACHE_SOURCE = "appealgroupchild"
DEFAULT_FEED_ID = "appeal_group"

# Settings may only choose one of these. URLs are not free text.
APPEAL_FEEDS = {
    "appeal_group": {
        "label": "Appeal group (current)",
        "url": APPEAL_GROUP_URL,
    },
    "go_legacy": {
        "label": "GO appeals (legacy)",
        "url": LEGACY_APPEAL_URL,
    },
}

# Subtype on appealgroupchild, compared with atype_display on the legacy appeal API.
SUBTYPE_TO_APPEAL_TYPE = {
    "emergency": "Emergency Appeal",
    "minor emergency": "DREF",
}


def effective_feed_id(api: Optional[dict]) -> str:
    """Resolve the selected feed. A saved legacy URL with no explicit choice stays on appeal group."""
    api = api or {}
    feed = str(api.get("feed") or "").strip()
    if feed in APPEAL_FEEDS:
        return feed
    url = str(api.get("base_url") or "").strip().rstrip("/")
    if url == APPEAL_GROUP_URL.rstrip("/"):
        return "appeal_group"
    return DEFAULT_FEED_ID


def url_for_feed(feed_id: Optional[str]) -> str:
    spec = APPEAL_FEEDS.get(str(feed_id or "").strip())
    if not spec:
        spec = APPEAL_FEEDS[DEFAULT_FEED_ID]
    return spec["url"]


def resolve_appeals_url(configured: Optional[str]) -> str:
    """Map a stored URL or feed id onto one of the hardcoded feeds."""
    text = (configured or "").strip()
    if text in APPEAL_FEEDS:
        return url_for_feed(text)
    return url_for_feed(effective_feed_id({"base_url": text}))


def map_subtype_to_appeal_type(subtype: Optional[str]) -> str:
    label = (subtype or "").strip()
    mapped = SUBTYPE_TO_APPEAL_TYPE.get(label.casefold())
    return mapped if mapped else (label or "Unknown Type")


_PART_OF_LABEL_RE = re.compile(r"^(.*?)\s+\(part of ([A-Za-z0-9]+)\)\s*$", re.IGNORECASE)
_CODE_FIRST_LABEL_RE = re.compile(r"^([A-Z][A-Z0-9]{4,})\s+(.+)$")
_NAME_FIRST_LABEL_RE = re.compile(r"^(.+?)\s+\(([A-Z][A-Z0-9]{4,})\)\s*$")


def parse_operation_label(value: Optional[str]) -> Dict[str, str]:
    """Read a dropdown label back into name and appeal code.

    Accepts ``CODE Name (part of PARENT)`` and the older ``Name (CODE)`` form.
    """
    text = (value or "").strip()
    if not text:
        return {"name": "", "code": "", "part_of": ""}
    parent = ""
    body = text
    part_match = _PART_OF_LABEL_RE.match(text)
    if part_match:
        body = part_match.group(1).strip()
        parent = part_match.group(2).strip().upper()
    code_first = _CODE_FIRST_LABEL_RE.match(body)
    if code_first:
        return {"name": code_first.group(2).strip(), "code": code_first.group(1).strip(), "part_of": parent}
    name_first = _NAME_FIRST_LABEL_RE.match(body)
    if name_first:
        return {"name": name_first.group(1).strip(), "code": name_first.group(2).strip(), "part_of": parent}
    return {"name": text, "code": "", "part_of": parent}


def format_operation_label(name: Optional[str], code: Optional[str], part_of: Optional[str] = None) -> str:
    """Dropdown label: ``CODE Name``, plus ``(part of PARENT)`` for a child appeal."""
    appeal_name = (name or "").strip()
    appeal_code = (code or "").strip()
    parent = (part_of or "").strip()
    if parent and appeal_code and parent.upper() == appeal_code.upper():
        parent = ""
    if appeal_code and appeal_name:
        label = f"{appeal_code} {appeal_name}"
    else:
        label = appeal_code or appeal_name
    if parent and label:
        label = f"{label} (part of {parent})"
    return label


def _basic_auth():
    from requests.auth import HTTPBasicAuth

    user = (os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME") or "").strip()
    password = (os.environ.get("IFRC_API_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError(
            "IFRC API credentials are not configured (IFRC_API_USER / IFRC_API_PASSWORD)"
        )
    return HTTPBasicAuth(user, password)


def normalize_appeal_group_row(row: dict) -> dict:
    """Shape one appealgroupchild row like the legacy GO appeal objects the UI reads."""
    subtype = (row.get("Subtype") or "").strip()
    original = (row.get("Original_Subtype") or "").strip()
    geo = (row.get("Geographical_Code") or "").strip().upper()
    code = (row.get("Appeal_Id") or "").strip().upper()
    country = None
    if geo:
        country = {"iso": geo, "iso3": "", "name": geo}
    return {
        "code": code,
        "name": (row.get("Appeal_Name") or "").strip(),
        "status": (row.get("Status") or "").strip(),
        "status_display": (row.get("Status") or "").strip(),
        "atype_display": map_subtype_to_appeal_type(subtype),
        "appeal_subtype": subtype,
        "original_subtype": original,
        "start_date": row.get("Start_Date"),
        "end_date": row.get("End_Date"),
        "country": country,
        "countries": None,
        "part_of": (row.get("Part_of") or "").strip().upper(),
        "group_appeal_name": (row.get("Group_Appeal_Name") or "").strip(),
        "group_geographical_code": (row.get("Group_Geographical_Code") or "").strip().upper(),
        "disaster_type": (row.get("Disaster_Type") or "").strip(),
        "amount_requested": None,
        "amount_funded": None,
        "num_beneficiaries": None,
        "event": None,
    }


def fetch_appeal_group_records(api_url: str, timeout: int = 60) -> List[Dict]:
    """Download the appealgroupchild catalogue and return normalized rows."""
    import requests

    response = requests.get(
        api_url,
        auth=_basic_auth(),
        headers={"Accept": "application/json", "User-Agent": "IFRC-Network-Databank/1.0"},
        timeout=max(int(timeout or 60), 60),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("value") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    normalized = [normalize_appeal_group_row(row) for row in rows if isinstance(row, dict)]
    return [row for row in normalized if row.get("code")]
