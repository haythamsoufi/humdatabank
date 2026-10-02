"""Country MAA codes for Unified Plan and Report cover pages.

Emergency Operations downloads the IFRC appealgroupchild catalogue for emergency
and DREF codes. The same rows include each country's annual appeal (``MAA`` +
ISO2 + sequence). The sequence is not always ``001`` — Syria's current code is
``MAASY002``, for example — so the visuals cover reads it from that feed
instead of printing a fixed suffix.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from plugins.upr.formatters import appeal_number

logger = logging.getLogger(__name__)

# Country annual appeals embed ISO2. Regional codes such as MAA65001 do not.
_MAA_COUNTRY_RE = re.compile(r"^MAA([A-Z]{2})(\d{3})$")
_ACTIVE_STATUS = {"active", "open", "ongoing"}
_LIVE_TTL_SECONDS = 60 * 60
_REFRESH_CHECK_SECONDS = 5 * 60

_live_lock = threading.Lock()
_live_rows: list[dict] | None = None
_live_loaded_at = 0.0
_refresh_checked_at = 0.0
_catalogue_warned = False


def appeal_code_for_cover(meta: dict | None) -> str:
    """Appeal number printed on the visuals cover."""
    meta = meta or {}
    explicit = str(meta.get("appeal_code") or "").strip().upper()
    if explicit.startswith("MAA") and explicit.isalnum():
        return explicit
    return appeal_number(meta.get("iso2") or meta.get("appeal_iso2"))


def resolve_appeal_number(
    iso2: str | None,
    *,
    year: Any = None,
    records: list[dict] | None = None,
) -> str:
    """MAA code for a country, from appealgroupchild when that catalogue is available.

    ``records`` injects catalogue rows (tests). Otherwise the shared Emergency
    Operations cache is used, then a live appealgroupchild fetch. The static
    ``MAA`` + ISO2 + ``001`` pattern is only the fallback when the feed has no
    row for the country or cannot be read.
    """
    catalogue = records if records is not None else load_appeal_catalogue()
    if catalogue:
        found = choose_maa_code(catalogue, iso2, year=year)
        if found:
            return found
    return appeal_number(iso2)


def choose_maa_code(records: list[dict] | None, iso2: str | None, *, year: Any = None) -> str:
    """Pick the country MAA code that best matches the document year."""
    iso = (iso2 or "").strip().upper()
    if len(iso) != 2 or not iso.isalpha():
        return ""
    document_year = _as_year(year)
    best_key: tuple | None = None
    best_code = ""
    for row in records or []:
        if not isinstance(row, dict):
            continue
        code = _row_code(row)
        match = _MAA_COUNTRY_RE.match(code)
        if not match or match.group(1) != iso:
            continue
        geo = _row_iso(row)
        if len(geo) == 2 and geo != iso:
            continue
        start = _row_day(row, "start_date", "Start_Date")
        end = _row_day(row, "end_date", "End_Date")
        key = (
            1 if _covers(start, end, document_year) else 0,
            1 if _is_active(_row_status(row)) else 0,
            int(match.group(2)),
            end,
            start,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_code = code
    return best_code


def load_appeal_catalogue() -> list[dict] | None:
    """Appealgroupchild rows, or None when the feed cannot be read.

    An empty list means the catalogue was read and contained no rows.
    """
    cached = _emops_appeal_rows()
    if cached is not None:
        _schedule_refresh_once()
        return cached
    return _live_appeal_rows()


def _emops_appeal_rows() -> list[dict] | None:
    try:
        from plugins.emergency_operations.appeal_group import CACHE_SOURCE
        from plugins.emergency_operations.data_store import get_data_store

        data = get_data_store().load_cached()
    except Exception:
        logger.debug("UPR MAA codes: emergency operations cache unreadable", exc_info=True)
        return None
    if not isinstance(data, dict) or data.get("source") != CACHE_SOURCE:
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None
    return results


def _live_appeal_rows() -> list[dict] | None:
    global _live_rows, _live_loaded_at, _catalogue_warned
    now = time.monotonic()
    with _live_lock:
        if _live_rows is not None and (now - _live_loaded_at) < _LIVE_TTL_SECONDS:
            return _live_rows
    try:
        from plugins.emergency_operations.appeal_group import (
            APPEAL_GROUP_URL,
            fetch_appeal_group_records,
        )

        rows = fetch_appeal_group_records(APPEAL_GROUP_URL, timeout=60)
    except Exception as exc:
        if not _catalogue_warned:
            _catalogue_warned = True
            logger.warning(
                "UPR MAA codes: appealgroupchild catalogue unavailable (%s); "
                "cover pages use the static MAA appeal number",
                exc,
            )
        return None
    if not isinstance(rows, list):
        return None
    _store_catalogue_if_cache_empty(rows)
    with _live_lock:
        _live_rows = rows
        _live_loaded_at = time.monotonic()
    return rows


def _store_catalogue_if_cache_empty(rows: list[dict]) -> None:
    """Warm the shared Emergency Operations file when it does not exist yet.

    A legacy GO cache is left untouched. That feed does not carry country MAA
    codes, and replacing it would change the appeals list an admin selected.
    """
    try:
        from plugins.emergency_operations.appeal_group import CACHE_SOURCE
        from plugins.emergency_operations.data_store import get_data_store

        store = get_data_store()
        if store.load_cached() is not None:
            return
        store.save(rows, {"format": "json"}, source=CACHE_SOURCE)
    except Exception:
        logger.debug("UPR MAA codes: could not warm the shared appeal catalogue", exc_info=True)


def _schedule_refresh_once() -> None:
    """Keep the shared catalogue fresh without blocking the visuals render."""
    global _refresh_checked_at
    now = time.monotonic()
    if (now - _refresh_checked_at) < _REFRESH_CHECK_SECONDS:
        return
    _refresh_checked_at = now
    try:
        from plugins.emergency_operations.data_store import get_data_store, trigger_background_refresh
        from plugins.emergency_operations.routes import _appeals_feed_url, plugin_config

        store = get_data_store()
        cached = store.load_cached() or {}
        cfg = plugin_config.get_all_config()
        schedule = (cfg.get("data_cache") or {}).get("schedule", "off")
        if not store.is_refresh_due(schedule, cached.get("fetched_at")):
            return
        timeout = (cfg.get("api") or {}).get("timeout", 60)
        trigger_background_refresh(_appeals_feed_url(), {"format": "json"}, timeout=timeout)
    except Exception:
        logger.debug("UPR MAA codes: scheduled catalogue refresh skipped", exc_info=True)


def _row_code(row: dict) -> str:
    return str(row.get("code") or row.get("Appeal_Id") or "").strip().upper()


def _row_iso(row: dict) -> str:
    country = row.get("country")
    if isinstance(country, dict):
        iso = str(country.get("iso") or "").strip().upper()
        if iso:
            return iso
    return str(row.get("Geographical_Code") or "").strip().upper()


def _row_status(row: dict) -> str:
    return str(row.get("status_display") or row.get("status") or row.get("Status") or "").strip()


def _row_day(row: dict, *keys: str) -> str:
    for key in keys:
        raw = row.get(key)
        if raw:
            return str(raw)[:10]
    return ""


def _as_year(value: Any) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2500 else None
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        return year if 1900 <= year <= 2500 else None
    return None


def _covers(start: str, end: str, year: int | None) -> bool:
    if not year:
        return False
    start_year = int(start[:4]) if len(start) >= 4 and start[:4].isdigit() else None
    end_year = int(end[:4]) if len(end) >= 4 and end[:4].isdigit() else None
    if start_year and end_year:
        return start_year <= year <= end_year
    if start_year and not end_year:
        return start_year <= year
    if end_year and not start_year:
        return year <= end_year
    return False


def _is_active(status: str) -> bool:
    label = status.casefold()
    return label in _ACTIVE_STATUS or label.startswith("active")
