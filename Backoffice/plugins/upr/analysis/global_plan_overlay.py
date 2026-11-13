"""Manual Global Plan overlay figures (SPF, appeals, large emergencies, divisions).

Stored under ``PluginData`` for plugin ``upr`` at key ``global_plan.overlay``.
Empty / null values are ignored by the aggregator so live UPR data still shows.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from plugins.upr.secondary.store import load_plugin_payload, save_plugin_payload
from app.utils.common.datetime_helpers import utcnow

OVERLAY_KEY = "global_plan.overlay"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def empty_overlay() -> dict[str, Any]:
    return {
        "updated_at": None,
        "years": {},
        "appeals": [],
        "large_emergency_iso3": [],
        "divisions": [],
    }


def _clean_iso3_list(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(values, str):
        parts = [p.strip() for p in values.replace(";", ",").replace("\n", ",").split(",")]
        values = parts
    if not isinstance(values, (list, tuple)):
        return out
    for item in values:
        code = str(item or "").strip().upper()
        if len(code) != 3 or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _clean_year_block(raw: Any) -> dict[str, Any]:
    block = raw if isinstance(raw, dict) else {}
    return {
        "special_purpose_funds": _num(block.get("special_purpose_funds")),
        "new_emergency_appeals_estimate": _num(block.get("new_emergency_appeals_estimate")),
        "emergency_appeals_rollover": _num(block.get("emergency_appeals_rollover")),
        "use_manual_ea_rollover": _truthy(block.get("use_manual_ea_rollover")),
        "note": str(block.get("note") or "").strip(),
    }


def _clean_appeal(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    year_raw = raw.get("year")
    try:
        year = int(year_raw) if year_raw is not None and str(year_raw).strip() != "" else None
    except (TypeError, ValueError):
        year = None
    iso3 = str(raw.get("iso3") or "").strip().upper() or None
    if iso3 and len(iso3) != 3:
        iso3 = None
    requested = _num(raw.get("amount_requested"))
    funded = _num(raw.get("amount_funded"))
    if not name and requested is None and funded is None:
        return None
    return {
        "year": year,
        "name": name,
        "iso3": iso3,
        "country": str(raw.get("country") or "").strip(),
        "region": str(raw.get("region") or "").strip(),
        "amount_requested": requested,
        "amount_funded": funded,
        "start_date": str(raw.get("start_date") or "").strip() or None,
        "end_date": str(raw.get("end_date") or "").strip() or None,
    }


def _clean_division(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    division = str(raw.get("division") or "").strip()
    value = _num(raw.get("value"))
    if not division or value is None:
        return None
    year_raw = raw.get("year")
    try:
        year = int(year_raw) if year_raw is not None and str(year_raw).strip() != "" else None
    except (TypeError, ValueError):
        year = None
    return {
        "year": year,
        "division": division,
        "department": str(raw.get("department") or "").strip(),
        "area": str(raw.get("area") or "EFs").strip() or "EFs",
        "value": value,
    }


def normalize_overlay(raw: Any) -> dict[str, Any]:
    """Coerce arbitrary JSON into the overlay schema."""
    payload = empty_overlay()
    if not isinstance(raw, dict):
        return payload
    years_in = raw.get("years") if isinstance(raw.get("years"), dict) else {}
    years: dict[str, dict[str, Any]] = {}
    for key, block in years_in.items():
        try:
            year = str(int(key))
        except (TypeError, ValueError):
            continue
        years[year] = _clean_year_block(block)
    payload["years"] = years
    payload["large_emergency_iso3"] = _clean_iso3_list(raw.get("large_emergency_iso3"))
    appeals = []
    for item in raw.get("appeals") or []:
        cleaned = _clean_appeal(item)
        if cleaned:
            appeals.append(cleaned)
    payload["appeals"] = appeals
    divisions = []
    for item in raw.get("divisions") or []:
        cleaned = _clean_division(item)
        if cleaned:
            divisions.append(cleaned)
    payload["divisions"] = divisions
    updated = raw.get("updated_at")
    payload["updated_at"] = str(updated).strip() if updated else None
    return payload


def load_overlay() -> dict[str, Any]:
    data = load_plugin_payload()
    return normalize_overlay(data.get(OVERLAY_KEY))


def save_overlay(raw: Any) -> dict[str, Any]:
    overlay = normalize_overlay(raw)
    overlay["updated_at"] = utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = deepcopy(load_plugin_payload()) if load_plugin_payload() else {}
    payload[OVERLAY_KEY] = overlay
    save_plugin_payload(payload)
    return overlay


def year_overlay(overlay: dict[str, Any] | None, year: int | None) -> dict[str, Any]:
    if not overlay or year is None:
        return _clean_year_block({})
    return _clean_year_block((overlay.get("years") or {}).get(str(year)))
