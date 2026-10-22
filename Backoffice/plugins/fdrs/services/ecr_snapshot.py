"""Saved Everyone Counts calculation.

The explorer tab used to run the FDRS panel query and the chapter build inside
the request. That exceeds the database statement timeout and the gateway limit
that closes the browser after about 30 seconds. The page now reads one saved
JSON document. Refresh starts the same calculation on a background thread and
keeps the previous document until the new one is stored.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.utils.datetime_helpers import ensure_utc, naive_utc, utcnow
from plugins.fdrs.models import EveryoneCountsSnapshot

logger = logging.getLogger(__name__)

STATUS_EMPTY = "empty"
STATUS_BUILDING = "building"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

# A build that never writes again is treated as abandoned so Refresh can run.
BUILD_STALE_AFTER = timedelta(minutes=20)
BUILD_STATEMENT_TIMEOUT_MS = 180_000

FAILURE_MESSAGE = "The latest calculation did not finish. Refresh figures to try again."
STALE_MESSAGE = "The calculation stopped before it finished. Refresh figures to try again."


def read_snapshot(template_id: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the saved analysis, if any, and the status shown on the page."""
    row = EveryoneCountsSnapshot.query.filter_by(template_id=int(template_id)).first()
    if row is None:
        return None, _empty_meta()
    payload = dict(row.payload) if isinstance(row.payload, dict) else None
    return payload, snapshot_meta(row)


def request_rebuild(
    template_id: int,
    user_id: int | None,
    *,
    refresh_external: bool = False,
) -> dict[str, Any]:
    """Claim a build and start it, unless a recent build is already running."""
    from flask import current_app

    template_id = int(template_id)
    row = _locked_row(template_id)
    if row.status == STATUS_BUILDING and not _is_stale(row):
        meta = snapshot_meta(row)
        db.session.commit()
        return {"started": False, **meta}

    token = uuid.uuid4().hex
    row.status = STATUS_BUILDING
    row.build_token = token
    row.started_at = naive_utc(utcnow())
    row.error = None
    row.built_by_user_id = int(user_id) if user_id else None
    meta = snapshot_meta(row)
    db.session.commit()
    start_snapshot_build(
        current_app._get_current_object(),
        template_id,
        token,
        refresh_external=refresh_external,
    )
    return {"started": True, **meta}


def start_snapshot_build(
    app,
    template_id: int,
    token: str,
    *,
    refresh_external: bool = False,
) -> None:
    """Run the calculation on a daemon thread so the request can return."""
    thread = threading.Thread(
        target=_build_worker,
        args=(app, int(template_id), token, bool(refresh_external)),
        name=f"ecr-snapshot-{int(template_id)}",
        daemon=True,
    )
    thread.start()


def complete_snapshot(template_id: int, token: str, payload: dict[str, Any]) -> bool:
    """Store a finished calculation when this build is still the current one."""
    ready = _json_ready(payload)
    row = _locked_existing(int(template_id))
    if row is None or row.build_token != token:
        db.session.commit()
        return False
    finished = naive_utc(utcnow())
    row.payload = ready
    row.status = STATUS_READY
    row.error = None
    row.built_at = finished
    row.finished_at = finished
    db.session.commit()
    return True


def fail_snapshot(template_id: int, token: str) -> bool:
    """Mark this build failed without removing a calculation that already exists."""
    row = _locked_existing(int(template_id))
    if row is None or row.build_token != token:
        db.session.commit()
        return False
    row.status = STATUS_FAILED
    row.error = FAILURE_MESSAGE
    row.finished_at = naive_utc(utcnow())
    db.session.commit()
    return True


def snapshot_meta(row: EveryoneCountsSnapshot) -> dict[str, Any]:
    stale = row.status == STATUS_BUILDING and _is_stale(row)
    status = STATUS_FAILED if stale else row.status
    error = row.error
    if stale:
        error = error or STALE_MESSAGE
    return {
        "status": status,
        "busy": row.status == STATUS_BUILDING and not stale,
        "built_at": _iso(row.built_at),
        "started_at": _iso(row.started_at),
        "error": error,
    }


def relax_statement_timeout(timeout_ms: int = BUILD_STATEMENT_TIMEOUT_MS) -> None:
    """Allow the panel query to run longer than the request statement timeout.

    ``SET LOCAL`` applies only to this transaction, so the pooled connection
    keeps the normal timeout for the next request.
    """
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    db.session.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": str(int(timeout_ms))},
    )


def _build_worker(app, template_id: int, token: str, refresh_external: bool) -> None:
    import time

    from plugins.fdrs.services.ecr_analysis import load_everyone_counts

    with app.app_context():
        started = time.perf_counter()
        try:
            relax_statement_timeout()
            payload = load_everyone_counts(template_id, refresh_external=refresh_external)
            if complete_snapshot(template_id, token, payload):
                logger.info(
                    "Everyone Counts snapshot saved template=%s seconds=%.1f",
                    template_id,
                    time.perf_counter() - started,
                )
        except Exception:
            logger.exception("Everyone Counts snapshot failed template=%s", template_id)
            db.session.rollback()
            try:
                fail_snapshot(template_id, token)
            except Exception:
                logger.exception(
                    "Everyone Counts snapshot failure was not recorded template=%s",
                    template_id,
                )
                db.session.rollback()
        finally:
            db.session.remove()


def _empty_meta() -> dict[str, Any]:
    return {
        "status": STATUS_EMPTY,
        "busy": False,
        "built_at": None,
        "started_at": None,
        "error": None,
    }


def _locked_row(template_id: int) -> EveryoneCountsSnapshot:
    row = _lock_query(
        EveryoneCountsSnapshot.query.filter_by(template_id=template_id)
    ).first()
    if row is not None:
        return row
    row = EveryoneCountsSnapshot(template_id=template_id, status=STATUS_EMPTY)
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        row = _lock_query(
            EveryoneCountsSnapshot.query.filter_by(template_id=template_id)
        ).one()
    return row


def _locked_existing(template_id: int) -> EveryoneCountsSnapshot | None:
    return _lock_query(
        EveryoneCountsSnapshot.query.filter_by(template_id=template_id)
    ).first()


def _lock_query(query):
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return query.with_for_update()
    return query


def _is_stale(row: EveryoneCountsSnapshot) -> bool:
    started = _as_utc(row.started_at)
    if started is None:
        return True
    return utcnow() - started >= BUILD_STALE_AFTER


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value)


def _iso(value: datetime | None) -> str | None:
    parsed = _as_utc(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def _json_ready(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("saved", None)
    cleaned.pop("success", None)
    encoded = json.dumps(cleaned, allow_nan=False, default=_reject_value)
    ready = json.loads(encoded)
    if not isinstance(ready, dict):
        raise TypeError("Everyone Counts snapshot must be a JSON object")
    return ready


def _reject_value(value: Any) -> None:
    raise TypeError(f"Everyone Counts snapshot is not JSON: {type(value).__name__}")
