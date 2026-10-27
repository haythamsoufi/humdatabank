"""Manual tentative end-date overrides for Emergency Operations appeals.

Stored in a dedicated ``plugin_data`` row so settings saves cannot wipe them.
Applied on catalogue reads so filters and form lists see the adjusted end date
while the source cache keeps the ERP value for sync checks.
"""

from __future__ import annotations

import copy
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import has_app_context
from flask_login import current_user

from app.extensions import db
from app.models.plugin_data import PluginData
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

PLUGIN_DATA_ID = "emergency_operations_end_date_overrides"
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


def _normalize_code(code: Any) -> str:
    return str(code or "").strip().upper()


def _normalize_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return text


def _actor() -> Optional[str]:
    try:
        if current_user and getattr(current_user, "is_authenticated", False):
            return (
                getattr(current_user, "email", None)
                or getattr(current_user, "username", None)
                or str(getattr(current_user, "id", "") or "")
                or None
            )
    except Exception:
        pass
    return None


def _empty_payload() -> Dict[str, Any]:
    return {"overrides": {}}


def _row_query(*, for_update: bool = False):
    query = PluginData.query.filter_by(plugin_id=PLUGIN_DATA_ID)
    if for_update:
        query = query.with_for_update()
    return query


def _read_payload() -> Dict[str, Any]:
    if not has_app_context():
        return _empty_payload()
    try:
        row = _row_query().first()
    except Exception as exc:
        logger.warning("Failed to read end-date overrides: %s", exc)
        return _empty_payload()
    if row is None or not isinstance(row.data, dict):
        return _empty_payload()
    overrides = row.data.get("overrides")
    if not isinstance(overrides, dict):
        return _empty_payload()
    return {"overrides": copy.deepcopy(overrides)}


def _write_payload(payload: Dict[str, Any]) -> bool:
    if not has_app_context():
        logger.warning("Cannot persist end-date overrides outside application context")
        return False
    try:
        row = _row_query(for_update=True).first()
        data = {
            "overrides": copy.deepcopy(payload.get("overrides") or {}),
            "updated_at": utcnow().isoformat(),
        }
        if row is None:
            row = PluginData(plugin_id=PLUGIN_DATA_ID, data=data)
            db.session.add(row)
        else:
            row.data = data
            row.updated_at = utcnow()
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to save end-date overrides: %s", exc, exc_info=True)
        return False


def get_overrides_map() -> Dict[str, Dict[str, Any]]:
    """Return ``{CODE: {end_date, note, updated_at, updated_by}}``."""
    payload = _read_payload()
    out: Dict[str, Dict[str, Any]] = {}
    for raw_code, raw_entry in (payload.get("overrides") or {}).items():
        code = _normalize_code(raw_code)
        if not code or not isinstance(raw_entry, dict):
            continue
        end_date = _normalize_date(raw_entry.get("end_date"))
        if not end_date:
            continue
        out[code] = {
            "end_date": end_date,
            "note": str(raw_entry.get("note") or "").strip(),
            "updated_at": raw_entry.get("updated_at"),
            "updated_by": raw_entry.get("updated_by"),
        }
    return out


def upsert_override(code: str, end_date: str, note: str = "") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Create or update an override. Returns ``(entry, error)``."""
    norm_code = _normalize_code(code)
    if not norm_code or not _CODE_RE.match(norm_code):
        return None, "Invalid appeal code"
    norm_date = _normalize_date(end_date)
    if not norm_date:
        return None, "Invalid end date (expected YYYY-MM-DD)"
    note_text = str(note or "").strip()[:500]

    payload = _read_payload()
    overrides = payload.setdefault("overrides", {})
    entry = {
        "end_date": norm_date,
        "note": note_text,
        "updated_at": utcnow().isoformat(),
        "updated_by": _actor(),
    }
    overrides[norm_code] = entry
    if not _write_payload(payload):
        return None, "Failed to save override"
    return {"code": norm_code, **entry}, None


def delete_override(code: str) -> Tuple[bool, Optional[str]]:
    """Remove an override. Returns ``(ok, error)``."""
    norm_code = _normalize_code(code)
    if not norm_code:
        return False, "Invalid appeal code"
    payload = _read_payload()
    overrides = payload.get("overrides") or {}
    matched = next((k for k in list(overrides) if _normalize_code(k) == norm_code), None)
    if matched is None:
        return False, "Override not found"
    del overrides[matched]
    if not _write_payload(payload):
        return False, "Failed to delete override"
    return True, None


def apply_end_date_overrides(results: List[dict]) -> List[dict]:
    """Return a new list with overridden ``end_date`` values (does not mutate cache)."""
    overrides = get_overrides_map()
    if not overrides or not results:
        return results

    out: List[dict] = []
    for item in results:
        if not isinstance(item, dict):
            out.append(item)
            continue
        code = _normalize_code(item.get("code"))
        ov = overrides.get(code) if code else None
        if not ov:
            out.append(item)
            continue
        row = dict(item)
        source_end = _normalize_date(item.get("end_date"))
        row["source_end_date"] = source_end
        row["end_date"] = ov["end_date"]
        row["end_date_overridden"] = True
        out.append(row)
    return out


def _source_status(override_end: str, source_end: Optional[str]) -> Dict[str, Any]:
    """Compare manual tentative end date against ERP/source cache value."""
    if not source_end:
        return {
            "source_matches": False,
            "source_covers": False,
            "sync_status": "missing_source",
            "can_remove": False,
        }
    matches = source_end == override_end
    covers = source_end >= override_end
    if matches:
        status = "matched"
    elif covers:
        status = "source_ahead"
    else:
        status = "pending"
    return {
        "source_matches": matches,
        "source_covers": covers,
        "sync_status": status,
        "can_remove": covers,
    }


def list_overrides_with_source(source_by_code: Optional[Dict[str, Optional[str]]] = None) -> List[Dict[str, Any]]:
    """List overrides enriched with source end dates and sync status."""
    overrides = get_overrides_map()
    source_by_code = source_by_code or {}
    rows: List[Dict[str, Any]] = []
    for code, entry in sorted(overrides.items()):
        source_end = _normalize_date(source_by_code.get(code))
        status = _source_status(entry["end_date"], source_end)
        rows.append(
            {
                "code": code,
                "end_date": entry["end_date"],
                "note": entry.get("note") or "",
                "updated_at": entry.get("updated_at"),
                "updated_by": entry.get("updated_by"),
                "source_end_date": source_end,
                **status,
            }
        )
    return rows


def source_end_dates_from_cache(results: Optional[List[dict]]) -> Dict[str, Optional[str]]:
    """Build ``{CODE: source_end_date}`` from raw appeals cache rows."""
    out: Dict[str, Optional[str]] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        code = _normalize_code(item.get("code"))
        if not code:
            continue
        out[code] = _normalize_date(item.get("end_date"))
    return out
