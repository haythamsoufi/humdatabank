"""Pull approved DREF stages from the public GO ``dref3`` API, and Emergency Appeals from the ``appeal`` API,
into operations and baselines."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from threading import Lock

from sqlalchemy.orm import sessionmaker

from app.extensions import db
from app.models.core import Country
from app.utils.common.datetime_helpers import utcnow
from plugins.emergency_operations_monitoring.config_store import emergency_appeal_settings, go_appeal_url, go_base_url
from plugins.emergency_operations_monitoring.constants import (
    APPEAL_STAGE_PREFIX,
    PLAN_VALIDATED,
    WORKFLOW_CLOSURE,
    WORKFLOW_MONITORING,
    WORKFLOW_PLAN_DRAFT,
)
from plugins.emergency_operations_monitoring.models import DrefBaseline, DrefOperation, DrefSyncLog
from plugins.emergency_operations_monitoring.services.go_application import NARRATIVE_VERSION
from plugins.emergency_operations_monitoring.services.go_appeals import appeal_queries, appeal_row
from plugins.emergency_operations_monitoring.services.go_parse import (
    is_emergency_appeal,
    is_monitored_appeal,
    narrative_signature,
    parse_stage,
    stage_signature,
)
from plugins.emergency_operations_monitoring.services.periods import default_frequency
from plugins.emergency_operations_monitoring.services.plans import backfill_appeal_indicators, latest_plan, sync_plan

logger = logging.getLogger(__name__)

_PAGE_LIMIT = 200
_MAX_PAGES = 100
_MAX_APPEAL_PAGES = 10


class FeedRows(list):
    """Rows read from the feed. ``truncated`` is set when the page cap stopped the read."""

    truncated = False
_STATUS_UNSPECIFIED = "unspecified"
# Session advisory lock shared by the manual job, the 05:10 UTC job, and the CLI.
# Namespace is next to the digest locks (702348, 702349), clear of the AI-job range.
DREF_GO_SYNC_LOCK_ID = 702360
_THREAD_LOCK = Lock()
_log_touch_at: dict[int, float] = {}


class GoSyncCancelled(Exception):
    """The operator asked the running sync to stop. Nothing from this pull is kept."""


class GoSyncBusy(Exception):
    """Another GO sync already holds the lock."""


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


def fetch_rows(
    http_get,
    base_url: str,
    *,
    operation_status: str | None = None,
    progress=None,
    should_stop=None,
) -> list[dict]:
    """Read the public dref3 feed. Omit ``operation_status`` to include active and closed rows."""
    rows = FeedRows()
    for page in range(_MAX_PAGES):
        if should_stop and should_stop():
            raise GoSyncCancelled()
        if progress:
            progress(
                {
                    "stage": "fetching",
                    "message": "Reading the GO feed, page %(current)s.",
                    "message_vars": {"current": page + 1},
                    "current": page + 1,
                    "total": None,
                    "percent": min(19.0, float((page + 1) * 4)),
                }
            )
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
            if progress:
                progress(
                    {
                        "stage": "fetching",
                        "message": "Reading the GO feed, page %(current)s.",
                        "message_vars": {"current": page + 1},
                        "current": page + 1,
                        "total": page + 1,
                        "percent": 20.0,
                    }
                )
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < _PAGE_LIMIT:
            if progress:
                progress(
                    {
                        "stage": "fetching",
                        "message": "Reading the GO feed, page %(current)s.",
                        "message_vars": {"current": page + 1},
                        "current": page + 1,
                        "total": page + 1,
                        "percent": 20.0,
                    }
                )
            break
    else:
        rows.truncated = True
        logger.warning("Emergency Operations GO sync stopped after %s rows; more pages may remain.", len(rows))
    return rows


def fetch_appeal_rows(
    http_get,
    url: str,
    *,
    closed_since_year: int,
    progress=None,
    should_stop=None,
) -> list[dict]:
    """Read Emergency Appeals from the public appeal API as dref3-shaped rows.

    Every active appeal is read, and every appeal that started since ``closed_since_year``.
    An appeal found by both reads is kept once.
    """
    found: dict[str, dict] = {}
    pages = 0
    for query in appeal_queries(closed_since_year):
        for page in range(_MAX_APPEAL_PAGES):
            if should_stop and should_stop():
                raise GoSyncCancelled()
            pages += 1
            if progress:
                progress(
                    {
                        "stage": "fetching",
                        "message": "Reading Emergency Appeals, page %(current)s.",
                        "message_vars": {"current": pages},
                        "current": pages,
                        "total": None,
                        "percent": min(19.5, 16.0 + pages),
                    }
                )
            payload = http_get(url, {**query, "limit": _PAGE_LIMIT, "offset": page * _PAGE_LIMIT})
            batch = payload.get("results") if isinstance(payload, dict) else payload
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                row = appeal_row(item)
                if row is not None:
                    found.setdefault(row["appeal_code"], row)
            if len(batch) < _PAGE_LIMIT:
                break
    return list(found.values())


def _hold_stored_appeals(rows: list[dict]) -> int:
    """Drop dref3 loan rows of an appeal this pull did not return, when the appeal is already stored.

    The loan DREF of an Emergency Appeal shares its code. Without the appeal row, those rows would
    become the latest stage and replace the appeal's budget with the loan. Returns how many were held.
    """
    present = {
        str(row.get("appeal_code") or "").strip().upper() for row in rows if row.get("appeal_feed")
    }
    loans = {
        str(row.get("appeal_code") or "").strip().upper()
        for row in rows
        if not row.get("appeal_feed") and is_emergency_appeal(row.get("appeal_type") or "")
    } - present
    if not loans:
        return 0
    stored = {
        code
        for (code,) in db.session.query(DrefOperation.appeal_code)
        .join(DrefBaseline, DrefBaseline.operation_id == DrefOperation.id)
        .filter(
            DrefOperation.appeal_code.in_(sorted(loans)),
            DrefBaseline.go_stage_id.like(f"{APPEAL_STAGE_PREFIX}%"),
        )
        .distinct()
        .all()
    }
    if not stored:
        return 0
    kept = [
        row
        for row in rows
        if row.get("appeal_feed")
        or not is_emergency_appeal(row.get("appeal_type") or "")
        or str(row.get("appeal_code") or "").strip().upper() not in stored
    ]
    held = len(rows) - len(kept)
    rows[:] = kept
    return held


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
    if isinstance(parsed.get("application"), dict):
        row.application = parsed["application"]
    row.is_latest = False
    row.synced_at = utcnow()
    return row


def _money_key(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)


def _stage_fingerprint(parsed: dict) -> tuple:
    return (
        (parsed.get("stage") or "")[:64],
        (parsed.get("allocation") or "")[:64],
        _money_key(parsed.get("amount_approved")),
        _money_key(parsed.get("total_approved")),
        parsed.get("start_date"),
        parsed.get("end_date"),
        parsed.get("people_targeted"),
        parsed.get("people_assisted"),
        stage_signature(parsed),
        narrative_signature(parsed.get("application")),
    )


def _baseline_fingerprint(row: DrefBaseline) -> tuple:
    return _stage_fingerprint(
        {
            "stage": row.stage or "",
            "allocation": row.allocation or "",
            "amount_approved": row.amount_approved,
            "total_approved": row.total_approved,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "people_targeted": row.people_targeted,
            "people_assisted": row.people_assisted,
            "sectors": list(row.sectors or []),
            "application": row.application,
        }
    )


def _header_fingerprint(parsed: dict, country_id: int | None) -> tuple:
    return (
        parsed.get("go_appeal_id"),
        (parsed.get("disaster_name") or parsed.get("appeal_code") or "")[:255],
        (parsed.get("pillar") or "")[:32],
        (parsed.get("appeal_type") or "")[:32],
        (parsed.get("allocation_type") or "")[:32],
        (parsed.get("country_name") or "")[:120],
        (parsed.get("country_iso3") or "")[:3],
        country_id,
        (parsed.get("hazard") or "")[:120],
        parsed.get("districts") or "",
        (parsed.get("region") or "")[:80],
        (parsed.get("onset") or "")[:32],
        (parsed.get("crisis_category") or "")[:32],
        _money_key(parsed.get("amount_approved")),
        _money_key(parsed.get("total_approved")),
        parsed.get("people_affected"),
        parsed.get("people_targeted"),
        parsed.get("date_of_disaster"),
        parsed.get("date_of_approval"),
        parsed.get("start_date"),
        parsed.get("end_date"),
        parsed.get("operation_timeframe_months"),
        (parsed.get("operation_status") or "").strip().lower()[:16],
    )


def _operation_fingerprint(operation: DrefOperation) -> tuple:
    return (
        operation.go_appeal_id,
        operation.disaster_name or "",
        operation.pillar or "",
        operation.appeal_type or "",
        operation.allocation_type or "",
        operation.country_name or "",
        operation.country_iso3 or "",
        operation.country_id,
        operation.hazard or "",
        operation.districts or "",
        operation.region or "",
        operation.onset or "",
        operation.crisis_category or "",
        _money_key(operation.amount_approved),
        _money_key(operation.total_approved),
        operation.people_affected,
        operation.people_targeted,
        operation.date_of_disaster,
        operation.date_of_approval,
        operation.start_date,
        operation.end_date,
        operation.operation_timeframe_months,
        (operation.operation_status or "").strip().lower()[:16],
    )


def _appeal_is_current(operation, stages, latest, baselines, country_id) -> bool:
    """True when this pull would write the same operation and the same stages."""
    if operation is None or not baselines:
        return False
    latest_row = next((row for row in baselines.values() if row.is_latest), None)
    if latest_row is None or latest_row.go_stage_id != latest["go_stage_id"]:
        return False
    for stage in stages:
        stored = baselines.get(stage["go_stage_id"])
        if stored is None or _stage_fingerprint(stage) != _baseline_fingerprint(stored):
            return False
    return _header_fingerprint(latest, country_id) == _operation_fingerprint(operation)


def _load_known(appeal_codes: list[str]) -> tuple[dict[str, DrefOperation], dict[int, dict[str, DrefBaseline]]]:
    if not appeal_codes:
        return {}, {}
    operations = {
        row.appeal_code: row
        for row in DrefOperation.query.filter(DrefOperation.appeal_code.in_(appeal_codes)).all()
    }
    baselines: dict[int, dict[str, DrefBaseline]] = defaultdict(dict)
    op_ids = [row.id for row in operations.values()]
    if not op_ids:
        return operations, baselines
    for row in DrefBaseline.query.filter(DrefBaseline.operation_id.in_(op_ids)).all():
        baselines[row.operation_id][row.go_stage_id] = row
    return operations, baselines


def _country_ids(iso3s: set[str]) -> dict[str, int]:
    wanted = {code.upper() for code in iso3s if code}
    if not wanted:
        return {}
    found: dict[str, int] = {}
    for country in Country.query.filter(db.func.upper(Country.iso3).in_(list(wanted))).all():
        code = (country.iso3 or "").upper()
        if code and code not in found:
            found[code] = int(country.id)
    return found


def _write_appeal(operation, stages, latest, baselines, today) -> bool:
    """Save one appeal: header, stages, plan, workflow, and project. True when it is new."""
    previous = None
    current = next((row for row in baselines.values() if row.is_latest), None)
    if current is not None:
        previous = stage_signature(
            {
                "total_approved": current.total_approved,
                "end_date": current.end_date,
                "sectors": list(current.sectors or []),
                "application": current.application,
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
    from plugins.emergency_operations_monitoring.services.project_link import sync_operation_project

    sync_operation_project(operation)
    return was_created


def apply_rows(rows: list[dict], today: date | None = None, *, progress=None, should_stop=None) -> dict:
    """Upsert operations from parsed or raw dref3 rows. Commits once.

    An appeal whose header and stages already match what is stored is left as it
    is, including its plan and project. A new stage, or any change in the header,
    amounts, dates, sectors, or application, is saved.
    """
    today = today or date.today()
    parsed_rows = []
    for row in rows:
        parsed = row if "go_stage_id" in row and "sectors" in row else parse_stage(row)
        if parsed:
            parsed_rows.append(parsed)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for parsed in parsed_rows:
        if not is_monitored_appeal(parsed.get("appeal_type") or ""):
            continue
        grouped[parsed["appeal_code"]].append(parsed)

    operations, baselines_by_op = _load_known(list(grouped))
    country_ids = _country_ids(
        {stage.get("country_iso3") or "" for stages in grouped.values() for stage in stages}
    )
    created = 0
    updated = 0
    unchanged = 0
    failed: list[str] = []
    total = len(grouped)
    if progress:
        progress(
            {
                "stage": "applying",
                "message": "Saving operations (%(current)s of %(total)s).",
                "message_vars": {"current": 0, "total": total},
                "current": 0,
                "total": total,
                "percent": 75.0,
            }
        )
    for index, (appeal_code, stages) in enumerate(grouped.items()):
        if should_stop and should_stop():
            raise GoSyncCancelled()
        latest = _latest_stage(stages)
        if not is_monitored_appeal(latest.get("appeal_type") or ""):
            continue
        latest["operation_status"] = operation_status_for(stages, latest)
        operation = operations.get(appeal_code)
        if latest.get("from_appeal_feed"):
            _carry_event_details(latest, operation)
        baselines = baselines_by_op.get(operation.id, {}) if operation is not None else {}
        if latest.get("from_appeal_feed") and not isinstance(latest.get("application"), dict):
            # The emergency page could not be read this time. Keep the text stored from an earlier pull.
            stored = baselines.get(latest["go_stage_id"])
            if stored is not None and isinstance(stored.application, dict):
                latest["application"] = stored.application
        if _appeal_is_current(operation, stages, latest, baselines, country_ids.get((latest.get("country_iso3") or "").upper())):
            unchanged += 1
        else:
            try:
                with db.session.begin_nested():
                    was_created = _write_appeal(operation, stages, latest, baselines, today)
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception:
                logger.warning("Emergency Operations GO sync could not save %s", appeal_code, exc_info=True)
                failed.append(appeal_code)
        if progress and total:
            progress(
                {
                    "stage": "applying",
                    "message": "Saving operations (%(current)s of %(total)s).",
                    "message_vars": {"current": index + 1, "total": total},
                    "current": index + 1,
                    "total": total,
                    "percent": round(75 + 24 * (index + 1) / total, 1),
                }
            )
    if should_stop and should_stop():
        raise GoSyncCancelled()
    removed = _drop_unsupported_operations()
    try:
        with db.session.begin_nested():
            backfill_appeal_indicators()
    except Exception:
        logger.warning("Emergency Operations GO sync could not add the bank indicators to appeal plans", exc_info=True)
    db.session.commit()
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
        "failed": len(failed),
        "failed_codes": failed[:20],
        "appeals": len(grouped),
        "emergency_appeals": sum(
            1 for stages in grouped.values() if any(item.get("from_appeal_feed") for item in stages)
        ),
    }


def _latest_stage(stages: list[dict]) -> dict:
    """The stage the operation follows. An Emergency Appeal read from the appeal API always wins.

    The dref3 rows that share its code are the loan DREF. They stay as earlier stages, so their
    application text is still available, but their sector budgets are not the appeal's.
    """
    appeal = next((item for item in stages if item.get("from_appeal_feed")), None)
    if appeal is not None:
        for item in stages:
            item["is_latest_stage"] = item is appeal
        return appeal
    latest = next((item for item in stages if item.get("is_latest_stage")), None)
    if latest is None:
        latest = max(stages, key=lambda item: (item.get("date_of_approval") or date.min, item["go_stage_id"]))
    return latest


def _carry_event_details(latest: dict, operation: DrefOperation | None) -> None:
    """Keep the areas, event date, and people affected already stored when this pull could not read them.

    They come from the emergency page, which can be slow or missing. Without this, one failed page
    would blank the header and the next sync would write it back.
    """
    if operation is None:
        return
    if not latest.get("districts") and operation.districts:
        latest["districts"] = operation.districts
    if latest.get("date_of_disaster") is None and operation.date_of_disaster is not None:
        latest["date_of_disaster"] = operation.date_of_disaster
    if latest.get("people_affected") is None and operation.people_affected is not None:
        latest["people_affected"] = operation.people_affected


def _drop_unsupported_operations() -> int:
    """Remove operations of a type this plugin does not monitor, such as an International Appeal."""
    stale = [row for row in DrefOperation.query.all() if not is_monitored_appeal(row.appeal_type)]
    if not stale:
        return 0
    ids = [row.id for row in stale]
    # This cascades to plans, reports, and drafts, so name what is removed.
    logger.warning(
        "Emergency Operations GO sync is removing unsupported operations with their monitoring data: %s",
        ", ".join(f"{row.appeal_code} ({row.appeal_type or 'no type'})" for row in stale),
    )
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
        headers={"Accept": "application/json", "User-Agent": "IFRC-Network-Databank/emergency-operations"},
    )
    response.raise_for_status()
    return response.json()


@contextmanager
def isolated_session():
    """Commit progress without flushing the sync transaction on ``db.session``."""
    session = sessionmaker(bind=db.engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def _single_sync():
    """One GO sync at a time, on this process and across app instances.

    The advisory lock sits on its own autocommit connection. The sync commits
    the request session many times, and that must not drop the lock or leave it
    on a pooled connection.
    """
    if not _THREAD_LOCK.acquire(blocking=False):
        raise GoSyncBusy()
    lock_conn = None
    try:
        bind = db.session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            from sqlalchemy import text

            lock_conn = db.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            acquired = bool(
                lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": int(DREF_GO_SYNC_LOCK_ID)},
                ).scalar()
            )
            if not acquired:
                lock_conn.close()
                lock_conn = None
                raise GoSyncBusy()
        yield
    finally:
        try:
            if lock_conn is not None:
                from sqlalchemy import text

                try:
                    lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": int(DREF_GO_SYNC_LOCK_ID)},
                    )
                finally:
                    lock_conn.close()
        finally:
            _THREAD_LOCK.release()


def go_sync_lock_held() -> bool:
    """True when this process or another instance is inside a GO sync."""
    if _THREAD_LOCK.locked():
        return True
    try:
        bind = db.session.get_bind()
    except Exception:
        return False
    if bind is None or bind.dialect.name != "postgresql":
        return False
    from sqlalchemy import text

    classid = (DREF_GO_SYNC_LOCK_ID >> 32) & 0xFFFFFFFF
    objid = DREF_GO_SYNC_LOCK_ID & 0xFFFFFFFF
    try:
        return bool(
            db.session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_locks
                        WHERE locktype = 'advisory'
                          AND classid = :classid
                          AND objid = :objid
                    )
                    """
                ),
                {"classid": int(classid), "objid": int(objid)},
            ).scalar()
        )
    except Exception:
        logger.debug("Emergency Operations GO sync lock lookup failed", exc_info=True)
        return False


def _touch_running_log(log_id: int, message: str, *, force: bool = False) -> None:
    now = time.time()
    if not force and now - _log_touch_at.get(int(log_id), 0.0) < 1.0:
        return
    _log_touch_at[int(log_id)] = now
    try:
        with isolated_session() as session:
            row = session.get(DrefSyncLog, int(log_id))
            if row is not None and row.status == "running":
                row.message = (message or "")[:1000]
    except Exception:
        logger.debug("DREF sync log progress update failed", exc_info=True)


def _finish_log(log_id: int, status: str, message: str, created: int = 0, updated: int = 0) -> None:
    with isolated_session() as session:
        row = session.get(DrefSyncLog, int(log_id))
        if row is None:
            return
        row.status = status[:16]
        row.message = (message or "")[:1000]
        row.finished_at = utcnow()
        row.created_count = int(created or 0)
        row.updated_count = int(updated or 0)
    _log_touch_at.pop(int(log_id), None)
    stale = db.session.get(DrefSyncLog, int(log_id))
    if stale is not None:
        db.session.expire(stale)


def _emit(progress, should_stop, log_id: int, payload: dict) -> None:
    if should_stop and should_stop():
        raise GoSyncCancelled()
    message = str(payload.get("message") or "")
    variables = payload.get("message_vars") or {}
    try:
        text = message % variables if variables else message
    except Exception:
        text = message
    _touch_running_log(log_id, text)
    if progress:
        progress(payload)


def stamp_stored_applications(rows: list[dict]) -> int:
    """Copy a stored plan onto feed rows so an unchanged stage is not downloaded again.

    A new stage id, or a stage that has no stored plan, is left for the emergency fetch.
    """
    pending = []
    for row in rows:
        # An appeal has no interventions to reuse, and its event summary changes, so it is read every time.
        if not isinstance(row, dict) or isinstance(row.get("application"), dict) or row.get("appeal_feed"):
            continue
        stage_id = str(row.get("id") or "").strip()
        if stage_id:
            pending.append((row, stage_id))
    if not pending:
        return 0
    stored: dict[str, dict] = {}
    stage_ids = list({stage_id for _row, stage_id in pending})
    for baseline in DrefBaseline.query.filter(
        DrefBaseline.go_stage_id.in_(stage_ids),
        DrefBaseline.application.isnot(None),
    ).all():
        application = baseline.application
        # A plan stored before the written application was kept is read once more.
        if (
            isinstance(application, dict)
            and application.get("interventions")
            and application.get("narrative_version") == NARRATIVE_VERSION
        ):
            stored[baseline.go_stage_id] = application
    reused = 0
    for row, stage_id in pending:
        if stage_id not in stored:
            continue
        row["application"] = stored[stage_id]
        reused += 1
    return reused


def completion_progress(summary: dict) -> dict:
    """Message the status poll shows when the sync finishes."""
    created = int(summary.get("created") or 0)
    updated = int(summary.get("updated") or 0)
    unchanged = int(summary.get("unchanged") or 0)
    variables = {"created": created, "updated": updated, "unchanged": unchanged}
    if unchanged:
        message = "Synced %(created)s new and %(updated)s updated operations. %(unchanged)s were already current."
    else:
        message = "Synced %(created)s new and %(updated)s updated operations."
    return {"message": message, "message_vars": variables}


def _success_text(summary: dict, applications: dict) -> str:
    message = f"Synced {summary['appeals']} appeal(s)"
    if summary.get("emergency_appeals"):
        message += f", {summary['emergency_appeals']} of them Emergency Appeals"
    message += "."
    if summary.get("appeals_unavailable"):
        message += " The Emergency Appeals could not be read from GO, so stored ones were left as they are."
    if summary.get("loans_held"):
        message += f" Kept {summary['loans_held']} loan stage(s) of stored Emergency Appeals out of this pull."
    if summary.get("unchanged"):
        message += f" {summary['unchanged']} were already up to date."
    if applications.get("reused"):
        message += f" Reused {applications['reused']} stored application(s)."
    if applications.get("with_plan"):
        message += f" Read the application for {applications['with_plan']} emergency page(s)."
    if applications.get("missing"):
        message += f" {applications['missing']} emergency page(s) are not published."
    if summary.get("removed"):
        message += f" Removed {summary['removed']} unsupported operation(s)."
    if summary.get("failed"):
        codes = ", ".join(summary.get("failed_codes") or [])
        message += f" {summary['failed']} appeal(s) could not be saved and were skipped: {codes}."
    if summary.get("truncated"):
        message += " The GO feed is longer than one sync reads, so some appeals were not read."
    return message


def _run_sync(http_get, operation_status, progress, should_stop, log_id: int) -> dict:
    def report(payload: dict) -> None:
        _emit(progress, should_stop, log_id, payload)

    getter = http_get or _default_http_get
    rows = fetch_rows(
        getter,
        go_base_url(),
        operation_status=operation_status,
        progress=report,
        should_stop=should_stop,
    )
    from plugins.emergency_operations_monitoring.services.go_application import attach_applications

    appeals_unavailable = False
    settings = emergency_appeal_settings()
    if not settings["enabled"]:
        # Switched off: Emergency Appeals are neither read nor changed. Stored ones stay as they are.
        rows[:] = [row for row in rows if not is_emergency_appeal(row.get("appeal_type") or "")]
    else:
        try:
            rows.extend(
                fetch_appeal_rows(
                    getter,
                    go_appeal_url(),
                    closed_since_year=settings["closed_since_year"],
                    progress=report,
                    should_stop=should_stop,
                )
            )
        except GoSyncCancelled:
            raise
        except Exception as exc:
            # The DREF pull still stands. Stored appeals are left alone rather than rebuilt from a partial read.
            logger.warning("Emergency Operations GO sync could not read Emergency Appeals: %s", exc)
            appeals_unavailable = True
    # With the appeal feed off or unreachable, the loan stages of a stored appeal must not take over.
    loans_held = _hold_stored_appeals(rows)

    reused = stamp_stored_applications(rows)
    applications = attach_applications(rows, http_get, progress=report, should_stop=should_stop)
    applications["reused"] = reused
    if applications.get("cancelled"):
        raise GoSyncCancelled()
    summary = apply_rows(rows, progress=report, should_stop=should_stop)
    summary["truncated"] = bool(getattr(rows, "truncated", False))
    summary["appeals_unavailable"] = appeals_unavailable
    summary["loans_held"] = loans_held
    if summary["failed"] and not (summary["created"] or summary["updated"] or summary["unchanged"]):
        raise RuntimeError(f"Every appeal failed to save: {', '.join(summary['failed_codes'])}")
    message = _success_text(summary, applications)
    _finish_log(log_id, "ok", message, summary["created"], summary["updated"])
    if progress:
        finished = completion_progress(summary)
        progress(
            {
                "stage": "completed",
                "message": finished["message"],
                "message_vars": finished["message_vars"],
                "current": summary["appeals"],
                "total": summary["appeals"],
                "percent": 100.0,
                "summary": {
                    "created": summary["created"],
                    "updated": summary["updated"],
                    "unchanged": summary["unchanged"],
                    "removed": summary["removed"],
                    "appeals": summary["appeals"],
                },
            }
        )
    summary["log_id"] = log_id
    return summary


def sync_from_go(http_get=None, *, operation_status: str | None = None, progress=None, should_stop=None) -> dict:
    """Pull the public dref3 feed. Raises ``GoSyncBusy`` when a sync is already running."""
    with _single_sync():
        log = DrefSyncLog(status="running", message="Waiting to start the GO sync.")
        db.session.add(log)
        db.session.commit()
        log_id = int(log.id)
        try:
            return _run_sync(http_get, operation_status, progress, should_stop, log_id)
        except GoSyncCancelled:
            db.session.rollback()
            _finish_log(log_id, "cancelled", "GO sync was cancelled.")
            raise
        except Exception as exc:
            logger.warning("Emergency Operations GO sync failed: %s", exc)
            db.session.rollback()
            _finish_log(log_id, "error", str(exc)[:1000])
            raise
