#!/usr/bin/env python3
"""Restore Jan-Jun 2026 bilateral Financial Overview matrices (template 23, item 1433).

The 18 Sep 2026 UPR Master import replaced partner-country rows on assigned_form 34
with one row for the reporting society, and deleted the matrix on three assignments.
The template 33 restore script does not touch these rows.

This script only writes form_item 1433, and for the three deleted assignments the
workflow columns the import cleared. It does not delete rows and does not touch
staff (1434), comments, published snapshots, or any other template.

A row is written only when live data still matches the 18 Sep fingerprint.
Default is dry-run. ``--commit`` requires ``--force``.

    azure_webapp_tools.bat prod script ops/restore_t23_bilateral_matrix_1433.py "--dry-run --verbose"
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("restore_t23_bilateral")

ASSIGNED_FORM_ID = 34
TEMPLATE_ID = 23
PERIOD_NAME = "Jan-Jun 2026"
FORM_ITEM_ID = 1433
IMPORT_AT = datetime(2026, 9, 18, 10, 36, 4)

SNAPSHOT_KEYS = (
    "value",
    "numeric_value",
    "disagg_data",
    "disagg_type",
    "data_not_available",
    "not_applicable",
)

STATUS_KEYS = (
    "status",
    "status_timestamp",
    "submitted_at",
    "submitted_by_user_id",
    "approved_by_user_id",
    "sent_for_review_by_user_id",
    "sent_for_review_at",
    "status_changed_by_user_id",
)


def _ensure_app_importable() -> None:
    app_root = Path("/app")
    if (app_root / "run.py").is_file() and (app_root / "app").is_dir():
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))
        return
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)


_ensure_app_importable()


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("Z", "")
    if text.endswith("+00:00"):
        text = text[:-6]
    return datetime.fromisoformat(text)


def _norm_num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    number = float(value)
    if number.is_integer():
        return float(int(number))
    return number


def _norm_disagg(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshots_equal(current: dict[str, Any], expected: dict[str, Any]) -> bool:
    if (current.get("value") or None) != (expected.get("value") or None):
        return False
    if _norm_num(current.get("numeric_value")) != _norm_num(expected.get("numeric_value")):
        return False
    if _norm_disagg(current.get("disagg_data")) != _norm_disagg(expected.get("disagg_data")):
        return False
    if (current.get("disagg_type") or None) != (expected.get("disagg_type") or None):
        return False
    if bool(current.get("data_not_available")) != bool(expected.get("data_not_available")):
        return False
    if bool(current.get("not_applicable")) != bool(expected.get("not_applicable")):
        return False
    return True


def status_equal(current: dict[str, Any], expected: dict[str, Any]) -> bool:
    if str(current.get("status") or "") != str(expected.get("status") or ""):
        return False
    for key in STATUS_KEYS:
        if key == "status":
            continue
        if key.endswith("_at") or key == "status_timestamp":
            if _parse_ts(current.get(key)) != _parse_ts(expected.get(key)):
                return False
        else:
            left = current.get(key)
            right = expected.get(key)
            if left is not None:
                left = int(left)
            if right is not None:
                right = int(right)
            if left != right:
                return False
    return True


def _cell_count(disagg: Any) -> int:
    return len(disagg) if isinstance(disagg, dict) else 0


def _row_count(disagg: Any) -> int:
    if not isinstance(disagg, dict):
        return 0
    return len({str(key).split("_", 1)[0] for key in disagg if isinstance(key, str) and not key.startswith("_")})


def load_payload(path: Optional[str] = None) -> dict[str, Any]:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    here = Path(__file__).resolve().parent
    stem = here / "restore_t23_bilateral_matrix_1433.payload.json"
    candidates.extend([
        stem,
        Path("/tmp/restore_t23_bilateral_matrix_1433.payload.json"),
    ])
    for candidate in candidates:
        if candidate.is_file():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            logger.info("Loaded payload from %s", candidate)
            return payload
    if not PAYLOAD_GZ_B64.strip():
        raise SystemExit("No restore payload found.")
    payload = json.loads(gzip.decompress(base64.b64decode(PAYLOAD_GZ_B64)))
    logger.info("Loaded embedded payload")
    return payload


def _live_matrix_notes(aes_ids: set[int]) -> dict[int, str]:
    """Informational only. The matrix fingerprint is the write lock."""
    from app.models.system import EntityActivityLog

    if not aes_ids:
        return {}
    rows = (
        EntityActivityLog.query.filter(EntityActivityLog.activity_type == "data_update")
        .filter(EntityActivityLog.assignment_id.in_(aes_ids))
        .filter(EntityActivityLog.timestamp > IMPORT_AT)
        .order_by(EntityActivityLog.timestamp.asc())
        .all()
    )
    notes: dict[int, str] = {}
    for row in rows:
        aes_id = int(row.assignment_id)
        notes[aes_id] = f"data_update user_id={row.user_id} at {row.timestamp}"
    return notes


def _snapshot_from_model(row: Any) -> dict[str, Any]:
    return {key: getattr(row, key) for key in SNAPSHOT_KEYS}


def _status_from_model(row: Any) -> dict[str, Any]:
    status = row.status.value if hasattr(row.status, "value") else str(row.status)
    return {
        "status": status,
        "status_timestamp": row.status_timestamp,
        "submitted_at": row.submitted_at,
        "submitted_by_user_id": row.submitted_by_user_id,
        "approved_by_user_id": row.approved_by_user_id,
        "sent_for_review_by_user_id": row.sent_for_review_by_user_id,
        "sent_for_review_at": row.sent_for_review_at,
        "status_changed_by_user_id": row.status_changed_by_user_id,
    }


def _json_param(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def run_restore(payload: dict[str, Any], *, commit: bool, aes_filter: Optional[set[int]], verbose: bool) -> int:
    from sqlalchemy import text

    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.forms import FormData

    meta = payload["meta"]
    if meta.get("form_item_id") != FORM_ITEM_ID or meta.get("assigned_form_id") != ASSIGNED_FORM_ID:
        raise SystemExit("Payload is not the bilateral item 1433 restore.")

    assigned = db.session.get(AssignedForm, ASSIGNED_FORM_ID)
    if assigned is None or int(assigned.template_id) != TEMPLATE_ID or assigned.period_name != PERIOD_NAME:
        raise SystemExit(
            f"assigned_form {ASSIGNED_FORM_ID} is not template {TEMPLATE_ID} period {PERIOD_NAME!r}. Aborting."
        )

    updates = list(payload.get("updates") or [])
    inserts = list(payload.get("inserts") or [])
    if aes_filter is not None:
        updates = [row for row in updates if int(row["aes_id"]) in aes_filter]
        inserts = [row for row in inserts if int(row["aes_id"]) in aes_filter]

    aes_ids = {int(row["aes_id"]) for row in updates + inserts}
    owned = {
        int(row.id)
        for row in AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.id.in_(aes_ids),
            AssignmentEntityStatus.assigned_form_id == ASSIGNED_FORM_ID,
        ).all()
    }
    notes = _live_matrix_notes(aes_ids)
    stats = {
        "would_update": 0,
        "would_insert": 0,
        "would_restore_status": 0,
        "skipped": 0,
    }

    def skip(reason: str, row: dict[str, Any]) -> None:
        stats["skipped"] += 1
        logger.info("SKIP %s %s aes=%s %s", reason, row.get("iso3"), row.get("aes_id"), row.get("country"))

    try:
        for row in updates:
            aes_id = int(row["aes_id"])
            if aes_id not in owned:
                skip("wrong_assignment", row)
                continue
            if _cell_count(row["restore"].get("disagg_data")) <= _cell_count(row["expected"].get("disagg_data")):
                skip("restore_not_richer", row)
                continue
            current = FormData.query.filter_by(
                assignment_entity_status_id=aes_id,
                form_item_id=FORM_ITEM_ID,
            ).one_or_none()
            if current is None:
                skip("missing_row", row)
                continue
            if not snapshots_equal(_snapshot_from_model(current), row["expected"]):
                skip("optimistic_lock", row)
                continue
            note = notes.get(aes_id)
            logger.info(
                "UPDATE %s aes=%s %s form_data=%s cells %s -> %s%s",
                row.get("iso3"),
                aes_id,
                row.get("country"),
                current.id,
                _cell_count(row["expected"].get("disagg_data")),
                _cell_count(row["restore"].get("disagg_data")),
                f" note={note}" if note else "",
            )
            if verbose:
                logger.info("  submitted_at %s -> %s", current.submitted_at, row["restore"].get("submitted_at"))
            restore = row["restore"]
            result = db.session.execute(
                text(
                    """
                    UPDATE form_data
                    SET value = :value,
                        numeric_value = :numeric_value,
                        disagg_data = CAST(:disagg AS json),
                        disagg_type = :disagg_type,
                        data_not_available = :data_not_available,
                        not_applicable = :not_applicable,
                        submitted_at = :submitted_at
                    WHERE id = :id
                      AND assignment_entity_status_id = :aes_id
                      AND form_item_id = :form_item_id
                      AND disagg_data::jsonb = CAST(:expected_disagg AS jsonb)
                    """
                ),
                {
                    "value": restore.get("value"),
                    "numeric_value": restore.get("numeric_value"),
                    "disagg": _json_param(restore.get("disagg_data")),
                    "disagg_type": restore.get("disagg_type"),
                    "data_not_available": bool(restore.get("data_not_available")),
                    "not_applicable": bool(restore.get("not_applicable")),
                    "submitted_at": _parse_ts(restore.get("submitted_at")),
                    "id": int(current.id),
                    "aes_id": aes_id,
                    "form_item_id": FORM_ITEM_ID,
                    "expected_disagg": _json_param(row["expected"].get("disagg_data")),
                },
            )
            if result.rowcount != 1:
                skip("sql_lock", row)
                continue
            stats["would_update"] += 1

        for row in inserts:
            aes_id = int(row["aes_id"])
            if aes_id not in owned:
                skip("wrong_assignment", row)
                continue
            current = FormData.query.filter_by(
                assignment_entity_status_id=aes_id,
                form_item_id=FORM_ITEM_ID,
            ).one_or_none()
            if current is not None:
                skip("row_already_present", row)
                continue
            restore = row["restore"]
            if _row_count(restore.get("disagg_data")) < 1:
                skip("empty_restore", row)
                continue
            logger.info(
                "INSERT %s aes=%s %s rows=%s",
                row.get("iso3"),
                aes_id,
                row.get("country"),
                _row_count(restore.get("disagg_data")),
            )
            result = db.session.execute(
                text(
                    """
                    INSERT INTO form_data (
                        assignment_entity_status_id, form_item_id, value, numeric_value,
                        disagg_data, disagg_type, data_not_available, not_applicable,
                        submitted_at, created_at, created_by_user_id
                    )
                    SELECT :aes_id, :form_item_id, :value, :numeric_value,
                           CAST(:disagg AS json), :disagg_type, :data_not_available, :not_applicable,
                           :submitted_at, :created_at, :created_by_user_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM form_data
                        WHERE assignment_entity_status_id = :aes_id
                          AND form_item_id = :form_item_id
                    )
                    """
                ),
                {
                    "aes_id": aes_id,
                    "form_item_id": FORM_ITEM_ID,
                    "value": restore.get("value"),
                    "numeric_value": restore.get("numeric_value"),
                    "disagg": _json_param(restore.get("disagg_data")),
                    "disagg_type": restore.get("disagg_type"),
                    "data_not_available": bool(restore.get("data_not_available")),
                    "not_applicable": bool(restore.get("not_applicable")),
                    "submitted_at": _parse_ts(restore.get("submitted_at")),
                    "created_at": _parse_ts(restore.get("created_at")),
                    "created_by_user_id": restore.get("created_by_user_id"),
                },
            )
            if result.rowcount != 1:
                skip("insert_conflict", row)
                continue
            stats["would_insert"] += 1

            expected_status = row.get("status_expected")
            before_status = row.get("status_before")
            if not expected_status or not before_status:
                continue
            if str(before_status.get("status")) == str(expected_status.get("status")):
                continue
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            if aes is None or not status_equal(_status_from_model(aes), expected_status):
                skip("status_lock", row)
                continue
            logger.info(
                "STATUS %s aes=%s %s -> %s",
                row.get("iso3"),
                aes_id,
                expected_status.get("status"),
                before_status.get("status"),
            )
            status_result = db.session.execute(
                text(
                    """
                    UPDATE assignment_entity_status
                    SET status = CAST(:status AS assignmententitystatus),
                        status_timestamp = :status_timestamp,
                        submitted_at = :submitted_at,
                        submitted_by_user_id = :submitted_by_user_id,
                        approved_by_user_id = :approved_by_user_id,
                        sent_for_review_by_user_id = :sent_for_review_by_user_id,
                        sent_for_review_at = :sent_for_review_at,
                        status_changed_by_user_id = :status_changed_by_user_id
                    WHERE id = :id
                      AND assigned_form_id = :assigned_form_id
                      AND status = CAST(:expected_status AS assignmententitystatus)
                      AND submitted_at IS NOT DISTINCT FROM :expected_submitted_at
                      AND submitted_by_user_id IS NOT DISTINCT FROM :expected_submitted_by
                    """
                ),
                {
                    "status": before_status.get("status"),
                    "status_timestamp": _parse_ts(before_status.get("status_timestamp")),
                    "submitted_at": _parse_ts(before_status.get("submitted_at")),
                    "submitted_by_user_id": before_status.get("submitted_by_user_id"),
                    "approved_by_user_id": before_status.get("approved_by_user_id"),
                    "sent_for_review_by_user_id": before_status.get("sent_for_review_by_user_id"),
                    "sent_for_review_at": _parse_ts(before_status.get("sent_for_review_at")),
                    "status_changed_by_user_id": before_status.get("status_changed_by_user_id"),
                    "id": aes_id,
                    "assigned_form_id": ASSIGNED_FORM_ID,
                    "expected_status": expected_status.get("status"),
                    "expected_submitted_at": _parse_ts(expected_status.get("submitted_at")),
                    "expected_submitted_by": expected_status.get("submitted_by_user_id"),
                },
            )
            if status_result.rowcount != 1:
                skip("status_sql_lock", row)
                continue
            stats["would_restore_status"] += 1

        if commit:
            db.session.commit()
            logger.info("COMMITTED")
        else:
            db.session.rollback()
            logger.info("DRY-RUN rolled back; no writes")
    except Exception:
        db.session.rollback()
        raise

    logger.info("Totals: %s", stats)
    return 0 if stats["skipped"] == 0 or not commit else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default).")
    parser.add_argument("--commit", action="store_true", help="Write matching rows. Requires --force.")
    parser.add_argument("--force", action="store_true", help="Required with --commit.")
    parser.add_argument("--payload", help="Payload JSON path. Defaults to the embedded snapshot.")
    parser.add_argument("--aes-id", type=int, action="append", dest="aes_ids")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--summary-only", action="store_true", help="Print payload counts and exit.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    payload = load_payload(args.payload)
    meta = payload["meta"]
    logger.info(
        "Payload %s template=%s period=%s item=%s updates=%s inserts=%s",
        meta.get("kind"),
        meta.get("template_id"),
        meta.get("period_name"),
        meta.get("form_item_id"),
        len(payload.get("updates") or []),
        len(payload.get("inserts") or []),
    )
    if args.summary_only:
        return 0
    if args.commit and not args.force:
        logger.error("--commit requires --force")
        return 2
    if args.commit and args.dry_run:
        logger.error("Pass only one of --dry-run and --commit")
        return 2

    from app import create_app

    app = create_app()
    with app.app_context():
        return run_restore(
            payload,
            commit=bool(args.commit),
            aes_filter=set(args.aes_ids) if args.aes_ids else None,
            verbose=bool(args.verbose),
        )


# gzip+base64 of restore_t23_bilateral_matrix_1433.payload.json
PAYLOAD_GZ_B64 = """
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
"""

if __name__ == "__main__":
    raise SystemExit(main())
