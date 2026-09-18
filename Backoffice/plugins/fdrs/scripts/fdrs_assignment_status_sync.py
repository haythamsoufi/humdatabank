"""
FDRS section workflow KPIs → assignment_entity_status sync.

Reads per-section WasStarted / WasSubmitted / WasValidated flags and ValidationDate /
PublishDate from data-api.ifrc.org fdrsdata, then maps to databank assignment workflow.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from fdrs_sync_constants import (
    FDRS_SECTION_WORKFLOW_SPECS,
    FdrsSyncCancelled,
    fdrs_section_workflow_kpi_codes,
)

logger = logging.getLogger(__name__)

_WORKFLOW_KPI_SET = frozenset(fdrs_section_workflow_kpi_codes())


def _parse_fdrs_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def _parse_fdrs_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y  %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _fdrs_row_value(row: Dict[str, Any]) -> Any:
    for key in ("BoolValue", "DateValue", "IntValue", "StrValue", "value", "Value"):
        val = row.get(key)
        if val is not None:
            return val
    return None


def fetch_section_workflow_rows(
    base_url: str,
    api_key: str,
    *,
    years: Optional[List[int]] = None,
    min_status: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch raw fdrsdata rows for section workflow KPIs only."""
    from fdrs_data_fetcher import _fdrs_reporting_year_key

    if years is None:
        years = [2024]
    years_str = ",".join(str(int(y)) for y in years)
    params = {
        "year": years_str,
        "force": "true",
        "minstatus": str(max(0, min(int(min_status), 500))),
        "showunpublished": "true",
        "apiKey": api_key,
    }
    url = f"{base_url.rstrip('/')}/api/fdrsdata?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, list):
        logger.warning("Unexpected fdrsdata payload type for workflow KPIs: %s", type(payload))
        return []

    out: List[Dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        kpi = (row.get("KPICode") or row.get("KPI_code") or "").strip()
        if kpi not in _WORKFLOW_KPI_SET:
            continue
        year_raw = row.get("Year") or row.get("year")
        year_key = _fdrs_reporting_year_key(year_raw)
        out.append(
            {
                "DonCode": (row.get("DonCode") or "").strip(),
                "year": str(year_key if year_key is not None else year_raw),
                "KPI_code": kpi,
                "value": _fdrs_row_value(row),
                "State": row.get("State"),
            }
        )
    return out


def _section_states_from_kpi_values(kpi_values: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    for spec in FDRS_SECTION_WORKFLOW_SPECS:
        prefix = spec["prefix"]
        validation_date = _parse_fdrs_datetime(kpi_values.get(f"{prefix}_ValidationDate"))
        publish_date = _parse_fdrs_datetime(kpi_values.get(f"{prefix}_PublishDate"))
        sections.append(
            {
                "label": spec["label"],
                "started": _parse_fdrs_bool(kpi_values.get(f"{prefix}_WasStarted")),
                "submitted": _parse_fdrs_bool(kpi_values.get(f"{prefix}_WasSubmitted")),
                "validated": _parse_fdrs_bool(kpi_values.get(f"{prefix}_WasValidated")),
                "published": _parse_fdrs_bool(kpi_values.get(f"{prefix}_WasPublished")),
                "validation_date": validation_date,
                "publish_date": publish_date,
            }
        )
    return sections


def derive_assignment_status_from_sections(sections: List[Dict[str, Any]]) -> Optional[str]:
    """
    Map FDRS section flags to databank assignment_entity_status.status.

    - all sections validated (or published) → approved
    - all sections submitted → submitted
    - any section submitted/validated → submitted (partial progress)
    - any section started only → in_progress
    - no workflow signal → None (skip update)
    """
    if not sections:
        return None
    if not any(s["started"] or s["submitted"] or s["validated"] or s["published"] for s in sections):
        return None

    all_validated = all(s["validated"] or s["published"] for s in sections)
    if all_validated:
        return "approved"

    all_submitted = all(s["submitted"] for s in sections)
    if all_submitted:
        return "submitted"

    if any(s["submitted"] or s["validated"] or s["published"] for s in sections):
        return "submitted"

    if any(s["started"] for s in sections):
        return "in_progress"

    return None


def _section_event_datetimes(sections: List[Dict[str, Any]]) -> Tuple[List[datetime], List[datetime]]:
    """Return (submitted-ish dates, all workflow dates) for timestamp selection."""
    submitted_dates: List[datetime] = []
    all_dates: List[datetime] = []
    for section in sections:
        for dt in (section.get("publish_date"), section.get("validation_date")):
            if dt is not None:
                all_dates.append(dt)
        if section.get("submitted") or section.get("validated") or section.get("published"):
            for dt in (section.get("publish_date"), section.get("validation_date")):
                if dt is not None:
                    submitted_dates.append(dt)
    return submitted_dates, all_dates


def derive_assignment_timestamps(
    status: str,
    sections: List[Dict[str, Any]],
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Return (status_timestamp, submitted_at) from section workflow dates."""
    submitted_dates, all_dates = _section_event_datetimes(sections)
    if not all_dates:
        return None, None

    status_timestamp = max(all_dates)
    submitted_at = min(submitted_dates) if submitted_dates else min(all_dates)

    if status == "in_progress":
        return status_timestamp, None
    if status == "submitted":
        return status_timestamp, submitted_at
    if status == "approved":
        return status_timestamp, submitted_at
    return status_timestamp, submitted_at


def build_assignment_status_plan(
    workflow_rows: List[Dict[str, Any]],
    assignment_rows: List[Dict[str, Any]],
    *,
    don_to_iso: Optional[Dict[str, str]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build per-assignment status updates from workflow KPI rows."""
    if don_to_iso is None:
        from fdrs_data_fetcher import fetch_country_map

        country_map = fetch_country_map(base_url=base_url or "", api_key=api_key)
        don_to_iso = {don: iso for don, iso in country_map.items() if don and iso}

    assignment_by_key: Dict[Tuple[str, str], int] = {
        (r["period_name"], r["iso3"]): int(r["assignment_entity_status_id"]) for r in assignment_rows
    }

    kpi_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in workflow_rows or []:
        don = (row.get("DonCode") or "").strip()
        year = str(row.get("year") or "").strip()
        kpi = (row.get("KPI_code") or "").strip()
        iso3 = don_to_iso.get(don, "")
        if not iso3 or not year or not kpi:
            continue
        kpi_index.setdefault((iso3, year), {})[kpi] = row.get("value")

    summary: Dict[str, Any] = {
        "workflow_rows": len(workflow_rows or []),
        "planned": 0,
        "skipped_no_assignment": 0,
        "skipped_no_signal": 0,
        "by_status": {},
    }
    plan: List[Dict[str, Any]] = []

    for (iso3, year), kpi_values in sorted(kpi_index.items()):
        aes_id = assignment_by_key.get((year, iso3))
        if aes_id is None:
            summary["skipped_no_assignment"] += 1
            continue

        sections = _section_states_from_kpi_values(kpi_values)
        status = derive_assignment_status_from_sections(sections)
        if not status:
            summary["skipped_no_signal"] += 1
            continue

        status_timestamp, submitted_at = derive_assignment_timestamps(status, sections)
        summary["planned"] += 1
        summary.setdefault("by_status", {})
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

        plan.append(
            {
                "assignment_entity_status_id": aes_id,
                "period_name": year,
                "iso3": iso3,
                "status": status,
                "status_timestamp": status_timestamp,
                "submitted_at": submitted_at,
                "sections": sections,
            }
        )

    return plan, summary


def upsert_assignment_status_from_plan(
    plan_rows: List[Dict[str, Any]],
    *,
    dry_run: bool = False,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_start_pct: float = 94.0,
    progress_end_pct: float = 99.0,
) -> Dict[str, int]:
    """Apply assignment status updates. Does not set submitted_by / approved_by (unknown in FDRS)."""
    from app.extensions import db
    from app.models.assignments import AssignmentEntityStatus
    from app.models.enums import AssignmentEntityStatusValue

    stats = {"updated": 0, "skipped": 0, "errors": 0}
    if not plan_rows:
        return stats

    total_rows = len(plan_rows)

    def _check_cancel() -> None:
        if cancel_check and cancel_check():
            raise FdrsSyncCancelled()

    def _emit_progress(index: int, *, message: str) -> None:
        _check_cancel()
        if not progress_cb:
            return
        span = max(progress_end_pct - progress_start_pct, 0.0)
        pct = progress_start_pct + (span * (index / total_rows)) if total_rows else progress_end_pct
        try:
            progress_cb(
                {
                    "stage": "assignment_status_upsert",
                    "message": message,
                    "current": index,
                    "total": total_rows,
                    "percent": pct,
                    "stats": dict(stats),
                }
            )
        except FdrsSyncCancelled:
            raise
        except Exception as e:
            logger.debug("assignment status progress_cb failed: %s", e)

    aes_ids = [int(r["assignment_entity_status_id"]) for r in plan_rows]
    aes_by_id = {
        int(row.id): row
        for row in AssignmentEntityStatus.query.filter(AssignmentEntityStatus.id.in_(aes_ids)).all()
    }

    for i, row in enumerate(plan_rows, start=1):
        _check_cancel()
        try:
            aes_id = int(row["assignment_entity_status_id"])
            aes = aes_by_id.get(aes_id)
            if aes is None:
                stats["skipped"] += 1
                continue

            current_status = aes.status.value if hasattr(aes.status, "value") else str(aes.status)
            if current_status == AssignmentEntityStatusValue.cancelled.value:
                stats["skipped"] += 1
                continue

            new_status = AssignmentEntityStatusValue.normalize(row["status"])
            new_ts = row.get("status_timestamp")
            new_submitted_at = row.get("submitted_at")

            changed = current_status != new_status.value
            if new_ts is not None and aes.status_timestamp != new_ts:
                changed = True
            if new_submitted_at != aes.submitted_at:
                changed = True
            if new_status.value == "in_progress" and aes.submitted_at is not None:
                changed = True

            if not changed:
                stats["skipped"] += 1
                continue

            if dry_run:
                stats["updated"] += 1
                continue

            aes.status = new_status
            if new_ts is not None:
                aes.status_timestamp = new_ts
            if new_status.value in {"submitted", "approved"}:
                if new_submitted_at is not None:
                    aes.submitted_at = new_submitted_at
            else:
                aes.submitted_at = None
            db.session.add(aes)
            stats["updated"] += 1

            if i == 1 or i % 50 == 0 or i == total_rows:
                _emit_progress(i, message=f"Assignment status {i}/{total_rows}")
        except FdrsSyncCancelled:
            raise
        except Exception as e:
            stats["errors"] += 1
            logger.error("Assignment status row error (aes_id=%s): %s", row.get("assignment_entity_status_id"), e)

    if not dry_run and stats["updated"] > 0:
        db.session.commit()
    return stats


def run_fdrs_assignment_status_sync(
    *,
    base_url: str,
    api_key: str,
    assignment_rows: List[Dict[str, Any]],
    years: Optional[List[int]] = None,
    dry_run: bool = False,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_start_pct: float = 94.0,
    progress_end_pct: float = 99.0,
) -> Dict[str, Any]:
    """Fetch workflow KPIs, build plan, upsert assignment_entity_status."""
    def _progress(**kwargs: Any) -> None:
        if cancel_check and cancel_check():
            raise FdrsSyncCancelled()
        if not progress_cb:
            return
        try:
            progress_cb(kwargs)
        except FdrsSyncCancelled:
            raise
        except Exception:
            pass

    _progress(
        stage="assignment_status",
        message="Fetching FDRS section workflow KPIs...",
        percent=progress_start_pct,
        current=0,
        total=0,
    )

    workflow_rows = fetch_section_workflow_rows(base_url, api_key, years=years)
    plan, summary = build_assignment_status_plan(
        workflow_rows,
        assignment_rows,
        base_url=base_url,
        api_key=api_key,
    )
    planned = int(summary.get("planned") or 0)
    _progress(
        stage="assignment_status_plan",
        message=f"Assignment status planned: {planned}",
        percent=progress_start_pct,
        current=0,
        total=planned,
    )
    upsert_stats = upsert_assignment_status_from_plan(
        plan,
        dry_run=dry_run,
        progress_cb=progress_cb,
        cancel_check=cancel_check,
        progress_start_pct=progress_start_pct,
        progress_end_pct=progress_end_pct,
    )
    _progress(
        stage="assignment_status_done",
        message=(
            f"Assignment status: updated={upsert_stats.get('updated', 0)} "
            f"skipped={upsert_stats.get('skipped', 0)} "
            f"errors={upsert_stats.get('errors', 0)}"
        ),
        percent=progress_end_pct,
        current=planned,
        total=planned,
    )

    logger.info(
        "FDRS assignment status: planned=%s updated=%s skipped=%s errors=%s by_status=%s",
        summary.get("planned"),
        upsert_stats.get("updated"),
        upsert_stats.get("skipped"),
        upsert_stats.get("errors"),
        summary.get("by_status"),
    )
    return {
        "assignment_status_summary": summary,
        "assignment_status_stats": upsert_stats,
    }
