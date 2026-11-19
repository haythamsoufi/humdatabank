"""Pull approved DREF stages from the public GO ``dref3`` API into operations and baselines."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from app.extensions import db
from app.models.core import Country
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.config_store import go_base_url
from plugins.dref_monitoring.constants import (
    PLAN_VALIDATED,
    WORKFLOW_CLOSURE,
    WORKFLOW_MONITORING,
    WORKFLOW_PLAN_DRAFT,
)
from plugins.dref_monitoring.models import DrefBaseline, DrefOperation, DrefSyncLog
from plugins.dref_monitoring.services.go_parse import is_dref_appeal, parse_stage, stage_signature
from plugins.dref_monitoring.services.periods import default_frequency
from plugins.dref_monitoring.services.plans import latest_plan, sync_plan

logger = logging.getLogger(__name__)

_PAGE_LIMIT = 200
_MAX_PAGES = 50
_STATUS_UNSPECIFIED = "unspecified"


def _json_sectors(sectors: list[dict]) -> list[dict]:
    safe = []
    for item in sectors:
        budget = item.get("budget_chf")
        safe.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "budget_chf": None if budget is None else str(budget),
                "people_targeted": item.get("people_targeted"),
                "people_assisted": item.get("people_assisted"),
            }
        )
    return safe


def fetch_rows(http_get, base_url: str, *, operation_status: str | None = None) -> list[dict]:
    """Read the public dref3 feed. Omit ``operation_status`` to include active and closed rows."""
    rows: list[dict] = []
    for page in range(_MAX_PAGES):
        params = {"limit": _PAGE_LIMIT, "offset": page * _PAGE_LIMIT}
        if operation_status:
            params["operation_status"] = operation_status
        payload = http_get(base_url, params)
        if isinstance(payload, list):
            batch = payload
        elif isinstance(payload, dict):
            batch = payload.get("results") or []
        else:
            batch = []
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < _PAGE_LIMIT:
            break
    else:
        logger.warning("DREF GO sync stopped after %s rows; more pages may remain.", len(rows))
    return rows


def _country_id(iso3: str) -> int | None:
    if not iso3:
        return None
    country = Country.query.filter(db.func.upper(Country.iso3) == iso3.upper()).first()
    return country.id if country else None


def _apply_operation(parsed: dict, operation: DrefOperation | None) -> tuple[DrefOperation, bool]:
    created = operation is None
    if operation is None:
        operation = DrefOperation(
            appeal_code=parsed["appeal_code"],
            sign_off_authority="ns",
            reporting_frequency=default_frequency(
                parsed["appeal_type"],
                parsed["operation_timeframe_months"],
                parsed["start_date"],
                parsed["end_date"],
            ),
        )
        db.session.add(operation)
    operation.go_appeal_id = parsed["go_appeal_id"]
    operation.disaster_name = (parsed["disaster_name"] or parsed["appeal_code"])[:255]
    operation.pillar = parsed["pillar"][:32]
    operation.appeal_type = parsed["appeal_type"][:32]
    operation.allocation_type = parsed["allocation_type"][:32]
    operation.country_name = parsed["country_name"][:120]
    operation.country_iso3 = parsed["country_iso3"][:3]
    operation.country_id = _country_id(parsed["country_iso3"])
    operation.hazard = parsed["hazard"][:120]
    operation.districts = parsed["districts"]
    operation.region = parsed["region"][:80]
    operation.onset = parsed["onset"][:32]
    operation.crisis_category = parsed["crisis_category"][:32]
    operation.amount_approved = parsed["amount_approved"]
    operation.total_approved = parsed["total_approved"]
    operation.people_affected = parsed["people_affected"]
    operation.people_targeted = parsed["people_targeted"]
    operation.date_of_disaster = parsed["date_of_disaster"]
    operation.date_of_approval = parsed["date_of_approval"]
    operation.start_date = parsed["start_date"]
    operation.end_date = parsed["end_date"]
    operation.operation_timeframe_months = parsed["operation_timeframe_months"]
    status = (parsed.get("operation_status") or "").strip().lower()[:16]
    if status:
        operation.operation_status = status
    elif created:
        operation.operation_status = _STATUS_UNSPECIFIED
    return operation, created


def operation_status_for(stages: list[dict], latest: dict) -> str:
    """Status of the appeal as GO states it now.

    The latest stage wins when it has a status. GO often leaves that field blank
    on a final report after marking an earlier stage closed, so a blank latest
    stage falls back to the newest stage that does have a status. An older
    ``closed`` value does not override a latest stage that is still ``active``.
    """
    latest_status = (latest.get("operation_status") or "").strip().lower()[:16]
    if latest_status:
        return latest_status
    ordered = sorted(
        stages,
        key=lambda item: (item.get("date_of_approval") or date.min, str(item.get("go_stage_id") or "")),
    )
    for item in reversed(ordered):
        status = (item.get("operation_status") or "").strip().lower()[:16]
        if status:
            return status
    return _STATUS_UNSPECIFIED


def _sync_workflow(operation: DrefOperation) -> None:
    if operation.operation_status == "closed":
        operation.workflow_status = WORKFLOW_CLOSURE
        return
    if operation.workflow_status == WORKFLOW_CLOSURE and operation.operation_status == "active":
        plan = latest_plan(operation.id)
        if plan is not None and plan.status == PLAN_VALIDATED:
            operation.workflow_status = WORKFLOW_MONITORING
        else:
            operation.workflow_status = WORKFLOW_PLAN_DRAFT


def _upsert_baseline(operation: DrefOperation, parsed: dict) -> DrefBaseline:
    row = DrefBaseline.query.filter_by(go_stage_id=parsed["go_stage_id"]).first()
    if row is None:
        row = DrefBaseline(operation_id=operation.id, go_stage_id=parsed["go_stage_id"])
        db.session.add(row)
    row.operation_id = operation.id
    row.stage = parsed["stage"][:64]
    row.allocation = parsed["allocation"][:64]
    row.amount_approved = parsed["amount_approved"]
    row.total_approved = parsed["total_approved"]
    row.start_date = parsed["start_date"]
    row.end_date = parsed["end_date"]
    row.people_targeted = parsed["people_targeted"]
    row.people_assisted = parsed["people_assisted"]
    row.sectors = _json_sectors(parsed["sectors"])
    row.is_latest = False
    row.synced_at = utcnow()
    return row


def apply_rows(rows: list[dict], today: date | None = None) -> dict:
    """Upsert operations from parsed or raw dref3 rows. Commits once."""
    today = today or date.today()
    parsed_rows = []
    for row in rows:
        parsed = row if "go_stage_id" in row and "sectors" in row else parse_stage(row)
        if parsed:
            parsed_rows.append(parsed)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for parsed in parsed_rows:
        if not is_dref_appeal(parsed.get("appeal_type") or ""):
            continue
        grouped[parsed["appeal_code"]].append(parsed)

    created = 0
    updated = 0
    for appeal_code, stages in grouped.items():
        latest = next((item for item in stages if item.get("is_latest_stage")), None)
        if latest is None:
            latest = max(stages, key=lambda item: (item.get("date_of_approval") or date.min, item["go_stage_id"]))
        if not is_dref_appeal(latest.get("appeal_type") or ""):
            continue
        latest["operation_status"] = operation_status_for(stages, latest)
        operation = DrefOperation.query.filter_by(appeal_code=appeal_code).first()
        previous = None
        if operation is not None:
            current = DrefBaseline.query.filter_by(operation_id=operation.id, is_latest=True).first()
            if current is not None:
                previous = stage_signature(
                    {
                        "total_approved": current.total_approved,
                        "end_date": current.end_date,
                        "sectors": list(current.sectors or []),
                    }
                )
        operation, was_created = _apply_operation(latest, operation)
        db.session.flush()
        DrefBaseline.query.filter_by(operation_id=operation.id).update({"is_latest": False})
        for stage in stages:
            baseline = _upsert_baseline(operation, stage)
            baseline.is_latest = stage["go_stage_id"] == latest["go_stage_id"]
        db.session.flush()
        latest_row = DrefBaseline.query.filter_by(operation_id=operation.id, is_latest=True).first()
        if latest_row is not None:
            sync_plan(operation, latest_row, previous, today)
        _sync_workflow(operation)
        from plugins.dref_monitoring.services.project_link import sync_operation_project

        sync_operation_project(operation)
        if was_created:
            created += 1
        else:
            updated += 1
    removed = _drop_non_dref_operations()
    db.session.commit()
    return {"created": created, "updated": updated, "removed": removed, "appeals": len(grouped)}


def _drop_non_dref_operations() -> int:
    """Remove Emergency Appeals and any other non-DREF rows a previous sync stored."""
    stale = [row for row in DrefOperation.query.all() if not is_dref_appeal(row.appeal_type)]
    if not stale:
        return 0
    ids = [row.id for row in stale]
    for row in stale:
        db.session.expunge(row)
    DrefOperation.query.filter(DrefOperation.id.in_(ids)).delete(synchronize_session=False)
    return len(ids)


def _default_http_get(url, params):
    import requests

    response = requests.get(
        url,
        params=params,
        timeout=20,
        headers={"Accept": "application/json", "User-Agent": "IFRC-Network-Databank/dref-monitoring"},
    )
    response.raise_for_status()
    return response.json()


def sync_from_go(http_get=None, *, operation_status: str | None = None) -> dict:
    log = DrefSyncLog(status="ok", message="")
    db.session.add(log)
    db.session.flush()
    try:
        rows = fetch_rows(http_get or _default_http_get, go_base_url(), operation_status=operation_status)
        summary = apply_rows(rows)
        log.finished_at = utcnow()
        log.created_count = summary["created"]
        log.updated_count = summary["updated"]
        log.message = f"Synced {summary['appeals']} DREF appeal(s)."
        if summary["removed"]:
            log.message += f" Removed {summary['removed']} non-DREF operation(s)."
        log.status = "ok"
        db.session.commit()
        summary["log_id"] = log.id
        return summary
    except Exception as exc:
        logger.warning("DREF GO sync failed: %s", exc)
        db.session.rollback()
        failed = DrefSyncLog(status="error", message=str(exc)[:1000], finished_at=utcnow())
        db.session.add(failed)
        db.session.commit()
        raise
