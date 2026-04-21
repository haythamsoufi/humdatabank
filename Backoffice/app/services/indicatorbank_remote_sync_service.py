"""
Remote Indicator Bank sync service.

Purpose:
- The external IFRC Indicator Bank is still the source of truth.
- We need a reusable sync implementation that can be triggered from:
  - CLI (`flask indicatorbank sync-remote`)
  - Admin UI button (calls a backend endpoint)

Important behavior:
- Local `indicator_bank.id` is set to the remote `indicatorId` (authoritative).
- We do NOT store any extra sync marker in comments.
- We clear translations when the base English source text changes:
  - If `name` changes -> clear `name_translations`
  - If `definition` changes -> clear `definition_translations`
"""

from __future__ import annotations

import logging
from contextlib import nullcontext, suppress
from datetime import datetime
import threading
from typing import Any


logger = logging.getLogger(__name__)
_sync_lock = threading.Lock()
_sync_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "last_error": None,
}


def get_remote_sync_state() -> dict[str, Any]:
    """Get current/last sync state (safe to serialize to JSON)."""
    with _sync_lock:
        def _iso(dt: datetime | None):
            return dt.isoformat() if isinstance(dt, datetime) else None

        return {
            "running": bool(_sync_state.get("running")),
            "started_at": _iso(_sync_state.get("started_at")),
            "finished_at": _iso(_sync_state.get("finished_at")),
            "last_result": _sync_state.get("last_result"),
            "last_error": _sync_state.get("last_error"),
        }


def start_remote_sync(app, api_url: str, api_key: str, limit: int | None = None) -> tuple[bool, str]:
    """Start the remote sync in a background thread.

    Returns (success, message).
    """
    if not api_key:
        return False, "Missing IFRC Indicator Bank API key."

    with _sync_lock:
        if _sync_state.get("running"):
            return False, "A sync is already running."
        _sync_state["running"] = True
        _sync_state["started_at"] = datetime.utcnow()
        _sync_state["finished_at"] = None
        _sync_state["last_result"] = None
        _sync_state["last_error"] = None

    def _runner():
        try:
            with app.app_context():
                result = sync_remote_indicator_bank(api_url=api_url, api_key=api_key, limit=limit, apply=True)
            with _sync_lock:
                _sync_state["last_result"] = result
        except Exception as e:
            with _sync_lock:
                _sync_state["last_error"] = "Sync failed."
        finally:
            with _sync_lock:
                _sync_state["running"] = False
                _sync_state["finished_at"] = datetime.utcnow()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    return True, "Sync started."


def sync_remote_indicator_bank(
    *,
    api_url: str,
    api_key: str,
    limit: int | None = None,
    apply: bool = True,
) -> dict[str, int]:
    """Fetch and sync indicators from the remote IFRC Indicator Bank API.

    - When apply=False, performs a dry-run and returns the counts without DB writes.
    - When apply=True, performs upserts and commits via the caller's transaction/atomic wrapper.
    """
    import requests
    from sqlalchemy import text

    from app.extensions import db
    from app.models import IndicatorBank, Sector, SubSector
    from app.utils.transactions import atomic

    if not api_url:
        raise ValueError("Missing api_url")
    if not api_key:
        raise ValueError("Missing api_key")

    def _get_text_list(items):
        out: list[str] = []
        if not items:
            return out
        for it in items:
            with suppress(Exception):
                txt = it.get("text") if isinstance(it, dict) else None
                if txt and str(txt).strip():
                    out.append(str(txt).strip())
        # de-dupe, keep order
        seen: set[str] = set()
        deduped: list[str] = []
        for x in out:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        return deduped

    def _is_emergency(item: dict) -> bool:
        try:
            val = (item.get("emergency") or "").strip().lower()
            if val == "emergency":
                return True
        except Exception as e:
            logger.debug("Emergency check failed: %s", e)
        tags = _get_text_list(item.get("tags"))
        return any(t.strip().lower() == "emergency" for t in tags)

    def _normalize_type(type_of_measurement: str | None) -> str:
        t = (type_of_measurement or "").strip()
        if not t:
            return "Number"
        allowed = {"Number", "Percentage", "Text", "YesNo", "Date"}
        if t in allowed:
            return t
        tl = t.lower()
        if tl in ("number", "numeric", "count"):
            return "Number"
        if tl in ("percentage", "percent", "%"):
            return "Percentage"
        if tl in ("text", "string"):
            return "Text"
        if tl in ("yesno", "yes/no", "boolean", "bool"):
            return "YesNo"
        if tl in ("date", "datetime"):
            return "Date"
        return "Number"

    def _build_levels_json(primary_id, secondary_id, tertiary_id):
        data: dict[str, int] = {}
        if primary_id:
            data["primary"] = int(primary_id)
        if secondary_id:
            data["secondary"] = int(secondary_id)
        if tertiary_id:
            data["tertiary"] = int(tertiary_id)
        return data or None

    def _name_conflicts(target_id: int, new_name: str) -> bool:
        if not new_name:
            return False
        other = (
            IndicatorBank.query.filter(IndicatorBank.name == new_name)
            .filter(IndicatorBank.id != target_id)
            .first()
        )
        return other is not None

    # Fetch remote
    resp = requests.get(api_url, headers={"X-API-KEY": api_key}, timeout=180)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected response type: {type(payload)} (expected list)")
    if limit is not None and limit > 0:
        payload = payload[:limit]

    stats = {
        "sectors_created": 0,
        "subsectors_created": 0,
        "indicators_created": 0,
        "indicators_updated": 0,
        "name_translations_cleared": 0,
        "definition_translations_cleared": 0,
        # Remote indicatorId did not match an existing row id, but the name existed already.
        # We update the existing row by name to avoid unique-name insert failures.
        "name_id_mismatches": 0,
        "skipped": 0,
    }

    sector_cache: dict[str, Sector] = {}
    subsector_cache: dict[str, SubSector] = {}

    def _get_or_create_sector_by_name(name: str | None):
        key = (name or "").strip()
        if not key:
            return None
        if key in sector_cache:
            return sector_cache[key]
        obj = Sector.query.filter_by(name=key).first()
        if obj is None and apply:
            obj = Sector(name=key, is_active=True, display_order=0)
            db.session.add(obj)
            db.session.flush()
            stats["sectors_created"] += 1
        if obj is not None:
            sector_cache[key] = obj
        return obj

    def _get_or_create_subsector_by_name(name: str | None, parent_sector: Sector | None):
        key = (name or "").strip()
        if not key:
            return None
        if key in subsector_cache:
            ss = subsector_cache[key]
            if apply and parent_sector and getattr(ss, "sector_id", None) is None:
                ss.sector_id = parent_sector.id
            return ss
        obj = SubSector.query.filter_by(name=key).first()
        if obj is None and apply:
            obj = SubSector(name=key, is_active=True, display_order=0)
            if parent_sector:
                obj.sector_id = parent_sector.id
            db.session.add(obj)
            db.session.flush()
            stats["subsectors_created"] += 1
        if obj is not None:
            if apply and parent_sector and getattr(obj, "sector_id", None) is None:
                obj.sector_id = parent_sector.id
            subsector_cache[key] = obj
        return obj

    tx = atomic(remove_session=True) if apply else nullcontext()
    with tx:
        for item in payload:
            # Use a savepoint per item so one bad row doesn't rollback the whole sync.
            # (The outer `atomic()` handles the final commit.)
            savepoint = db.session.begin_nested() if apply else nullcontext()
            with savepoint:
                try:
                    if not isinstance(item, dict):
                        stats["skipped"] += 1
                        continue

                    remote_indicator_id = item.get("indicatorId")
                    try:
                        remote_indicator_id_int = int(remote_indicator_id) if remote_indicator_id is not None else None
                    except Exception as e:
                        logger.debug("Could not parse remote indicatorId %r: %s", remote_indicator_id, e)
                        remote_indicator_id_int = None
                    if remote_indicator_id_int is None:
                        stats["skipped"] += 1
                        continue

                    name = (item.get("title") or "").strip()
                    if not name:
                        stats["skipped"] += 1
                        continue

                    definition = (item.get("definition") or "").strip()
                    unit = (item.get("unitOfMeasurement") or "").strip() or None
                    indicator_type = _normalize_type(item.get("typeOfMeasurement"))
                    archived = bool(item.get("isArchived")) if item.get("isArchived") is not None else False
                    emergency_flag = _is_emergency(item)
                    related_programs = ", ".join(_get_text_list(item.get("relatedPrograms"))) or None
                    remote_comments = (item.get("comments") or "").strip() or None

                    p_sector = _get_or_create_sector_by_name(item.get("primarySector"))
                    s_sector = _get_or_create_sector_by_name(item.get("secondarySector"))
                    t_sector = _get_or_create_sector_by_name(item.get("tertiarySector"))

                    p_subsector = _get_or_create_subsector_by_name(item.get("primarySubsector"), p_sector)
                    s_subsector = _get_or_create_subsector_by_name(item.get("secondarySubsector"), s_sector)
                    t_subsector = _get_or_create_subsector_by_name(item.get("tertiarySubsector"), t_sector)

                    sector_json = _build_levels_json(
                        p_sector.id if p_sector else None,
                        s_sector.id if s_sector else None,
                        t_sector.id if t_sector else None,
                    )
                    subsector_json = _build_levels_json(
                        p_subsector.id if p_subsector else None,
                        s_subsector.id if s_subsector else None,
                        t_subsector.id if t_subsector else None,
                    )

                    existing = IndicatorBank.query.get(remote_indicator_id_int)
                    if existing is None:
                        # Avoid unique-name violations when the indicator already exists locally by title/name.
                        by_name = IndicatorBank.query.filter_by(name=name).first()
                        if by_name is not None:
                            existing = by_name
                            if existing.id != remote_indicator_id_int:
                                stats["name_id_mismatches"] += 1

                    if existing is None:
                        if not apply:
                            stats["indicators_created"] += 1
                            continue
                        existing = IndicatorBank(
                            id=remote_indicator_id_int,
                            name=name,
                            definition=definition,
                            type=indicator_type,
                            unit=unit,
                            emergency=emergency_flag,
                            related_programs=related_programs,
                            archived=archived,
                        )
                        existing.sector = sector_json
                        existing.sub_sector = subsector_json
                        existing.comments = remote_comments
                        db.session.add(existing)
                        # Flush inside savepoint to surface uniqueness problems per row.
                        db.session.flush()
                        stats["indicators_created"] += 1
                    else:
                        if not apply:
                            stats["indicators_updated"] += 1
                            continue

                        # If base EN text changes, clear translations so missing translations
                        # are visible and can be re-generated.
                        old_name = (existing.name or "").strip()
                        old_def = (existing.definition or "").strip()

                        # Name update (guarded by uniqueness)
                        if not _name_conflicts(existing.id, name):
                            if old_name != name:
                                had = isinstance(existing.name_translations, dict) and len(existing.name_translations) > 0
                                existing.name = name
                                if apply:
                                    existing.name_translations = {}
                                if had:
                                    stats["name_translations_cleared"] += 1

                        # Definition update (no uniqueness constraint)
                        if old_def != definition:
                            had = isinstance(existing.definition_translations, dict) and len(existing.definition_translations) > 0
                            existing.definition = definition
                            if apply:
                                existing.definition_translations = {}
                            if had:
                                stats["definition_translations_cleared"] += 1

                        existing.type = indicator_type
                        existing.unit = unit
                        existing.emergency = emergency_flag
                        existing.related_programs = related_programs
                        existing.archived = archived
                        existing.sector = sector_json
                        existing.sub_sector = subsector_json
                        existing.comments = remote_comments
                        db.session.flush()
                        stats["indicators_updated"] += 1
                except Exception as e:
                    logger.debug("Skipping indicator item during sync: %s", e)
                    stats["skipped"] += 1
                    continue

        # Ensure the Postgres sequence is not behind MAX(id) when we insert explicit IDs.
        if apply:
            db.session.execute(text(
                "SELECT setval("
                "pg_get_serial_sequence('indicator_bank','id'), "
                "(SELECT COALESCE(MAX(id), 1) FROM indicator_bank), "
                "true)"
            ))

    return stats
