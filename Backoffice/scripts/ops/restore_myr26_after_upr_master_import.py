#!/usr/bin/env python3
"""Restore MYR26 (T33 / Jan-Jun 2026) rows overwritten by the 18 Sep 2026 UPR Master import.

The Master Excel run ``upr_excel_import.run_import`` at 2026-09-18 10:36 UTC wrote
stale MYR26 values into live country forms (before the round allowlist existed).
This script reapplies the 17 Sep dump snapshot for overwritten cells and deletes
Master-created empty fills, while leaving real focal saves alone.

Safety:
  * Default is dry-run (no writes).
  * Countries with focal ``data_update`` activity are skipped for value
    restore (and post-import focals are skipped entirely). Direct/indirect
    people-reached splits may still be restored when the total is unchanged;
    funding/support matrices on those AES are left alone.
  * Each row is optimistic-locked against the 18 Sep 23:35 dump. If prod no
    longer matches that expected value, the row is skipped.
  * AES with a focal ``data_update`` *after* the after-dump are skipped live.
  * Only ``value`` / ``numeric_value`` / ``disagg_data`` / ``disagg_type`` /
    ``data_not_available`` / ``not_applicable`` are written. Published /
    prefilled / imputed columns are untouched.

Run on prod via App Service SSH (uploads this file to /tmp; payload is embedded)::

    azure_webapp_tools.bat prod script ops/restore_myr26_after_upr_master_import.py "--dry-run"
    azure_webapp_tools.bat prod script ops/restore_myr26_after_upr_master_import.py "--commit --force"

Or inside the container::

    cd /app && PYTHONPATH=/app/scripts FLASK_CONFIG=production python /tmp/restore_myr26_after_upr_master_import.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("restore_myr26")

# AES with focal data_update after the 17 Sep dump. Never restore *values* here.
# Honduras/Burkina/Kenya may still get disagg-only restores (totals unchanged).
SKIP_VALUE_AES = {1630, 1566, 1585, 1572, 1609, 1686, 1627}
# Focal saved after the Master import — do not delete Master inserts or restore.
POST_IMPORT_FOCAL_AES = {1572, 1609, 1686, 1627}

SNAPSHOT_KEYS = (
    "value",
    "numeric_value",
    "disagg_data",
    "disagg_type",
    "data_not_available",
    "not_applicable",
)


def _ensure_app_importable() -> None:
    """Make ``from app import …`` work from /tmp upload or scripts/ops/."""
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


def _naive_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _json_norm(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _num_eq(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    try:
        return abs(float(left) - float(right)) < 1e-6
    except (TypeError, ValueError):
        return left == right


def snapshot_from_row(row: Any) -> dict[str, Any]:
    return {
        "value": row.value,
        "numeric_value": row.numeric_value,
        "disagg_data": row.disagg_data,
        "disagg_type": row.disagg_type,
        "data_not_available": bool(row.data_not_available),
        "not_applicable": bool(row.not_applicable),
    }


def snapshots_equal(current: dict[str, Any], expected: dict[str, Any]) -> bool:
    if current.get("value") != expected.get("value"):
        return False
    if not _num_eq(current.get("numeric_value"), expected.get("numeric_value")):
        return False
    if _json_norm(current.get("disagg_data")) != _json_norm(expected.get("disagg_data")):
        return False
    if current.get("disagg_type") != expected.get("disagg_type"):
        return False
    if bool(current.get("data_not_available")) != bool(expected.get("data_not_available")):
        return False
    if bool(current.get("not_applicable")) != bool(expected.get("not_applicable")):
        return False
    return True


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds")
    return str(value)


def export_live_snapshot() -> dict[str, Any]:
    """Read-only dump of live MYR26 (T33 / Jan-Jun 2026) form_data + dynamic rows."""
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country
    from app.models.form_items import FormItem
    from app.models.forms import DynamicIndicatorData, FormData
    from app.models.indicator_bank import IndicatorBank

    assigned = AssignedForm.query.filter_by(template_id=33, period_name="Jan-Jun 2026").one()
    aes_rows = AssignmentEntityStatus.query.filter_by(assigned_form_id=assigned.id).all()
    aes_by_id = {int(row.id): row for row in aes_rows}
    country_ids = {int(row.entity_id) for row in aes_rows if row.entity_type == "country"}
    countries = {int(row.id): row for row in Country.query.filter(Country.id.in_(country_ids)).all()}
    aes_ids = list(aes_by_id)

    fd_rows = FormData.query.filter(FormData.assignment_entity_status_id.in_(aes_ids)).all()
    items = {
        int(row.id): row
        for row in FormItem.query.filter(FormItem.id.in_({int(r.form_item_id) for r in fd_rows} or {0})).all()
    }
    form_data = []
    for row in fd_rows:
        aes = aes_by_id[int(row.assignment_entity_status_id)]
        country = countries.get(int(aes.entity_id))
        item = items.get(int(row.form_item_id))
        snap = snapshot_from_row(row)
        form_data.append({
            "aes_id": int(row.assignment_entity_status_id),
            "form_item_id": int(row.form_item_id),
            "country": getattr(country, "name", None),
            "iso3": getattr(country, "iso3", None),
            "item_label": ((item.label if item else "") or "")[:120],
            **snap,
            "created_at": _iso(row.created_at),
            "created_by_user_id": row.created_by_user_id,
        })

    did_rows = DynamicIndicatorData.query.filter(
        DynamicIndicatorData.assignment_entity_status_id.in_(aes_ids)
    ).all()
    banks = {
        int(row.id): row
        for row in IndicatorBank.query.filter(
            IndicatorBank.id.in_({int(r.indicator_bank_id) for r in did_rows} or {0})
        ).all()
    }
    dynamic = []
    for row in did_rows:
        aes = aes_by_id[int(row.assignment_entity_status_id)]
        country = countries.get(int(aes.entity_id))
        bank = banks.get(int(row.indicator_bank_id))
        snap = snapshot_from_row(row)
        label = (row.custom_label or getattr(bank, "name", None) or "")[:120]
        dynamic.append({
            "aes_id": int(row.assignment_entity_status_id),
            "section_id": int(row.section_id),
            "indicator_bank_id": int(row.indicator_bank_id),
            "repeat_instance_number": row.repeat_instance_number,
            "country": getattr(country, "name", None),
            "iso3": getattr(country, "iso3", None),
            "item_label": label,
            **snap,
            "added_at": _iso(row.added_at),
            "added_by_user_id": row.added_by_user_id,
            "created_at": _iso(row.created_at),
            "created_by_user_id": row.created_by_user_id,
        })
    return {
        "assigned_form_id": int(assigned.id),
        "form_data": form_data,
        "dynamic": dynamic,
    }


def load_payload(path: Optional[str] = None) -> dict[str, Any]:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    here = Path(__file__).resolve().parent
    stem = here / "restore_myr26_after_upr_master_import.payload.json"
    candidates.extend([stem, Path(str(stem) + ".gz"), stem.with_suffix(".json.gz")])
    tmp = Path("/tmp/restore_myr26_after_upr_master_import.payload.json")
    candidates.extend([tmp, Path(str(tmp) + ".gz")])

    for candidate in candidates:
        if not candidate.is_file():
            continue
        data = candidate.read_bytes()
        if candidate.name.endswith(".gz"):
            data = gzip.decompress(data)
        payload = json.loads(data.decode("utf-8"))
        logger.info("Loaded payload from %s", candidate)
        return payload

    if not PAYLOAD_GZ_B64.strip():
        raise SystemExit("No restore payload found (embedded blob empty and no sidecar file).")
    payload = json.loads(gzip.decompress(base64.b64decode(PAYLOAD_GZ_B64)))
    logger.info("Loaded embedded payload")
    return payload


def _filter_ops(ops: list[dict[str, Any]], aes_ids: Optional[set[int]], iso3s: Optional[set[str]]) -> list[dict[str, Any]]:
    out = []
    for op in ops:
        if int(op["aes_id"]) in POST_IMPORT_FOCAL_AES:
            continue
        if aes_ids is not None and int(op["aes_id"]) not in aes_ids:
            continue
        if iso3s is not None and (op.get("iso3") or "").upper() not in iso3s:
            continue
        out.append(op)
    return out


def live_skip_aes(aes_ids: set[int], after_dump_at: datetime) -> dict[int, str]:
    """AES with a focal data_update after the after-dump must not be touched."""
    from app.models.system import EntityActivityLog

    if not aes_ids:
        return {}
    rows = (
        EntityActivityLog.query.filter(EntityActivityLog.activity_type == "data_update")
        .filter(EntityActivityLog.assignment_id.in_(aes_ids))
        .filter(EntityActivityLog.timestamp > after_dump_at)
        .all()
    )
    skipped: dict[int, str] = {}
    for row in rows:
        aes_id = int(row.assignment_id)
        skipped[aes_id] = (
            f"live data_update after after-dump "
            f"(user_id={row.user_id} at {row.timestamp})"
        )
    return skipped


def _find_form_data(aes_id: int, form_item_id: int):
    from app.models.forms import FormData

    return FormData.query.filter_by(
        assignment_entity_status_id=aes_id,
        form_item_id=form_item_id,
    ).one_or_none()


def _find_dynamic_rows(aes_id: int, section_id: int, bank_id: int, repeat: Optional[int]):
    from app.models.forms import DynamicIndicatorData

    query = DynamicIndicatorData.query.filter_by(
        assignment_entity_status_id=aes_id,
        section_id=section_id,
        indicator_bank_id=bank_id,
    )
    if repeat is None:
        query = query.filter(DynamicIndicatorData.repeat_instance_number.is_(None))
    else:
        query = query.filter_by(repeat_instance_number=repeat)
    return list(query.all())


def _pick_row(rows, *, expected: dict[str, Any], restore: Optional[dict[str, Any]] = None):
    """Pick a row when Postgres unique indexes treat NULL repeats as distinct."""
    if not rows:
        return None
    expected_hits = [row for row in rows if snapshots_equal(snapshot_from_row(row), expected)]
    if expected_hits:
        return expected_hits[0]
    if restore is not None:
        restored_hits = [row for row in rows if snapshots_equal(snapshot_from_row(row), restore)]
        if restored_hits:
            return restored_hits[0]
    return rows[0]


def _apply_snapshot(model, row_id: int, snap: dict[str, Any]) -> None:
    from sqlalchemy import null as sql_null
    from sqlalchemy import update

    from app.extensions import db

    disagg = snap.get("disagg_data")
    db.session.execute(
        update(model)
        .where(model.id == row_id)
        .values(
            value=snap.get("value"),
            numeric_value=snap.get("numeric_value"),
            disagg_data=sql_null() if disagg is None else disagg,
            disagg_type=snap.get("disagg_type"),
            data_not_available=bool(snap.get("data_not_available")),
            not_applicable=bool(snap.get("not_applicable")),
        )
    )


def _fmt_op(op: dict[str, Any]) -> str:
    label = op.get("item_label") or ""
    kind = op.get("kind") or op.get("op") or ""
    return f"aes={op['aes_id']} {op.get('iso3') or ''} {op.get('country') or ''} {kind} {label[:80]}"


def run_restore(
    payload: dict[str, Any],
    *,
    commit: bool,
    aes_ids: Optional[set[int]],
    iso3s: Optional[set[str]],
    verbose: bool,
) -> dict[str, int]:
    from app.extensions import db
    from app.models.forms import DynamicIndicatorData, FormData

    meta = payload["meta"]
    after_dump_at = _naive_utc(meta["after_dump_at"])
    restore_fd = _filter_ops(payload.get("restore_form_data") or [], aes_ids, iso3s)
    delete_fd = _filter_ops(payload.get("delete_form_data") or [], aes_ids, iso3s)
    restore_did = _filter_ops(payload.get("restore_dynamic") or [], aes_ids, iso3s)
    delete_did = _filter_ops(payload.get("delete_dynamic") or [], aes_ids, iso3s)

    planned_aes = {int(op["aes_id"]) for op in restore_fd + delete_fd + restore_did + delete_did}
    live_skip = live_skip_aes(planned_aes, after_dump_at)

    stats: dict[str, int] = Counter()
    skipped_by_reason: dict[str, int] = Counter()
    by_country: dict[str, Counter] = defaultdict(Counter)

    def skip(reason: str, op: dict[str, Any]) -> None:
        stats["skipped"] += 1
        skipped_by_reason[reason] += 1
        if verbose or skipped_by_reason[reason] <= 8:
            logger.info("SKIP %s | %s", reason, _fmt_op(op))

    def touch(op: dict[str, Any], action: str) -> None:
        stats[action] += 1
        country = op.get("country") or str(op.get("aes_id"))
        by_country[country][action] += 1
        if verbose:
            logger.info("%s %s", action.upper(), _fmt_op(op))

    logger.info(
        "Plan: restore_form_data=%s delete_form_data=%s restore_dynamic=%s delete_dynamic=%s",
        len(restore_fd),
        len(delete_fd),
        len(restore_did),
        len(delete_did),
    )
    if live_skip:
        logger.warning("Live-skip AES (focal save after after-dump): %s", live_skip)

    def process_restore(ops: list[dict[str, Any]], finder, model) -> None:
        for op in ops:
            aes_id = int(op["aes_id"])
            if aes_id in POST_IMPORT_FOCAL_AES:
                skip("post_import_focal", op)
                continue
            if aes_id in SKIP_VALUE_AES and op.get("kind") == "value_changed":
                skip("focal_value_skip", op)
                continue
            if aes_id in SKIP_VALUE_AES and (op.get("restore") or {}).get("disagg_type") == "matrix":
                skip("focal_matrix_skip", op)
                continue
            if aes_id in live_skip:
                skip("live_focal_save", op)
                continue
            row = finder(op)
            if row is None:
                skip("missing_row", op)
                continue
            current = snapshot_from_row(row)
            if snapshots_equal(current, op["restore"]):
                skip("already_restored", op)
                continue
            if not snapshots_equal(current, op["expected"]):
                skip("optimistic_lock", op)
                continue
            if commit:
                _apply_snapshot(model, int(row.id), op["restore"])
            touch(op, "restored")

    def process_delete(ops: list[dict[str, Any]], finder) -> None:
        for op in ops:
            aes_id = int(op["aes_id"])
            if aes_id in POST_IMPORT_FOCAL_AES:
                skip("post_import_focal", op)
                continue
            if aes_id in live_skip:
                skip("live_focal_save", op)
                continue
            row = finder(op)
            if row is None:
                skip("already_gone", op)
                continue
            current = snapshot_from_row(row)
            if not snapshots_equal(current, op["expected"]):
                skip("optimistic_lock", op)
                continue
            if commit:
                db.session.delete(row)
            touch(op, "deleted")

    process_restore(
        restore_fd,
        lambda op: _find_form_data(int(op["aes_id"]), int(op["form_item_id"])),
        FormData,
    )
    process_restore(
        restore_did,
        lambda op: _pick_row(
            _find_dynamic_rows(
                int(op["aes_id"]),
                int(op["section_id"]),
                int(op["indicator_bank_id"]),
                op.get("repeat_instance_number"),
            ),
            expected=op["expected"],
            restore=op.get("restore"),
        ),
        DynamicIndicatorData,
    )
    process_delete(
        delete_fd,
        lambda op: _find_form_data(int(op["aes_id"]), int(op["form_item_id"])),
    )

    for op in delete_did:
        aes_id = int(op["aes_id"])
        if aes_id in POST_IMPORT_FOCAL_AES:
            skip("post_import_focal", op)
            continue
        if aes_id in live_skip:
            skip("live_focal_save", op)
            continue
        rows = _find_dynamic_rows(
            aes_id,
            int(op["section_id"]),
            int(op["indicator_bank_id"]),
            op.get("repeat_instance_number"),
        )
        matching = [row for row in rows if snapshots_equal(snapshot_from_row(row), op["expected"])]
        if not matching:
            skip("already_gone" if not rows else "optimistic_lock", op)
            continue
        for row in matching:
            if commit:
                db.session.delete(row)
            touch(op, "deleted")

    if commit:
        db.session.commit()
        logger.info("COMMITTED")
    else:
        db.session.rollback()
        logger.info("DRY-RUN (rolled back; no writes)")

    logger.info("Totals: %s", dict(stats))
    if skipped_by_reason:
        logger.info("Skipped by reason: %s", dict(skipped_by_reason))
    logger.info("By country (non-zero actions):")
    for country, counts in sorted(by_country.items()):
        logger.info("  %s: %s", country, dict(counts))
    return dict(stats)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing (default).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply restores/deletes. Requires --force on this SSH script.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required together with --commit (no interactive prompt on SSH).",
    )
    parser.add_argument("--payload", help="Optional path to payload JSON / JSON.gz (else embedded).")
    parser.add_argument(
        "--aes-id",
        type=int,
        action="append",
        dest="aes_ids",
        help="Limit to this assignment_entity_status id (repeatable).",
    )
    parser.add_argument(
        "--iso3",
        action="append",
        dest="iso3s",
        help="Limit to this country ISO3 (repeatable, e.g. RUS).",
    )
    parser.add_argument("--verbose", action="store_true", help="Log every applied row.")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print payload counts and exit (no database).",
    )
    parser.add_argument(
        "--export-live",
        action="store_true",
        help="Print current T33 Jan-Jun 2026 snapshots as JSON between sentinels (read-only).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    if args.export_live:
        from app import create_app

        app = create_app()
        with app.app_context():
            snapshot = export_live_snapshot()
        packed = gzip.compress(
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"),
            compresslevel=9,
        )
        sys.stdout.write("\n__MYR26_LIVE_GZ_BEGIN__\n")
        sys.stdout.write(base64.b64encode(packed).decode("ascii"))
        sys.stdout.write("\n__MYR26_LIVE_GZ_END__\n")
        logger.info(
            "Exported live MYR26 snapshot: form_data=%s dynamic=%s",
            len(snapshot.get("form_data") or []),
            len(snapshot.get("dynamic") or []),
        )
        return 0

    payload = load_payload(args.payload)
    meta = payload["meta"]
    logger.info(
        "Payload %s  template=%s period=%s import_at=%s after_dump_at=%s",
        meta.get("kind"),
        meta.get("template_id"),
        meta.get("period_name"),
        meta.get("import_at"),
        meta.get("after_dump_at"),
    )
    logger.info(
        "Counts: restore_fd=%s delete_fd=%s restore_did=%s delete_did=%s",
        len(payload.get("restore_form_data") or []),
        len(payload.get("delete_form_data") or []),
        len(payload.get("restore_dynamic") or []),
        len(payload.get("delete_dynamic") or []),
    )
    logger.info("Skip-value AES (focal): %s %s", meta.get("skip_value_aes"), meta.get("skip_value_countries"))
    logger.info("Skip-delete AES (post-import focal): %s", meta.get("skip_delete_aes"))
    if args.summary_only:
        return 0

    commit = bool(args.commit)
    if commit and not args.force:
        logger.error("--commit requires --force (this script has no TTY confirm on App Service SSH)")
        return 2

    aes_ids = set(args.aes_ids) if args.aes_ids else None
    iso3s = {s.upper() for s in args.iso3s} if args.iso3s else None

    from app import create_app

    app = create_app()
    with app.app_context():
        run_restore(
            payload,
            commit=commit,
            aes_ids=aes_ids,
            iso3s=iso3s,
            verbose=args.verbose,
        )
    return 0


# gzip+base64 of restore_myr26_after_upr_master_import.payload.json
PAYLOAD_GZ_B64 = """
H4sIABbDrWoC/+y933LbOLb/+yqq3MxMHSdD8D/7Lt35O52ks+10T83smkrREi1zRxa9Sclp966p
Oq9x3uNc/u72m5wnOQAp2aK5ZJMgAQKLmItMBxFJ8LNA/PmuhYX/eXaVbOJnP/zPs2/pevHsh2dX
t7ntf40vNkn+dXudf72KC/af6dV1lm+enTyr/uNrvKG/tS3bf25Fz0n4hVg/OP4Plvt/WdYPlkV/
V91hsb26pj+8zrNF+d/Pr7Nis8yT4jm71opIaDuO96L47xW95Dy5yPLk6WsCYpFgd811kqf0d+v4
KqHX/C1eP//bdj1jP6T/uEmurlfxJvma0jdznMNKNV7Adn5wPFr1uxcovqXXX2/i1Tb5GifFsx/+
k/iOdUI836d/hB79I7BPCK0P/SOkZb4d/Gt31SJZJZu7y8DfxUWRLtfJ4it95auyfm7tkfNsu97k
aXmHZ++y9WKbxwWt1Y/bnBoqnr2Ji4z+9edkfRvT//8pu8ryjP3gn/HVecqKPlEzXc4+xvNkka3L
krdbyuIqXsXP/vXvk2e7Si5uKbt0Th/zP8/SInMolY+vXjIDJkVZL1prWrWqPrfsX7PVIruJT2an
yfX2fJXOZ9kF/Xny+3Uy3yQL1pTKV6A/jRjHRVrEy+XXRcya2Xq7Wt0VbW6v2a8K2qRWCf3lentF
rTn/urs8smhRRpva9TV9SnxOf/PDRbwqEnoDerOv5b/dxOnq4J/oe6X0Hb/SsmRF7/3yitV7lq5n
P717Qys6i2+SPF4ms00er4uLJJ+VD3vB7E2rn2bryhYkojdaL+hjN1n+9TxefyvLfT88eZYn10m8
+Zqui028nidfabXPk7x6t3+fDE/Rc4M+GOnl/Tl+Kt+RAbxOMvqYGf06b9JFsph9T2kr267ntImm
jF+8ms3j4nLGGngFqC1cQj9r+XT9sA9c1h4GZ5sn8fySoj2/ZZg3FbqT2TJZL+jv4vWCtuf5alvQ
UvaDZR5fXaXrZetG7HgjNGLP6dWIPUcg6M1lnm2Xl7PL7VW8TjdxnsbrWZHkN+mctvQsXW+K2Z+v
Ugqa/tcJpU9HEdrQV7czWns6wtAult4yL7J1UZrnkg5Ys3l2dbWld6N9+F+qr6R2+/vvg13y1yyf
Xbe0n0OHIen2cwO3j/3o5QLtV9KlPdAm+X2zLe1CH5Nn1xT0JpldJvGK/vvOnkXrz8R2RsBsR70w
25FozFfJekP7+B1U1tqvi9s5bfHZPKXle8qzP3989/ns7C+zizy7oh9YMvsU74aHM/rLZHP74kXr
9h6YQbdpiDxZpcnFYT9Cp5Kz87igr7VOkkXReti1RxgPwn7jQSh0PCj5FpfJivbzs2J7zVY87bsN
e4TW6vfqnenlAmjSKXZKVzhs8v2x6jTe3Xcanw87jbMKcfsG67ZGfPrrWR1xdIj4dEu/HjoYv0no
zKrsn44Adogbem6v5czuFlqvaQai6fq9Bjm/P8OPu8nc/uvef/RMMMhu2Rg3iym6m3L61noBY4We
bJS3SdGHZfXb3p/+g6F9dhnTifDsp90M+Hb2er2kDbTCSj/+l/PyTePzdMX+9TqjT749mRW0AW+S
5e2MTYZX8br9giY02O+xv6JVYJrd7GO83lP/XCIu4Z/tKLel6/rE0L2ju676hYQuN7J8ka7LH9FJ
8fySLu2Kq3IOll3vXq91z+F2WNKhZlw+jbXYYq9sFLNNtu+lZ/s1+H7J3Fh+twXu2dIbtRNYYa9Z
WnmDIedp88t0tciT9ew6zjfpPL2m1V8v2cSi/JfnF3marBd0NU2X1sV2tanaNLMHnRpfzxYJk7BP
7m12UvYvVxnt8jOmU93eqVPJ3oLs/vvHth5W5Xfvge/1sRS9fEg7HbZ6QHGqr1r262/WEdU1pgMx
sf1iJpI+N/RCQnpND9kNcKuywy1qei5oxGKGVKM/FbNksZ3vS+86mPaynuPI5kxcz+pFuryBBP37
Ok+v4vx2L+7N4zyZ/XWWbTflD+/7lr/STp7O3ZMZm92zv85X6TqdF7uZz3HrtV9JWdInRLZPol4d
T3mD0VTu7/SPnK6hSg9DOSktPRG3SzqGJxzit3SJJQoCp5f4Xd5g2vL3QKbwI8/qpXWVN0ApgA/V
2Tj9uhqHIJC/h2Jp9XIl0MuN+P0EYKtfd1DeQADkm2xFXyahj2o/zw6e5Pcv9u/FpgxFawZHvXzz
lj5pFyy3e/1svbqtgXbJIeiXF8tSHaLPenZ379oE0X5I93+eXWUL9k+bjLYd+q/lTwv2D1XJD8T+
978b/OkTFnG++FoVAxNJm8sK4KTW7jWjtfs3h1fpDV0BMwGZtoiHw+v/93//P8WM8rigA8SGDsvr
lI4Nq+QmWTUbigNLRJZ/vKGQg6/s9U+/3reIXfQetfeS8jpsE3bNufd6vo0XWQ63B9d60et74/Qy
gcvxMSpSM/PnJJ+zHnSZlL6u+9F+Qcd/2gJoJ0sX3UxXKsPOaPd6k23pOJYXbS3t29ZYlo7CfpaO
wsEsHYUjVOQRS+/6+GKb3yS3bFZymdEZSikD58k8SW+YzbdFcrFdlVaPS0Oz29NBl0XVxrDSdaQN
OFG7NvDp7csn+38v8g9bwKd0SVHFcAtwQtu2unf/5WUcI0B53WBtBqx8Jw2JuzpPadrbUpbzZrdJ
nBdl47mMb5LZeUL/LVnn2WpVzc7Y/LaSr5nycUHXDaxd3fctR5QMutZYrbLv7Le0S0qKgt2hbWMj
1mOxZUdb29Eep0t7c6OeY0s03NgSjVCRR3ocOoDQlTsbZObbTTK7ilfr7SYvo5pn6YL+Lr1ID9Sy
u9nnrJjntFnRtsDE+IskZ+2GrUWZbrbp2DBaTjq+/Hr69DQ0cg6bxZf//T/5t/Q2OTIHJR7HJJR4
PLNQ4g03DSW9PDW8VWkZHJ/lDwNMLrbr+a4nWdGb5PG8DHcoq8X+e74qu5PZzoGW0b4nZ23pit1+
7wbdZLOLeM6CJ5jydx+z8tciWV08v//7CW2jtIW1XBnZUfuV5eDNz2tqf083P3oRR/PznOG6MK+f
ZOkJFSzp0JWsb9I8W+9Uy/h7TIdGOliVE6Y7P8pBqFM5Is4vs2zVPuqJEGu8duOEHmlu4Wgzf2LX
cU2g2IUDzqCg+nebQnFXqHUzAlfX87vwrp0aTru9q6yLe5kOd8F4TccmrsfRcsrLOBpOed1g7Qas
fCdNjrs6rVvNTuCcZ5dJ8aCboSMYrRcdJtkFq11gyXmy+c6m53fxDke32pRPgnbatHaqPDbPEt3w
AhJ6HEu+8jKOhldeN1jDAyvfKTiGuzpT38w1/OBJXJ5Zf3kZz9DJrhtu5IQq3zF+RcjsX4xXQuRA
6ARREDocQ2F1Ic9gWF053HAIv0I3nyp/lR5vEJVyySTLUhfIFjP2++Kup2poS9RG17T7ab2FIyIj
th7XCTj6EHYVR7thlw2nPwE176RA8VbmyeZS0HFkPmcLNTpRul+npcXBun9xtP38qeALQGzhGN0l
jSiTVlTA7j2jr/5Z381WFyVfrvaiJGSKdYZ6F0uV5IM9rETjWtbBF4mU2yK7op1FOp/FC6ZCzW/v
ySyYHza7pk04XqVLJpyeMC/tKomLcl8bi0c/qaZZy1V2Tm/9/s3pT40b7eb7D+ESBz/cvYxY+j3v
GijzXpzH828H+1EYTTanreLBV6sZC9j8nuXfIHK2NS1y7F6zq/tdUsVtQe9A+9V4s/MhFrStztNy
9XoVfyu9PfTL3+mwxX6vw768ck+yv9HfM68RfUG66K3UNqYIswUC7eiZDWKo5Ub4+X++i52vYiPP
kt+39Eevf79eZYeRqy/Pt3QU/PPns9cv/0K72rL8M+1OyxGR2Yat5nLakazvLtnL48xlnN5kOdw7
+IYxyLgav3rj9fDjLeKLZBdywOZoKQs5uO9x/1xs5yz9UdkBlOPWe7oaXOasg/6QrpO/3PfJm7uI
hvTuJ/OMdhL5ujiZXaUFy6q03XUg55XAUToo8+0qgbsQG/3gt2NCJw+liHPXPPfqTdmTl/G/B575
JiknQt9S58z9zCZZbG/SfpMe/ftttmVb3e9ns0/Mp9DPCg7mo5V6d0grvp+3sjkU/QslR7/tcgZB
/z+l86rt73QNwOJH8myVgBP+EDvDu05xtwuuVPZZLATbpRVvLr/Ht7WtvHejCOvPblLKbV31iLuF
734nBfTlop8mlcFLm/hbsi6jAPYLnxPaycWrbLlN6PBwuA2OtsvdKmCvFDCtOmYb1UvoVcxQOSKt
kmW8OrlbrR5uV6c3OvAXs+vOE7DndDHzP9iCXveeM8ir9IqFXMxjOrGnK1e2zXZO51ALNuE/Ty5j
2pC3+Q73CRvlyxVwzmxVbRed00Xu+vn2uozwKMtZN/L23dtZQsf7Yp804CHycCrI1/FmmyfPz2MG
tchW28o1+OeyV1lUXS6Tx0pxIN7tXN+u4ryyxH7hxYSXaiF2waKwksqVQ5d6S+ZzLP4CMkY9dUqL
e8zlepX2JcuUtesqbdA+YJYOYfHiKr5ms9QVna5WpO/mssVB9pDGRAH1IHefJKEKk2E4nrMg0rvO
AGRiI2LyBQqE3aVFyS4u0tLdf06bE10A7eZU5UhykcdXCROd6KImWyRlV7rcpovSYVqqLYvkgra1
as20f/tyMlWtPHdugXKuUN0fmhi4NsEFO0/YZxs3mb86gMu6urslJTj3PJwuvXz7Sy1y2K95el6u
l9nKaPRNjR4nNgkqMkZwYy11Xn55W+vRSH2XIR3Xl9u4rNiPcX6+XZgPGfiQ8TNUw/E2AdAyus9p
UVTaITcBWyjlnDO8pTnqJoBaG6cdelsIceDhpybAmYcemmTHHnqeZuVrHH6obaG+828q+FVxBOLm
LdkpiBrmAA5CTHy0chYiAy/CcXj6gJBdI5Qvyy7EuBwAlwNWcoo4GrDileFemAI7tZ0KWC2glivB
UBbsQMAKWB+3AU4LiHEWIGUlwkWAE5VsxwBOiqO5A3Di1MkJgM8CGkj/qKErI/gjpCxb5seHcAhx
X3sqekn6GHALEfI/1rgED7jQW5o0XaCMj5KbKiI+SrhSJHz05BQX8FHyV0y+N4yFivco8Wok3SPk
L0i4x0hKiGyPEJR00R4hw/Eke4QwtRLskfHXQa7Hi1wdsR4bY+lSPTKAgwj1ejPRTKbXHrYIkf6f
r+tU6mmT/kjy8zj9r3ht9GZOvRktX32EU7QmUEs7NZhFy6doCeujoCI1gRBpECkr2eogQozSF58I
GQ6x/tQfi15LUBS8BaxCf3x3Vg+hq4H5Mb6Mr+LChIo1QsWQclNj6Y4UroRQsQmQU1rxQMpfKbnD
MBaqdSDFq43QgZK/kFAxnKQE6EEoQUkWg1AyHCtUDCVMjULF0PFXP1QMM3JVQsXwMZas1qMDOIBU
rzsTrXR6BLBFiPSnP9apuHUq+Xm8yIxKD6j0SMEpItMjpStDp58AOrWFeqQGUEupN5DFSvVI+eqj
1aM0gBixHicqEWo9SlKy5XqUEEfT61HS1EmwR2cADRR7zMyVkezxQZat2aMjOIRorzsUvVR7BLRF
yPYf/lnH4tWwJKv0j8SI9k3RHiU2RSR7lGxlCPbowakt16PEr5ZYbxCLlOpR0tVHqEeIX4xMjxGU
CJEeISfZEj1ChKMJ9AhZ6iTPI8OvgTiPl7gy0jw2xLKFeWT8hpDl9UailyivPWsRkvzrT4dQPL/u
qWCzWaPINxV5jNQUEeQxopWhx2PnprYcj5G+Wmq8ISxQjMcIVx8tHh99MVI8Qk4ilHh8mGQL8fgI
jqbD40OpkwyPi74GKjxa4MqI8MgIy9bgceEbQoLXmoheCrzuqEUI8F8OmbjEqSf4udxuYqPAAwo8
SmyKSPAo2crQ4NGDU1uER4lfLRXeIBYpw6Okq48OjxC/GCEeIygRSjxCTrKleIQIR9PiEbLUSYxH
hl8DNR4vcWXkeGyIZevxyPgNIcjrjUQvRV571iIk+V8+1DcK+DUodD5wk8Yns8+rbZ6u7x67YeNd
dmG0+qZWPy2eioj404IuQ92fLlG1Zf9p2UUtf4BhP4qjYFrY9fEgTMkuYlwLkyIowucwJYCynRFT
Yjual2JKkHVyX0zFLhr4NSZoCmUcHpNhL9sTMhWwQ7hIkLLSy3eC1wginCrv39VoBfW9H1mxTuPS
Fu+S/I9kmd1QZsaX0vSlTAKjIi6USbCW4TmZHEi1HSaTMIdafhKDXKZ7ZBK09fGKTMAcYpwhUwAn
wgcyAW6jyfMTYKuTKo/cHBqI8dOxgDIaPHbksqV3XDz1UpHRsRchHv/9ZT1xUD11f7YpvsdGLobk
YqTgFBGIkdKVIQlPAJ3aIjBSA6gl+xrIYoVepHz1kXZRGkCMmIsTlQj5FiUp2bHqKCGOpnqjpKmT
zo3OABoo25iZK6Nl44MsW71GR3CICHHdoegl4iOgLUK2P31Zj5APaljy+I90ZUT7pmiPEpsikj1K
tjIEe/Tg1JbrUeJXS6w3iEVK9Sjp6iPUI8QvRqbHCEqESI+Qk2yJHiHC0QR6hCx1kueR4ddAnMdL
XBlpHhti2cI8Mn5DyPJ6I9FLlNeetQhJ/u1pfbtB3VOxXS3jPDWR9IAojxScIrI8UroyhPkJoFNb
mkdqALXEeQNZrDyPlK8+Aj1KA4iR6HGiEiHSoyQlW6ZHCXE0oR4lTZ2kenQG0ECsx8xcGbkeH2TZ
gj06gkNI9rpD0Uu0R0BbhGz/5sEGg3qu+W3+LV3HszdxkRnpvindI4YnQ2BGi0+MOoEWl+x1N1qQ
o6290RLVaf2N0ggarMGxc1dmHY4BtF6LJiTEBSycfvp4WkcTHqL5iRorz7K18WsK82v+9Pm3ugGi
ugGuk9lvSb5IzLq1sW7Fi06NoDO8fCWoAtOAp3TgGV4TKBV6ZjCLDj7DS9hM0zBKvGhhCQhBw8pK
shiOFeNYUjhWnhoJ4RhNoL4Mjpy6KiI4SsySw9EwMhwgIA0BFq28Kzh4i/CtvHxTAxNYNTD0hmwW
9/KCvg697WlyvT2nb2CE/qbQPxGQisj+E6EtwwkwQZRquwQmYhC1HAQGulx3wUR46+M8mIRBxLgS
poFOhGNhEuRkuxkmAXU0p8Mk6OrkgkBvEA0cElOygTLuCfzQZTsr0BMdwnWBDZJejgyE9AW4Nb78
9KqOidQwXcYL48JouDAwQlPDXYGRrATXBHZsSrshMMJXyuVgAItzL2Bkq40rAR98IW4DhJgEuAjw
UZLsDsAHcCzpHx9JjWR+XPDVl/TR8lZFvkcGWLJUj4veALK81kC0kuB1Jy1iF8G7D/Vj+uoZmi7T
lckNBGwZwEhNkf0BGNHK2AyAnZvakf8Y6asV5m8IC4zpxwhXnwB+fPTFROsj5CQiNB8fJtlx+PgI
jhZ0jw+lThH2uOhrEE6PFrgysfPICMsOlMeFb4ioeK2J6BUCrztqEQL8Lw+Y1PMbZavs6lzHo9/F
a/BIwSkiwyOlK0OJnwA6tcV4pAZQS483kMVK8kj56qPKozSAGGEeJyoR2jxKUrLleZQQR1PoUdLU
SaRHZwANdHrMzJWR6vFBlq3WoyM4hGCvOxS9NHsEtIXI9m/rWwmcOpb1MjOaPaDZI6SmimCPEK0U
tR45N8WleoT0FdPpDWGBIj1CuBop9OjoC5Ln8XESos2jwyRdmEdHcDxVHh1KrSR5VPR10OOxAldH
jMdFWLoSjwrfIDK8zkQ00+A1Ry1EgH+Qy8dtMDkpbfAqucrmbC4wv0uqX3ailyaxDSTQT5CqKgL+
BNFLEfgnzlVxB8AEraOYg8BYYEQHwgTha+RgmJx1BDkgpsdRiINichilOzAmR3g8B8fkUGvlAJmU
dXRwkEzVIOo4UKZlAekOlknhHcQBg5mYZg4a5KYQ4sD5ubaxxPXqzLJvs/cFveOiMH4awE+DF54q
7hi8hKV4XaaBT3HnCl4jKOZDMaDFu0rwMtbII4LVCIIcH2hxCfFvYKUl3Y2BFeR43gqsRLVySmA0
gg6+B+Tc1XExoAQt3ZOAkeIgDgMEYDTzC+AgLkL+P31fQ2NbdTSU9+yUVtmI/03xHy06RaR/tHxl
CP+TgKe27I/WBGqJ/gazaMkfLWF9BH+kJhAj92OFJULsR8pKttSPFONoQj9SnjrJ/AhNoIHIj5u6
MhI/RsyyBX6EDIeQ9/XHope4j4K3CGn//W/13RB1r8f//r90sFv86f1NluYmBxMg76PGp4jEj5qx
DJl/MgDVlvpRm0Etud+gliH5o6asj+yP2AxipH/MwETI/4h5yXYBIEY5mhsAMVOdXAFIzaCBOwA/
eWVcAlhRy3YLIOU4hGsABxq93ANomAtwEbw7rcHxA78Gh/YIm9SE/jd9A0i5qeEUQApXgjdgAuSU
dgMg5a+U/m8YCxX+keLVRvFHyV+I1I+TlACNHyUoyeI+SoZjqfooYWok56Pjr76Ojxm5KgI+PsaS
lXt0AAeQ7HVnopVWjwC2iDj+X3+sb3AgNSrbc6PQA9H7CKEpErOPkKyMSH3k2NSOz0cIX62ofANY
XCw+Qrb6ROCjgy8m7h4fJhHR9ugoyY6xRwdwtMh6dCR1iqdHBV+DKHqsvJWJnccFWHbEPCp6Q8TJ
6wxEr+h4zUkLkNtffXxZR2IfInmVXaVrkw8fktyxglNDdsdKV4L0PgV0SsvvWA2glARvIIuV4bHy
1UaKx2kAIXI8UlQCJHmcpCTL8jghjiXN46SpkTyPzwDqS/Somasi0yOELFmqx0dwALleeyhaSfYY
aIuQ7X/5WMfiQFjWs9PkentO624E/KaAjx6hIlI+es4yRP1JQVRb3kdvCrWEfoNbluSPnrQ+4j9y
U4hxA2CHJsIhgJyZbNcAcpyjOQmQc9XJXYDYFBo4DqZBXxkXAmbcsp0JiFkO4VbAg0cvBwMq7gJc
Da/f/qMGKAoOAb1e3l5vjHeh4V1ASU0NhwJKtBJ8COi5Ke02QElfKU+BISzQOYASrjb+AIT0hbgA
MHISoPojxCRZ6EdIcCxtHyFKjeR8ZPTVV/DxAldFtMdGWLJOjwzfANK83kS0UuO1Ry1AgD/7UD8n
wK6d6fuaPiJe3cSLLDcyfEOGR8xODTEeMWAJkvxE6CktzCO2gVLyvOEsXKRHjFgbqR6tDYQI9nhp
CZDt0cKSLN6j5TiWhI8WqEZCPkobqC/nY8euiqiPk7NkaR8lxAEEfgxctJL5kQAXIPa//fQfh2S8
oO4A+e9tzHQw+qi3W2oUk5i/KfmjJ6iG8I8eswT5f1IMlXYCoLeEUq4AQ1uSQwA9aG3cAsgtIcQ5
gJ2ZABcBcmSSHQXIaY7lLkCOVSOnAWJLqO86mAZ8VRwImGlLdiMgRjmAMwEPHa1cCqiwi9hF8Pd/
1vmENT7Fd/qodXpSmuRn2osssiuK3/gXmlsKJgJSkf0FE6EtY7PBBFGqvfNgIgZRaxuCgS53T8JE
eOuzQWESBhGzW2Ea6ERsXZgEOdn7GCYBdbRNDZOgq9MOB/QG0WC7w5RsoMzeB/zQZW+EQE90iF0R
2CDptUUCIX0RpxN8eVfHFNUwbS7T7Do12ySAAwqQglPkjAKkdGUcUzABdGqfVIDUAGodVmAgiz2v
AClffY4sQGkAMacW4EQl4uAClKRkn12AEuJoxxegpKnTCQboDKDBIQaYmStzjgE+yLKPMkBHcIjT
DHSHoteBBghoC5Dt3/ztfS0BlOsfYnmT/ldqJPuGZI8RmhpyPUayEqR67NiUlukxwldKojeAxcnz
GNlqI83jgy9ElkeISYAkj4+SZDkeH8CxpHh8JDWS4XHBV1+CR8tbFfkdGWDJ0jsuegPI7loD0Upy
1520iFMFXv5Y80KE1iGSt/F5tjZ6e/MkAYzUFDk9ACNaGScGYOem9ikBGOmrdTKAISzwNACMcPU5
AQAffTFZ/xFyEpHpHx8m2dn98REcLaM/PpQ6ZfHHRV+DzP1ogSuTrR8ZYdkZ+rXGp1feed1Ri5Cb
X/9SU+DruWveJlm+NDlZIMEZJzdFJGeccGWIzvjJqS074+SvlvBsGAuVnnHi1Ud8xshfjPyMkpQI
ARojKNkSNEaGo4nQGGHqJENj46+BEI0YuTJSNDrGssVobACHOCRWcyZ6SfT6wxYh0p++qlGxa2Hy
b+ncNl4YkR4Q6XFyU0SkxwlXhkiPn5zaIj1O/mqJ9IaxUJEeJ159RHqM/MWI9ChJiRDpMYKSLdJj
ZDiaSI8Rpk4iPTb+Goj0iJErI9KjYyxbpMcGcAiRXnMmeon0+sMWIdK//1TfXeDUqGypFYxGD2j0
KLEpItGjZCtDoUcPTm2BHiV+tfR5g1ikPI+Srj7qPEL8YsR5jKBEaPMIOcmW5hEiHE2ZR8hSJ2Ee
GX4NdHm8xJWR5bEhlq3KI+M3hCivNxK9NHntWYuQ5H/9R91RUd9NsL2N10aSByR5lNgUkeRRspUh
yaMHp7YkjxK/WpK8QSxSkkdJVx9JHiF+MZI8RlAiJHmEnGRL8ggRjibJI2SpkySPDL8Gkjxe4spI
8tgQy5bkkfEbQpLXG4lekrz2rAVI8u++1E98taNDKO9iOmEwinxDkUdJTQ1BHiVaCXo8em5Ky/Eo
6SulxhvCAsV4lHC10eIR0hcixWPkJECJR4hJshCPkOBYOjxClBrJ8Mjoq6/C4wWuigiPjbBkDR4Z
vgEkeL2JaKXAa49ahAD/66d6hv06ky1dAtD/MhJ8Q4LHyU0RER4nXBkyPH5yagvxOPmrJcUbxkLF
eJx49ZHjMfIXI8ijJCVCkscISrYoj5HhaLI8Rpg6CfPY+GsgzSNGrow4j46xbHkeG8AhBHrNmegl
0esPW4BI//5TPcO+GxxSeb9epCZvTVOiR0lNDYEeJVoJ8jx6bkqL8yjpKyXNG8IChXmUcLWR5RHS
FyLKY+QkQJJHiEmyII+Q4FhyPEKUGonxyOirL8XjBa6KEI+NsGQZHhm+AUR4vYloJcFrj1qEAH9a
d0tEtdw97ynZk9n7YhVf0cHqNLnentP6U+ZGlG+K8lMhqYhQPxXcMsT7KbJUW9CfikXUEvkNdcnC
/1SA6+MMmIZFxDgIJsJOhNNgGuhkOxKmQXU058I08OrkcMBvEQ2cEJMygjKOiQlQl+2swI90CAcG
Okp6OTUw4hfi6PiPOqfoAaf/NgNQrwHoby8/1gA75BDw3+KrmL698Rs1/EZIuanhJUIKV4JPaALk
lPYAIeWvlL/HMBbq3UGKVxtfDkr+Qjw3OEkJ8NOgBCXZK4OS4Vg+GJQwNfK4oOOvvn8FM3IjZiHx
naADOICnRHcmWvlFEMAW4AX52y+nh1QCy6pRyXJqFKPRNzV6lNgUkehRspWh0KMHp7ZAjxK/Wvq8
QSxSnkdJVx91HiF+MeI8RlAitHmEnGRL8wgRjqbMI2SpkzCPDL8Gujxe4srI8tgQy1blkfEbQpTX
G4lemrz2rAVI8j+//GfNURHWoPwc/xF/u2S0jSzfkOXxolNDmsfLV4I8Pw14Skv0eE2glExvMIuW
6vES1kaux2oCIZI9WlgCZHusrCRL91gxjiXfY+WpkYSP0QTqy/jIqasi5aPELFnOx8hwAEkfARat
ZH0cvEVI++9P6wdO1HIO/Zzm6Tl9mBH2m8I+UnCKyPpI6coQ9SeATm1JH6kB1BL0DWSxcj5SvvqI
+SgNIEbKx4lKhJCPkpRsGR8lxNFEfJQ0dZLw0RlAAwEfM3Nl5Ht8kGWL9+gIDiHd6w5FL+EeAW0B
sv3n059rWLy6PyOja4cTevurbM5mBvPZ5ySj7/inwhyQ/KioP02sakj+02QvwSFgwCrtLpimeZRy
JhgTjOlqmCZ9bRwRUzSPEDfFJEEKcGJMkaNkF8cUEY/lAJkia43cI1Mzj/rOkwlbRBXXyuRMINnx
MjW+A7hlkCPTymmD3xYidmK8fbBFpXYaxM+3+fL2D5NkCd6LgRadIrsx0PKVsR9jEvDU3pGB1gRq
7ckwmEXvykBLWJ99GUhNIGZnBlZYIvZmIGUle3cGUoyj7c9AylOnHRoITaDBHg3c1JXZpYERs+x9
GggZDrFTQ38seu3VQMFbgLT/4cdP9UMlamA+JOfxOjO6flPXR8pNDVEfKVwJiv4EyCkt5yPlr5SW
bxgLFfKR4tVGxUfJX4iEj5OUAP0eJSjJ4j1KhmMp9yhhaiTbo+OvvmaPGbkqgj0+xpLVenQAB5Dq
dWeilU6PALYIkf7sl0MqXujXqRQZ7V+NSN8U6XFyU0SkxwlXhkiPn5zaIj1O/mqJ9IaxUJEeJ159
RHqM/MWI9ChJiRDpMYKSLdJjZDiaSI8Rpk4iPTb+Goj0iJErI9KjYyxbpMcGcAiRXnMmeon0+sMW
Ekl/WqcS1Kik5/RFYiPSA5H0KLmpEkmPEq6USHr05BSPpEfJX7FIesNYaCQ9SrwaRdIj5C8okh4j
KSGR9AhBSY+kR8hwvEh6hDC1iqRHxl+HSHq8yNWJpMfGWHokPTKAg0TS681Es0h67WELEen/Ud9f
YD+gcmskekiiR0hNFYEeIVop8jxyboqL8wjpKybNG8IChXmEcDWS5dHRFyTK4+MkRJJHh0m6II+O
4HhyPDqUWonxqOjrIMVjBa6OEI+LsHQZHhW+QUR4nYloJsFrjlqAAP/x1W8HTFziuIdMPsarBZsn
GA2+ocFjBaeGDI+VrgQlfgrolBbjsRpAKT3eQBYryWPlq40qj9MAQoR5pKgEaPM4SUmW53FCHEuh
x0lTI5EenwHU1+lRM1dFqkcIWbJaj4/gAIK99lC00uwx0BYh2394X9tNEFkPsKRGsm9K9uigiVlO
o8M02toGHUmd1jXvPtSOGPecOvy8uGR+lfcF7ToWxsMJdJfIASri6UROWYbHc0II1fZ8IjeEWh5Q
A1uOJxQ5Z308oqgNIWYphxuZCA8pamKyPaWoYY6mKqCmahQG40Ft40GdAntlPKl4Ycv2qKIlOYRn
FQscvTysiKiL8LSefqn7cEgdz5auc+lS2aQpAxwIaNEp4jpAy1eG02AS8NR2F6A1gVqOAoNZtIsA
LWF9nANITSDGLYAVlgiHAFJWsl0BSDGO5gRAylMn+R+hCTQQ/nFTV0byx4hZttiPkOEQMr/+WPQS
+FHwFiHt/3pWB2M3waRbszUAUPaxklNE2MeKV4auPwV2asv6WC2glqpvKAsW9bEC1kfTx2kBMZI+
UlYiFH2cqGQL+jgpjqbn48Spk5yPzwIaqPmooSsj5iOkLFvLx4dwCClfeyp6KfkYcAsQ8t+cfaxv
YagniUvndORLijQ+mb1JFmyOQC1xtinbfXZh5P2GvD8xnmqI/hODLsEVMGGiSjsIJmYXpdwGhv0o
zoSJYdfGxTApuwhxPEyLoAB3xKQASnZSTIrtWK6LSUHWyKExGbuo7+aYoilUcX5Mh71kl8hkwA7g
KMHKSiv3CWIjiNgd8eltnZZXo5Wtl3SiYtIeAZsjkIJTZG8EUroytkZMAJ3aOyOQGkCtjREGsth9
EUj56rMtAqUBxOyKwIlKxKYIlKRk74lACXG0LREoaeq0IwKdATTYEIGZuTL7IfBBlr0dAh3BIXZD
6A5Fr80QCGiLkO1/+Wd9j0j9OIfsj/jqPP3vbWKE+6ZwjxadItI9Wr4yxPtJwFNbvkdrArUEfINZ
tISPlrA+Ij5SE4iR8bHCEiHkI2UlW8pHinE0MR8pT53kfIQm0EDQx01dGUkfI2bZoj5ChkPI+vpj
0UvYR8FbhLT/8bTu8fBrYG7j9VWcG12/qevj5KaIqI8TrgxFHz85teV8nPzV0vINY6FCPk68+qj4
GPmLkfBRkhKh32MEJVu8x8hwNOUeI0ydZHts/DXQ7BEjV0awR8dYtlqPDeAQUr3mTPTS6fWHLUCk
//TyY917UUsy9Cm+Ss9N1hxApEfKTQ2RHilcCSL9BMgpLdIj5a+USG8YCxXpkeLVRqRHyV+ISI+T
lACRHiUoySI9SoZjifQoYWok0qPjr75Ijxm5KiI9PsaSRXp0AAcQ6XVnopVIjwC2AJH+84e/110X
0SGVz/Eq3hqJviHRo6SmhkCPEq0EeR49N6XFeZT0lZLmDWGBwjxKuNrI8gjpCxHlMXISIMkjxCRZ
kEdIcCw5HiFKjcR4ZPTVl+LxAldFiMdGWLIMjwzfACK83kS0kuC1Ry1CgH+QvN+36kyut/RxyffZ
2y21hgmXB7R45AAVkeWRU5ah0E8IodpiPXJDqKXbI4etj8qM2hBiBGfcyERoz6iJyZahUcMcTZFG
TVUncRqtITTQqfGyly2ooiU5hLaKBY5eMisi6iIU19N/1PA4Th1PHi+38a1RWptKK1JwiiisSOnK
UFYngE5tRRWpAdRSUg1ksUHQSPnqo1CjNIAYZRonKhGKNEpSspVolBBHU6BR0tRJeUZnAA0UZ8zM
lQmOxgdZtpyPjuAQMr7uUPSS7xHQFiHb//KhhiUMalgyerOFEe2boj1KbIpI9ijZyhDs0YNTW65H
iV8tsd4gFinVo6Srj1CPEL8YmR4jKBEiPUJOsiV6hAhHE+gRstRJnkeGXwNxHi9xZaR5bIhlC/PI
+A0hy+uNRC9RXnvWAiT5019+rUMJD6GcZrR7NCd8Apo8Um5qiPJI4UpQ5SdATmlZHil/pXR5w1io
MI8UrzbKPEr+QqR5nKQEaPMoQUkW51EyHEudRwlTI3keHX/19XnMyFUR6PExlqzQowM4gESvOxOt
NHoEsEWI9H9/WT/3tOa5OP3OQJt1zg/Pfv70sr7tonY+7FlMF+yzn9PNphpYPiU3aWFcGw3XxiQo
quHomARqCW6PyXFU2gkyCWso5RIxxCU6SCYBWxt3yQSsIcR5MgVuZomhgWNlAkTHcrNMAK1GThfk
1lDfBTMdA6jikMFOXLJ7BjnOAZw1uAhp5bpBh16AI+fDTw8YeU1GH+jQZnZcNN0SiNmp4YxADFiC
C2Ii9JR2PCC2gVLuBsNZuJMBMWJtXAtobSDEoYCXlgA3AlpYkp0HaDmO5TJAC1QjRwFKG6jvHsCO
XRWnAE7Okl0BKCEO4ADAwEUr2R8JcAFi/28/famT8ZtkfqOd714oZ0Z5S2fE8YLZyHgAGh6AqQFV
wy0wNeoSfAVTRqq0A2FqhlHKq2Dgj+NqmBp3bfwP0zKMEKfExBAK8FRMi6Bk98W04I7l05gWZY0c
HdMxjPrej0naQhWXyITgS/aTTIfsAM4TtLC08qhgtoIAN8vfzz7WcPl2HddVZnZTNH0pKKmp4TBB
iVaCVwQ9N6VdHyjpK+XfMIQFOjFQwtXGU4GQvhB3BEZOAnwOCDFJdiwgJDiW9wAhSo1cBMjoq+8H
wAtcFbEfG2HJij4yfAPI9noT0Uqb1x61AAH+7Mvn+ukUYZ1JNvuSXVXMP+e0s02vEyPINwT5SVBU
Q6CfBGoJgv3kOCot4E/CGkoJ+oa4RIF/ErC1EfwnYA0hDoApcBPgEJgANskOggkQHcthMAG0GjkQ
kFtDfYfCdAygioMBO3HJDgfkOAdwQOAipJVDAh16EQ6K15/qjKIao2TNphzGJdF0SeDkpogTAidc
GW4H/OTUdjTg5K+Wa8EwFupMwIlXH/cBRv5iHAYoSYlwEWAEJdspgJHhaG4AjDB1Ev6x8ddA6keM
XBlxHx1j2XI+NoBDCPiaM9FLstcftgiR/sPr2s4Ki9SopGzCNvuQZGuzeQBQ6hHDU0SuR0xYhmY/
EXxqC/eIjaCWem9Ai5fwETPWR8dHawQxYj5eXCIUfbS0ZMv6aEGOpu2jJaqTwI/SCBqo/Ni5KyP1
4wQtW+9HSXEI0R8DGL2UfyTERcj/v/1cQxPV0ayym/hbahL5A9I/UnCKyP5I6cqQ/CeATm25H6kB
1JL6DWSxMj9SvvpI/CgNIEbex4lKhLSPkpRsWR8lxNEkfZQ0dZLz0RlAAykfM3NlZHx8kGVL+OgI
DiHf6w5FL+keAW0hUfs/1s9DcGpYslV2RbuB9wW96aIw6j0QuI+anyqx+6ghSwnfnwxBxSP4UdtB
sSB+w1pKHD9qzBqF8iO2g6BofszEhAT0IwYmPaYfMcvxwvoRQ9Uqsh+pHXQI7sePXp34fqyspYf4
IwU5SJQ/DjaaBfqjgS7CafBL/RBlq36IcnYVr0yoP+QswMlNEScBTrgynAP4yantFMDJXy1ngGEs
1AmAE68+4j9G/mJEf5SkRIj9GEHJFvkxMhxN3McIUydRHxt/DcR8xMiVEfHRMZYt3mMDOIRorzkT
vcR6/WELEOn/+fJNncoDFwZbGby8oC9jlPqmUo8ZnhpyPWbCEjT7qeBTWrjHbASl1HsDWryEj5mx
Njo+XiMIEfMR4xKg6OOlJVnWxwtyLG0fL1GNBH6cRlBf5UfPXRWpHyloyXo/TooDiP4owGil/GMh
LiJG/+xVHY3bRHO2peYx6n8zTh8vO0Vi9fEClhGvPw16asfs47WBWnH7hrPw2H28iPWJ38dqAzEx
/GhpiYjjxwpLdiw/Vo6jxfNjBapTTD9GG2gQ148cuzKx/Sg5y47vxwhxiBh/BFz0ivPHAVyA2P/h
55f1dEV1Mnk6+xCvvxm3/bCD+KtP9ebo1aAb3wrsW8FITRGvCka0Mvwp2Lmp7UnBSF8tH4ohLNB7
ghGuPn4TfPTFeEwQchLhK8GHSbaXBB/B0fwj+FDq5BnBRd/IKcYbgo2wbD8ILnxDeEC0JqKX70N3
1CK2OPx6WmPiBHUmebqmljIafFODRwpOERkeKV0ZSvwE0KktxiM1gFp6vIEsVpJHylcfVR6lAcQI
8zhRidDmUZKSLc+jhDiaQo+Spk4iPToDaKDTY2aujFSPD7JstR4dwSEEe92h6KXZI6AtQLb/8ref
a1ii2nENX+L/Sr+ljLcR7hvCPV50akj3ePlKEO+nAU9p+R6vCZQS8A1m0RI+XsLaiPhYTSBExkcL
S4CQj5WVZCkfK8axxHysPDWS8zGaQH1BHzl1VSR9lJgli/oYGQ4g6yPAopWwj4O3CGn/n/U8RJZf
B7P+gy5z45PZr3RKQa1wmlxvz+krUPZG7G+K/ROCqYj8PyHiMhwCE8WptotgQkZRy2lgwMt3I0yI
uT6OhckYRYyrYTr4RDgfJkNPtjtiMmBHc1BMhrBOLotJGEUDJ8bU7KCMW2Ma4GU7OiZBdQjXB0ZQ
ejlDkFpAhHvkl3oSJ7+2IeRLRlc0xg/S9INgpKaIwwMjWhmeDezc1HZhYKSvlq/CEBbolMAIVx/v
Az76YtwMCDmJ8CfgwyTbcYCP4GgeAnwodXIF4KKvgeaPFrgy4j4ywrJVfFz4hpDrtSaily6vO2oR
AvyXX+oZmcIak5xOFhZxtUD4kp3Hy8zI8U05Hj9DRcR5/KBlSPXToqi2cI/fFmrJ+Ia3NFEfP2p9
JH7sthAj+KOnJkL+xw5NtjMAO8/RXAPYwerkKMBsCw3cBhPBr4wTATVv2S4FzDCHcDAg4qOXuwEX
eBHOhwfHQUROjdD//p/8W3prjisGPA5IwSniZkBKV4ZvYQLo1HYoIDWAWl4EA1ms6wApX338BSgN
IMZJgBOVCM8ASlKy3QEoIY7mA0BJUyfhH50BNFD7MTNXRuLHB1m2ro+O4BBivu5Q9FLwEdAWIdv/
/LGOxa1h2ebf6E3NgcVHpHvE8BSR7xETliHhTwSf2jI+YiOoJeUb0OLlfMSM9ZH00RpBjKyPF5cI
aR8tLdnyPlqQo0n8aInqJPOjNIIGUj927srI/ThBy5b8UVIcQvbHAEYv6R8JcSFR+7/V0yjV9zVs
2SsY4R+I2ceITZWIfYxspcTrYweneLQ+RvyKxeobxCIj9THS1ShOHx9+QVH6CEEJidHHx0l6hD4+
hOPF5+NjqVV0Pi78OsTmoyWuTmQ+MsTS4/Jx8RskKl9rJJrF5OvOWoAk/+vbBycO16D8umScjSTf
kORxYlNDksfJVoIkjx+c0pI8TvxKSfIGsUhJHiddbSR5jPiFSPIoQQmQ5DFykizJY0Q4liSPkaVG
kjw2/OpL8oiJqyLJo0MsWZLHxm8ASV5zJFpJ8vqzFiHJn/6jnv0/qkHJt8ttfGs0+aYmj5ObIqI8
TrgyVHn85NSW5XHyV0uXN4yFCvM48eqjzGPkL0aaR0lKhDaPEZRscR4jw9HUeYwwdZLnsfHXQJ9H
jFwZgR4dY9kKPTaAQ0j0mjPRS6PXH7YIkf6fP9az/Hg1Kn+cJ99MHvsjOj1adIpI9Wj5ylDrJwFP
bcEerQnU0uwNZtGyPVrC+ij3SE0gRrzHCkuEfo+UlWwJHynG0VR8pDx1EvIRmkADLR83dWXkfIyY
ZSv6CBkOIerrj0UvXR8FbwHS/m+/fqnnCao5PH6L11vaGRtdv6HrI+WmhqiPFK4ERX8C5JSW85Hy
V0rLN4yFCvlI8Wqj4qPkL0TCx0lKgH6PEpRk8R4lw7GUe5QwNZLt0fFXX7PHjFwVwR4fY8lqPTqA
A0j1ujPRSqdHAFuESP/6U42Ka9WoJOvkj22yik9mP9IJwk2cp/Tmp8n19py+B6Vv5PumfD81oooI
+1PDLkPynzJTtZ0BU7OMWm4CQ38kB8LUwOvjWpiWZcQ4HSbGUIQ7YloIZTsqpkV3NBfGtDDr5NyY
jmU0cHtM0hjKOEQmRF+2q2Q6aIdwoqClpZd7BbMZBDhe/vH64yGvwKptG/kH62yMc6XhXEFJTQ0H
Ckq0Epwk6Lkp7QhBSV8pZ4chLNChgRKuNk4LhPSFOCYwchLgfECISbKDASHBsZwICFFq5ChARl99
ZwBe4KoI/tgISxb1keEbQLjXm4hW4rz2qAcT4P918ixPik2WJ1/Lf63e6T/vSL1885Ze+C1d0wsq
CF+rkWtR926QQ4AvL5bl4rbK8rS7/yHF29JE8jGa6Z2Y6Z1pJZMYs2tm3r15tl7d9jEyiQL/Idr/
ecaGAvqPm4y+DP3X8scF+4dFmlPbPPvBdgNKZ73/Kwns6N//bphjNzZ8rYqbdmEPH6yJQG/SpZFw
V6beSLZX50nOBsPrJKPPmVUy4GJ2flta/GEj+lNR60Su82xJR+QrUN5xIl/4R+9bLyyO9sAu42gA
vjWY+X2rj/E5K1Iz/eckn7Nl6LJ0F8V0pcjen06j6LSKDgJ0JTnbFqXnLy4uy8nTTbalbQPU5Z0g
EPvl1+js7Uysr6/fFKXTZs3wPmNQaeHZZwIV2lChAxW6UKH3oNCNgKfTwubTy0IbKnSgQhcqfPh0
4oAv74Bv74Cv74Dv74AAHIgAnRNCdXDBOrhgHVywDi5YBxesQwCZgZUCdQggQ1SlDljqgqVes3mw
KpxVIiQrtu7aIVBoQ4UOVOhChd6Dwl07bBQ2n75rhweF5K4dAoUuVPjw6ft22CwF3t6xgArs2yFU
6oJ3aNTBBevggnVwwTq4YB1csA4uWIcAMsO+HT64bwAZYt8OoVIXvG+tDqQxntHpXJ7+LnaqC/bL
7dtZpxYBWw5gKZ5EbSQ9TeYJHTEX+zpAa+fa8Pjhx6eHx6A+PK7O6egYtx8aP386K76ui68X2zWd
/vq2ZdFWU87fz5J5nmxYCOHm7gfEi8ofvPt0NsvovC+fFdmWTg/ub0F8Qn9hqdPGeF5QcrtorMD+
k82yluVS+ettEuf/mr2hy3Y2x/rzT+/e/AVqN464dvPM9hyuxRS9jGPyzC4bbPoMVb3LBJq7Mo+v
nhbU3OXa+nyVZQvQKRAdM+jxNVEXk1pewGNSehmPSellg5nUtYNeayJ2vdgF8fVd2NPJbJkwve3Q
NZ2t75bDtAWA6+FQsO0tj8v2lsdleyaDDyWGWJ7XSwyh12slhgzck5djM4ftqzGdQwmzyuF2MOsD
te9mft7qtLN/5RymX/5NukkreTxeLHIWUJKnlUayc+PTv36D3e2WQPMHAZf12WUcxmeXDWZ7qOpd
TM9dmQ6Wn2frTfL7ZhuvVrcz+pg8u2aTy2R2mcQr+u/7oCLQ7iI/e4fvq3f4PnpnyG/e6fnJO9aI
dv9O/8hPZgW1zEG08+XtMk3WyePNITCjgNajAKtKQa1f9vT3YVigJO6JtHVIuExNL+OxNL1sOEMD
Ve9kZ97KdDBzQp9Ip/jzW1pcXGfrogofoWv2FSuaZzdJfvvEjM+PBNo/5PrSQ67vPBzwKw/7feOh
+C+cDuqb7/FN8uALP2HbVa5j+vc1m/eVsZb7lnE3MwS7fCJyBhB6nDO/Q3+4Y4VcEwL68OEmBMCb
dJoQ8FamQ9NgftFVeplli2IfcQ71+6FAg7uWzWFvehWHfelVw6k7zXp3Enc4q9LBuNfF7fwyK7Iy
9LCM7q2CtFtM8iNL7KyOb07HN6Mbcj7XczYn2uLFZbJiU7ndpwzO4UTLtZHFp9fS67hEO3rdcCK8
5VluLxWe3UCAlTd5nK4TpszOLtK82MziFBbjQ8leuddr+hpML9rvEC++1j1AP0SBW65igF++piag
v2X7Gfa/9qyg/PXpfiryfPZqt0CpdijM6SQmaTzEDq39ZekqLbdIPZ+9q/o5dtX3ZLU6T+gFDy9k
dWvzPKCqTth85E871aycWt+HkT58KrHaVhd4rm35d1WmLZhe+Vv5ObF41u8PFfzGk23gyR+Pbg1t
XO4F7V8aqrvrtK86cL3rdao9cIfIV8rpa9q5aec6t/PasPXL9c5xxPbef1tk39fM0XT2+a+v3xyP
B/Akj1jjhlg6PvB0Wth8elloQ4UOVOhChQ+fHobA02lh8+lloQ0VOlChCxUqGVzZI7CRQIGNpHVg
I7mzfv2XO+sDhXbz8mZY5c76QOHDgL6d9RuFzafvrA8UPnz3nfWBXw4c0miBIY1Wh5BGhcIJO7Yt
D2oHNmQJOMLQ0yqW8O0vT44Bnu/UxoD1MlsdExvsyOaSG9h1PIIDu244yQGqfSfRgbs6RxakZRoZ
tg/9cBKyoOvUvGDb0OtyxE5hqpKo3e/HYJfehx6B+pMtsEUQ33N5WgS7jqdFsOuGaxFQ7Tu1CO7q
qORoHrRJcCobrufbflthwyWW77xwOysbPIs9vnUe5xqPd3nHu7LjX9QFoWu/cAL+VV2fFV2/1Vzg
+b5SogUvfw0oDLykFd9TjbuqG3xVYbVfVajzSeCm0G9C/8/XrZxM9W/gjyQ/j9P/MrkR1E7AbYyL
Opm1Ma/J9tZsCEeV+S7NQMGpjAo77/tMJEi/iQTpsOfbAvcpW5j2fBtLKD2t/PHtqxYpWezDHulH
2t+t4kVSXHJuO3dcP7Jc+0XkOdX/Htug7dpB6NgvnNCv/hc8uhvdsSzfp3e29r9WdGN6haDFi2u+
Nb3WvB7J7tSlgbEIwhecsY8vTPSj0AxPkrqTcVMs+R7wdFrYfHpZaEOFDlToQoWNqY0DTe4caHLn
QJM7B5rcOdDkzlE1+sCHwj9YKVAHHwoAqUodsNQFS5uTXBuc5NrgJNcGJ7k2OMm1wUmurWqKq5BA
daClQB3KUhssdcBSFyxt1gG0RQjaIgRtEYK2CEFbhPbxpG9PJdsiApJtkbseqf70XY/U+GXz6bse
CSh0ocKHT9/1SA+m4w40xXcg1daBImIcaIrv9ImIIR0iYrom+fKhkKR9j/Tgvj4Ud7LvkaBSFyxt
JhqzwaWODSYas8GUWTa41LHBpY7dZ7lFei+3CLzcuu+RmqVAHXY9ElTaiJDa9UjQb5t1AG0RgrYI
QVuEoC1CG6yDrXrSN0mdoLT+7lh3QdrlDxTVMQz0sXvgh0Z48xIK/1Tbf5R4Pr9+qs/pp1bL8poS
/WO+XSfp7FWcb4siXsVXxi8x1iEfNfsdXWZzWA/swQPInRBA7oQAcicEkDshgNwJAehO8KDlNisF
ZvcetOCuSh2w1AVLvWbFmsN5AInYASRiB5CIHUAidgDGfHvQ9H5PACq1wdJGd+Z50MzO8xSOEDGW
UHtgefOyRZyWX+uYtjn9fTx7ExdZBwUQEgAf9AhkV2YDv3OAMhcoO7LzZbB9T6TTvifyUPgiVWHz
vclD2euu0IEKXajQe8hyNNWVPd23gHf3IfK+Bby7D5H3IfI+vOMJejwrBdhbUAWqUgcsdYGnAXUg
AVQHWgrUoSy1wVIHLHWBpzWt0DxegPQ+XoB0OF6gapwE/AwI+B0Q8EMg4JdAwE+BgHWAP8U+GjQB
NWgCatAE1F6JVO216l8B2RM6YgAYC11gLHaBcdCFRuJRj1YgsNwHPd2Hng7tQCTQDkTiD3ywgwXJ
LBYks1hHDnbwIfI+RN6HyPsQeR8i74PkLdjwsOVh08O2h40P1mHXDzdLgTrs+mGo1AFLXbB04OM1
LPAwBavj8Ro+AT8DAn4HBPwQQKXVJ+CnQPoo7xYosFmgwGaBApt1VHkPQQ4hyCEEObRVnC1Q3FJo
feZCEhusgULSH6yLgrIofE/IWwJogbCAbAFV8qFNxj68yRi6HuiaCNg1EbBrImB3Q8DuhoDdDQG7
GwJ2LATsWJ44i6dxBx9UdX1Q1fVBVbfZLRCwWyBgt0DAbqG/k+0JxVovBfjV+xYL9eDBQp2FfnEG
/Xm+Y9nWoxFvVuA6xH4svs8OI5t4jqJBfa1fUfegvmHbTrk9P+I5oiIMXa92fqdtuR5vuoHIGzTf
QOT1TTgQeRodWzJ0mwhCnyuNda09+BbhOccgHO48IuA1Op1iEGp1lmutERx1K/YdVo62goOOwLVd
L+LJbTuo+5H4oRX0S3C7u4XwDMbZevl8k+RX99lGdulFHktkHppBAdWgMGi+YxkzzKezi5AoIHTS
2Da/SOAGdhR2Ti9CvwUSEYcjyQgJ6KyRndjNkWrEdX3PCjlzShIS+rbHmXXEizz6cN6kktTqhJ3y
zJtVMrStwCb8CUiorbzd8/mykDiO50RuvyQc9C2Ip20GVdPgTYNXs8EPm3dm8Bnts9Dj2rvGLuM5
omW4+UvYa+4SemrvW5MwWSHwriXQYQz6i8EtS+COJWjTGhS40i58woLCJ6xO4RM+tEvIhxzVPuSn
9iE3tQ95qX3SKnjDAoM3LDB4wwKDN6yuwRsgAgIyICAEAlIgIAYCcxjV53LcvUK4fS5NxzGBHMfk
rgU2CgG3NeSSAD0SoEMCdlO2dVt38Q3Bbmty1G3d1i8jzF2rUOpg8yUArZa/0XdvyW4Lr6HiPrSf
Pp62mhyGh9OGn2Ja8ywzSZ2UTshmTDuWaRfZFWWXzmfx4iabx/Pbe+MtkptklV3TDzRepUuWsO1k
Fm9mqyQuNmV2tjjfnFQi5nKVndNbl47YhzeCz2N0iWPsP410fMa4KhiX3Yvlztt338VtQe8w21zG
7GNmBizoFz9PS1f0VfyNXcO6+N2pfMXsit6H2mFfniesuMzOV2Xroy8Yz6thIblJF6VqlV2UzSSG
vv/INBEFmsjnu6iE2UWeXc3Okt+39Eevf79eZYfJ7l+eb4tk9ufPZ69f/mU3zs822SxhLYca+jqn
g8X67te7RkP/P79Jb7IcHgE80wJGbwHzPKGD9KLSpPcZPOnfb7MtO3/7frr3xGhuOvzxbXkwYVsv
/kqH6UODxvcTOzaC079Q49J+e12lY01SOqpvf6fz+Di/neXZKgEn7aEx8+hmLuKL5NCHxM5ITy6S
PGfRQ/Hm8nt8W7C+udEJs+H4JqWmZUMz/UE8n7Mz1PchBlCEgRmkR06qXNx/xOXMa7ZIlymLD6Ef
87pg9qrG6DyLF1fxNZumr9L1LrUym5aVa7L9pw923eab1j5BRc1sR/1p7Y0GirjjOpXAzU8tHQoW
pK1akLZqgQ4FdYR03BSMPKx21/XlMskTNibFjSjm2atq8lmuFZjmeycYgfPIw3nFq7+1CvoIamks
Xv1Xek6XKKkxXN/DGg6CmegP6NJgvot0uht+qlMZ6JdI5xnnyWVM55Bb+rPSRifMyKWAnLMo9mp7
w3yVxOvn2+uC3a4sZ3OXt+/ezpKrtGAKE3xYnmtahTnCo36ER60ZHJvZdGgEkz2LjIBHNkztLLKx
KPSa2bz+6dc26QNt9/AreD3fxossh3tC27Yt27VeOL0OZb2/y2Dd4u6WA9RKyj7OZuAtYEr3mCmP
ZRJsb8inN8kS23Mjz3vhkcf2yXqW7wZReczoI6d9BI7tOS8iRbcDV2/qP/2amm8HHr438GyuGGl2
GUeMtGcP1lt4vfb6ebbSMdIyugoHCtQFk4uBucUcKEoXzCzmWMMe7EGggz1It4M9+Cd9ZIBT20D0
8hK79Y+R7pLY7XiMNJhXCUyrBGZVApMqgTmVwJRKLQ9ysPolNregxObWuBP/xzPPELCUO6VVl9w1
XVJadcldo3yMdPsWdvzkPkGGhxMRtTdxO7Mpvgp7+/LHp5WI0Docj9/G58ekZRIEhCfjBr2MZ289
vWy4nfVA1Tvtq+etzDipVga2uwMsb9sYnl3HY3mHdy0Mmt7puTjnr85IOVaM9TWyfilGz7P1Jvl9
s41Xq9sZfUyeXTMVIGmTUSP0TYevXYf/uNW/0z/yk1kRrw/DWS9vl2myTh5vDGb017QxJPSJdNyf
39LiXdaLMiw9zlesaJ7dJPntU9mWIjMKaDwK9M+wNazNQ64sFFw5KIYzddjLzqGlS+6smqmPxxq0
NrYTvXA4zM0u4zA4u2wwkztRH5M7kdKS+tuPbT5pUrfy1Xka8ybhDTz/Mb+b7Xiu4z/mc3N921c2
/26rt9Pc21ZrMo90DW0bDduOz+VtK6/jGfytAYd+q9/Ab1lT7x4ap8kT6DR5Iug0+RA6RCeEUiKF
UEqkEDpBJ4RSIoV+G4cbERBlRSCHW+mUsh3I2WU7kLPLhuBXpQ5Y6gJPA+rggk4/F3T6uaDTzwUT
I7mg088FT3MCjxUj4LliBDxYjDROFiN3pS7426cdj/JPlBr8FHWryynqIXSMSgidohJCh6iE0Bkq
IXSESuiP5ni0IP+Tdf8lNksBp58Nwd9/iVCpC5Zyn2JvdTjF3upwij25/xIf/jYC6wCe3g6eLUXA
w6UIeLrU+IeHKBSB6gAomj0Cgb5eAn2TBPrSurlqm02agE2aPNbIYPNgN3s/Z++7l62m/XZtMkh/
EZutByonmjJ2nXCWKWN8rCmmjGVNfqnH8kuZ9jHp5FLG/KOY/y5RTZVoJqU3OOjt/1xs55cz+sO7
LCXv13Qgz9ng8CFdJ3+5Hw9oW6i6A1q0/8k8ox1Avi5OZldpQf/CNh+XDzuvXIRltpt8u0rg7sE2
E4NpZasyNjYpBh6kGDBNwuQXMG0AeUYzY2D90pnVbHbUEd/SYkcOpIBPB4KPB4LPB4IPCIJPCPJB
L6gPbn7zwc1vPnhAiA8eEOKDm998pQ8Iwc/COCQml9rs7ad20WO1Xfxvt3S4i5//SKex8dZYT2l3
krEvds+CsbCRD47IB6Zp6LvC+NQm1Lej5eCZ7cgxn9azDtFuBIx2I2C0G+kQ7abSSmMCLPqtNEy3
JmvFMYPnNetZdnGRlpvazvN4Pb/c+0rK+etFHl8lbO5yMmObRsoBcblNF+UmiNLdvkguqDUqx9r+
7UsnSeU+3e0YKR1k1f2hsx9cm5hGgWQZ+u7Tq6dTyTm13Y3vmEc1jwvOnW9OEFqBZwWPbA9zrMj2
o+ix3W+eGwauE6iacJJYTmA/9oqR4/vWYy9oW/T9dE9IOXTrembbgc+zRa68jmOLXHndgClsgdp3
S2DLW50jW6ev0iXt5jeVb4zWoew0FrPrJC+Yz622pfput3y5Ur7fXbfbPL8L5wF3VNtC20QzVXGb
FsFSE9NK7P7K1TiGzG7cM98yZ1XGyZs1eBMIwoijCdCrOKxOrxrM6kC9u1idtyod8ijE1OY36SZN
ynPD4sUiZ+eC1WUXanp6+ytYFhH66RPb5TE8u4xnvzS9bLgN00DVO+2Y5q1Mb+PnabWJeqe00b9+
g01vCTU9IQ5PJo3yOh7js+uGsz5U+07m567OGPnShh/zQzfkSZNVXscz1LPrhhvsodp3Gu65q9PB
+qwqxYb+O/vC7xVyMFeCJ9LYjuv5PDlz6GU8OXNcdlLAUDlzgKp3yprDW5kxU6IJGOYdP+Ab6NmF
XEM9u3DAwR56gW7DPXeFpKZGG9z2rhvxfPzssr7ru+oeAzUB6D26NADuyoyQNE2KqPh6Td+TTUT3
rv7ia12bYsf9BGF4Av2yeTrPD5HtBdaLgE6qTvfd4PPZq90YWH0HczoSJo3HOMQLWaouelm6SsvN
Z89n7ypk7KrvyWp1ntALHl5IPOK5nvX0A4HaOpZtR+SF5z147k+7WXnZg9+v0h4+2nXdwA+dNpUG
Hu56nhMEL2y7qjpt6/Ti38pv8GR2nX1/KA40X9wJI/fBwz8yKepuJ9dei4IqHzlu6ActXxyoPu1I
PftF2LbywB2I7dth+CIM278DZEPfthzyIvTUUbGH/6hc3+r8RflByDLBSv6gSGRH43xNbugQXT+l
vaW4PyTiBD2/IuIxdVGqo+SX652jhG0p/LbIvq+ZSHr2+a+v3xz3jHiyh8h2ZzgR6Awn0voMJ9Lv
DCfS+gwnS8AZTqTfGU7EnOF0PJXa4UaGh7/1wXRuPlgHH6xDu80U5W9DG+JAS4E6lKU2WOqAd3DB
0qfPsiLQWVZEwFlWpPVZVqT1WVaWrLOsSP+UcuAxYgQ8R6z1WVbwQUcWeNBRl1RqlqCcWlbvLUWk
wzYaAm+juf8SH/x29yVCpTZY6gD3BWyx+xLVDDbs0yMQ6OMnxz/+lt9585vsdKLYke/kkbbfr5X7
4H19ME9dy/ZMOrRn0r89Kx7u+f7VpzbHybrh4Sz1/XqRrels3mwuU3p7krEt5q1Jxrom8dlTic9M
G9Er+dnL6gK2ruydAc037cBkQeuQBc20kWlkQjN2HsnOdz3BzltywzzzF0mes/DaeHP5Pb4tYzAb
3Tv7iG9Satt11Q1UPcmdqx7y1JtJgNm//sT+ddMsTAo80w4mkgbPGFnPRBU1ux0LIehiNdBPAR0J
Bh0IBh0HFgFeU+gosOi4x/SJ2AULil2wWscuWMdiF0LoRLgQOhBOxGF8bT3WFuixtgbxWEeAZyMC
/BoR4FmBzhWCDp6KAJ8K6K4FvbUtPeWki6e8w0FPAo5+G90/qtCRW6b9mfZnPKImz8lAeU7en/7H
05MllnLkwG55/N9Hdh8GQcCz+ZBexrP3kF423NZDoOqddh7yVmacbceDmt0J3JAn+Uh5Hc9ORHbd
cFsRodp32ovIXZ0xthwPanniOx7XyezsOp7th+y64XYfQrXvtPmQuzpDWP47/SM/mRXx+tA3enm7
TJN18niDCIR1BcTxPJunLygv5OkMyguH6w3AF+jUHfBXSMIm9IGtbVlcHT+7jsvW9LoBTQ3Uvpul
eavTZesxnYev0sssWxR7Lxdk41BYF++SKOTp4tl1PF08u264Lh6qfacunrs6I+wvHtTwPt+37fN9
2v6QX7bf88P2JXzXxWWyYv337psGO25RCzVQWHIhRduFJG0X0rRdSNR2IVXbjbg3xVnQpjir/6Y4
EdvSrK7b0gJQ3A5AcTsAxe0AFLcDUNwObLAOEViHCKxDBNYhAusQgXWIQJEf3J4XgtvzQgKK/AQU
+Qko8kPb81xIZXUjQOx0IZ3VhYRWF1Ja3Yh/W5rVelsa6bItTYmNYYEN1SGwoToENlSHABRcAxva
xBLYYB0isA4RWAeoGey/Bei3LljaFJ4JVIcQ3CAXEohDSEDhmYDCM1HY8XH8m2z/+Xl82zqPb+I6
0p7A1jAK3V6y/oeXvzw95/DI4ZzjQ5zNPpfTnT8Vs1fJVTZnKQvms9PkentOK95+PtI5y4XrW7Zt
8SabKC9Wp7Vzvr1u6R5GbWFKnGgYgDPPAJx5BuDMMwBnngE48wwsWacqki4nCd5zaJZCoy046wgs
cLQFZx2BNbWTHY09Bh4bf3w6yiyw6j1Xch6vs/WRfH62y5XPj17Gk8KPXjZcCj+g6p1S+PFW5nG5
ZZPHKe3kmC/8Is2LzSxOF6A3JBRnVvj7Brt8sMcHO3ywvwe7e0u5AMKRVSZIWgAT//iQsOBDuoIP
yQpg0p9xNa5xQzfbpZ2yoLRTVuu0U9bRtFM29PKsFPjmbOj1q1IHLHXBUiU1RhVO1uuVfssC029Z
YPotq0P6rTFm/grovQporQScaILzTHCaCc4ywUkmpDQOHtbaPgGZBenMVmud2YKELqu1zmzdjYaN
QkBnhqRFH1IWfUhYBBNv9VG5rf7J1xwo+ZoDJV8TEFDcJ/Wb1T/1mw29/H40hEptsNQBS12wVIqX
weroZWh7rqkFnmtqgeeaWl3ONQXTgFkdUuBZYHIwC0wOZglKgWd1SIH3iN4gzeNjHfX4jO1tUUmD
MqOyGZXNqGxGZTMqm1HZjMoqeyI+vnrb6qDx2ua7j/EiXsbFPM7N7rspZDU0jcSkNTQNQceGUKUy
7t0GPNMGTG7LLrktTSMZq5HMqbE2VWrLWl7L22zLjiW9T3y+S2WVJvAnbxlrTi9VqTH0FHLTGStr
mpxOhOFAAf/JyEGr7zHAg9q7135NEZs1F9Ty5ad8vsoyOG7w6Pr6SNxgx8/RcWyLODzb68sLefbX
lxcOt8EefIFOO+z5K9RuK+55eYD7blF2Mlsm68XD4znvTvmmjQHcgR2KbQahF9lc++8d+/ALD4jP
85Gzpw/WIKBX6dIcuCvTYV92Wh4880c1Wj+6854ItTvYqU85fpVYcNg0HDcNB07DkdNw6LR1PH74
wX7Bdr5ZIsA3SyQeV7nn/2BPiQUdzbfn37wDsCvFgsMCVN6hY9oB7nZg/HEaZMOcwQrrmo7sF2mZ
Suecrr3nl3sFppTMLuhMLmFnxZ3M2BSqPFtiuU0XcXlOCHPVLZILujCvFNj925fSSyW27yZMpZJa
3R86TcS1iWkRGPKjfvz7+1ami+qmW8XfU2M2lQ/6NIYdx7CL7Copj+aJFzfZPJ7f3pvuQClfpUsm
gZ/MaIe8SuJiU36xcb45qVZpy1V2Tm9diqYPb3TMHeIY60/hjFdjWhMK9XgolGkgJgzKNIKJh0AZ
+5vwp0fDn0wDGSP0qTIaXQJcpcv8vjugFSvNXs4m1nS6SC1YFLQBsQLIOWO+dZRRbMaSE4hgM0ae
0EnbxtpjWHvL4lw28beEDa+3dxLaCR1o41W23CZ0DsXOFNlfy07gruSaqoi2knST0v+8qQ6jqkxW
TttWyTJendwJs/RK2nXk+xsdHOzNrjtPwNHbNQ3EnMP+yDnspk2YQ9hNI8Af5W4srGGE+6HRjoZC
tjXZkQTJYPY+MHkfmLsPTN0HZu5TLoVpAL17AL17AL17AL17AL17ACYthHNSgCkpwIwUYEIKMB+F
col5AujdA+jdA+jdA+jdA+jdA1/p5OSmBeBsAf2CHs1QbQIeTWvQPNjxH2ctzOaz023rZrst0vjI
8aH9ztYm4ZDHPfc767m/1X48+vk4gSPaDqSfHchwdhinSdQs8SGb0y/m13W6AY1hizWG50eu0wtC
dYfBTGKHAbEdr0+NdrcQsCb9z7go6MqT9Wdfb5M4/9eseX4X0LG5x2x49Jip9hYEZ8afP50VX9fF
14vtmrXSwGdnw5eCx1kyz5NNzI5tv/uBF/gupfXu09ksoyNvPiuybT5P7u/g2C5xPHUm/rXXi1zf
I8Ejr2dHFn1ByZPWFk2nfmoa0GwE98NmIqNI+L8x7bQ3ABj7mzjxJ+LETROZRLjRwHPDZ64f8GRt
sSPiHSbsIIEX8pzsR58+3Ml+wKt0OtmPtzJHEnaUQaHMB30YE7qYXSd5wVzQtUQe+wCkagcRnQcy
dPNK1LrP+QJm9rBFNg/f4Urqwy7jaA7sssGaA1T1Ls2BuzLDpmoa2qLEskKeDD30Mg6LssuG02KA
qncSY3grM1J6pqFN7/g+V4YuehlPfi562XDZuYCqd8rNxVuZ1qbfAC6PPxW1uMS98Y+kaPKF2t4K
eExvBTyWt4LhDN+sdye7c1alQw4uOmVPb9JNWsWWxotFziKK67GI1PL09ldwrKDQAdyzCIfd6VUc
dves4XR3oN6dJGfOqvS2e06Xf2y7+C7ylP71G2x1S+ggHwR8efjYdTzDPLtuuHEeqn2ngZ67Oh3s
P8/oGu/3zTZerW5n9DF5ds1E5WR2mcSrgyk9aH2hfb3t2xHPmo5exmF7dtlwvh2g6p0cO7yVGcLw
3+kf+cmsiNeHm4Mvb5dpsk4ebw+B0PYQeYRrje+Rvml3q3sM1TiA9+jUOHgr06FxsJoUtBmUPf/9
TgLI6IEn1OhhxDPjY5fx2JleNqCDNwr6eXcj4bO+hD6RrvDmt7S4uM7WRaXVJHG+YkXz7CbJb5+Y
8ftiBdxumbbvv/PQtkfPsM3q0Cv5Lr1edBOg4/zme3yTPPjUT1i+h+uY/n3NJoTlvqF9C7mbMoKD
ABG6EAgcnv6AXdZ3EKjuMdTCAHiPTisD3sp0aBmr9CZZpZdZtij23h+o/xcq9hD6CfCoPeV1PEsA
dt2AYVdA7bsFXvFWp4uds/XyOR3sr+71+51g/1ivL9bsfOs+vlXfkGu+nis+8eu96+J2fpkVWRm7
XO7+q7SdFsu9yBI70yMe10yPeFwzPeINONMjPeP4iCfA7ps8TtcJ0+1nF2lebGZxCntqQtlhe7tT
n+v7nHanPgOFhxuqyLO7U5+BX7pQode8nPvMadLzzGl1YguPv1utxkT1TTAfWm17iKwHLdZsekAQ
UGZsjzSfrDGsiRJ8JErQNI/J55I1TWDKmWSN9U0e2UfyyJrmgSP1qLEj+p0AxsS404kZ+2qXTOxD
i2RiLQ02dCoxAqUSI1AqMXIslZgDHWnqQCeaOtCBpo4FPN2BjjN1rDaJzAiUyIxAicwIlMiMQInM
CJTIjIDnuRLwPFcCnudKep/nWt7BdqA60FKgDmWpDZY6YGmjDmVpM6UagerQONX3vtQGSx2w1AVL
vWbjHDGpl2MBT3cs4OkOdJyoA50m6kCHiTpWq5RiBEopRqCUYgRKKUaglGIESilGep+mSsDTVK0O
p6mS+6/gwW93X0Hzt0Addl8BVOqC922cKgseqUuaZ+qS+68AKnXAUhcsle1b0iPFnvkazdc4ha/R
eHpNssNhkh2atqBhqsNfz1osLB+EFm3zdJNui/ary8bUnk34GzP7u0IbKnSgQhcq9JqFzYGk2Ydb
d08HCh2o0IUKVY0twk2h3yj26uXT8XWhW/sIstUiu4lPZqfJ9fac1pT2lEdiKB3CkxWBXcYTQ0kv
Gy6GEqh6pxhK3soolPZEZNMIPZ4wenoVR8OgVw23hcbrFUDPW5UOEdXFZbJiW+V2bmxwj1x0zMzH
t0jxGjqyXlgclmaXcZg6Gi4hatRrq1Q0wEapz0k+Z9HwyzIU6eBDptNa2sfn1OLbal98XFyWX/dN
tqUNAYxYcAJZ3T4saEAyN4FkbgLJ3ASWeUGVV4LIbnUS2cedAvYIbrf6BbdboLxugfK6BcrrFiiv
W53lddjDA7t44ONi4PNi4ANjwFNTAhuqAy0F6lCW2mCpA5a6YGmjDiHUEFkpUIcQaopVqQOWumCp
1/w8AWULkhYJJC0SWFoDlTUZwqbVRdgccxnSb5uJ1XObSQdJ0wIlTQuUNK2ukiasqsOyOqyrw8I6
rKxD0vq+H2iWAnXY9QNQqQOWumBpow4h1BD3/QBUaoOlDljqgqXKnmVk+iPTH5n+yPRHSot0n163
WqJ79fXaepOsk2WeGSeD4tvLjHmnduL9ocWPyi+d7G0Trkw07DIerZ0MmHwGqnonrZ0Mm3xmDK19
+AZBgtDiSlYZWly5Koc8pi3oeT5YEFoKJBkf3qZO6PIkJWGX8WQcDt3hkpJAVe+Uc5i3MiOlGRdh
fJtwGd8mXMa3yYDGt0k/49taZR4e3vhuwPPh06t4zg8JhvvsgXp3Oj0k8PTJODy81UPX8nnc5PQy
Hj85vWw4RzlQ9U6ect7KqJRzePgW4XPln/W50s/6A2af9fsln/XF557lzjEsYKSPCM9nzy7jGekj
MtxnD1W900gfEV/vFLPDN4fIc3jST7LLeEJo6GXDBdEAVe8URsNbGcF5ZQV8837kch0jFLlcxwhF
7oDHCDWr3u0YIc7KiMg3KUKLJQ5XDBy7jEeKGTBhcL9swY7aMXCDf8QKRr6NHP2lQuTV0B5+0sXD
3/Ryk35ebtLay02kepgJ7GFWKtIDRHnEPM7TqWhhDqr7kl+ethjgAsup93t5Np8bT6Pa59kby+IN
ETC2NUloH09Ca1qIyUNrWsHkU9GaBmCy0T6ejda0EDQJaY0pJxU1aswtPT/t/kt9ePY8XcDtY4Lu
UpnSZd2cju4LNp0/Ty5jauot/VlpohPWu5dH1Bz4G+erJF4/317vnI20nC0G3r57O0toP8+WEbC/
0TWNQpFGsY432zx5fh4zsxfZast+Wsz+XPYMiyoNdVbs0hXHu3S421WcV21lv/Bj+k61ELyYbfJk
d+IhXWou8+wmKf4CtgIzqE8rdbUxsY7Zqw+tdsTJ2MFm7VKMkdb5JQiUX4J0SzHmQU/3oKd70NM9
6Oke9HQP8u65oHvVBf2rLphC2gU9rC7oYnWtVumbLTB9s9UhfbMFpm+2wPTNcKI30novL4H28pIu
e3l3beDB5R70dA96ugc93YOe7kH7R13QxeuCPl4XdPK64D5uF3Tzula7dKkWmC7VAtOlWmC6VAtM
l2qB6VKVTrdn2qJpi8YHbrL3Kpq91zQHLRP4fvr8ocXZ4MGh1T4l12WwZcuZ9es1fSm2uNu7gYuv
b7brcl3/55/evflL2QECP3pN7UB/xrSB/Q+dwAsJ/fXpPqb8+ezVbsdBtdqf52mRQPenV6SrtNQM
n8/eVZuS2AXfk9XqPKG/ha959ClABX3LdWznweN+2mlcpUv6XgDjqiXwTNtyPX9XXdpw6ZW/lVGw
J7Pr7PvD/ZdPPfQj27Z95zrb79tuU91jbwnUmBASBmHUtsrQHWzP89pXHaZm2+pM94ZqaxyNxpiw
Qyf8y/Wu52VOw2+L7Pua7Xo++/zX12921QL6W+9Yf3s8Nr5tj8sOv+CLi7f4ksPS64aLjLf6ZSiw
1M4PK35oVezcM0vAuWcWdO5ZKdZA7+5Dp5750Lv7kGDlQ+/ug1sCILUqhM4aA3OAgilAwQygYALQ
CHp6BEllEfT0CBIrI+jpEZx+FN6N0e7EOav3iXNdNkUQcFMEATdFkK6bIlqmgiUiU8GGYErc0Abr
YEMcQjAlbgimxA3t44mhlTnpyhJw0pUFnXRl3fVCjcLm033o3X1IpvKhd/fBjTGQRhVCp0uBGf/A
hH9gvr8QEgkj6OkRJJBF0NMjSKKMoKdH0NOBM8asDmeMWb3PGOuSfJKAW4MIuDWIdEw+2TbxIxGV
+PG+F2qWQnWwIQ4hmAAzBBNghrbCwj3YnfXsj8AOBbQw+FEd+Sj6N9Mjjayt2RVXuD+9Pm11IFlt
d+undJnkRtBUeY+Xsesodl1kV0kZvBcvbrJ5PL+9t9zOe8Eie1fpku0TOpnFm9kqiYtNKWXH+eak
ivlZrrJzeusy7OfhjY6F+zrG+BPY3mcsazb3Pba5z7QPs7XPtIFJb+wz5jfb+h7b1mfaxxib+iqb
0cn/1VH372xNZ4oFc8/R9sMKoG1e5ktHuD3TGHIEQx6sx9eLv9KF2KE14/t1O1uj0b9Qy9K+e13t
1EpSum7b/p6u0ji/LYMKQUEmNDae5gZcY+wRjL1lJzFs4m8JG1pv74SzEzrIxqtsWcZtsa2z+2vZ
ztxKpamKaCNJNyn9z5sqs39lsXLGtkqW8erkTo2lV9KOI9/f6CCMjF13noAjt2vah9mefXx7tmkS
ZnO2aQPIt2YbA+u3MbtmsyMRrq0tBiechcP8wE3BYOZjcEswGOLHHeFqQRGuFhThagmIcLUERbiC
+7HbbYi3oA3xVqcN8f22g1uDbAcncHAXuAEU3P8Jbv8EA7v44xotKI7IguKILAFxjZaYuMZxD9U2
29Ab/a/5Bsw3YLa/m+BAs/kd3PxuGoOWW9/fvmxlNb9htTQ+shnTdoLIDl7Yvc7rvL/LcDstq1sO
UCsBC9H/ZLsul9VW49skzv81a272BUzpHjPl0YVoa0OCU6HPn86Kr+vi68V2zfae2rZneS8IOXlW
6hxnyTxPNjE7+vLuR65HnMh6wQ7mevfpbJbRHiefFdk2nyf3d1Josge94VOvJzuIv0XrqScqAFqO
I67lPHMdO+A5XZREXhDRd13vC2zHj0Keg4dZBYY7ehh6nU6HD3NX58jBdGWQCFOmD2NEFrPrJC+Y
MF07lXDvk6yCie/3drNL708qB88htwW2Ed8hjsN1NqnreEO0kbICwx1LC71Op4Npuaszzrn0Q7eH
IODJ4ECv4jA9vWowwwP17mJ23qr0Po++7uaklqe3v4LdkCK7AUKIQzzCM1pEIXE8ctgVEIt4FvF5
zi7e12O42eaRF+s03exTKQknVgtoDGFAPJsrlQsbBvzhWkNZkSFbA/hmHVsDf6U6tIaEPpUOD/Pb
g2Or2V6TOF+xonl2k+S3d2MFfJK1HwlsJo5vWVwnHFsW1wnHA2b7gare7YRjy1LwGOvBJwMez1zA
45kKDKcvBL0ED86KdLBrcZmsWCe/synYu4v8bG2ur9bm+mjtAb9Zu98nawv5YrnOJJehEA2Y6bJ7
kktiucRm2cQ6p7q0XSd0fa58lx7xQ9t54UVyU176gRN59gvf5sx66UWBN0rmS6tHwkSXToDIC8vt
lTPR0iflpTLt2+3TSp3eTbRHa9EuOaaETnp3WvmDLHshEFe0O0weKHSgQvdh4r8QiilqpGwku1Ig
rglM2kjArI0ETNtIwLyNzbx1pEPeOgLmrSMd8taRDnnrLDBvnQXmrSMd89Y1z6237loCUGg/ecK9
ddcSnjr23rpvCQ/SJIF58wiYOI+AqaYImDqPgLnzgNxhpEPuMALmDiMdcoeRDrnDLDCJlAXmDiN6
5g473s5cwMrHWg9kDXFW9p7O5KZ6oq/PL39ulZM5PBx4PsffSnfSkVV8r/XwcK6ZqJdfJupvix+P
htA4gSPWBn4vydEfTgHt6SYZYA39IZvTadmv63QDGsIWawgTzqRRgjRjf8Q50oxxp54CybQAkwXp
iSxIpokgSoRkjIknF5Kx5STSIRkzmyQ5TyTJMU3E5Mlp5skxrcKkyjHNQNdkKjWzHT0usL3R4GPl
PSirhwdl9fCgrB4elNXDg7J6eMc9rmJ971Z737vV2/dudfW9B1BKGVYK1CGAkspUpQ5Y6oKlvOfW
WQqcW9fF/9/13Lrdt/AgG4IHnd3mQRkWPCjDggdlWPCgs9t6RB9YraMPLCj6APYfW9KjDwIovcf+
W4BKG37pAMrwsf8WoFLu09OsDr5x+PQ0IigCAtXpaeabNN+k+SY1yH8jIl6j32aDIfcq+VG/2JFo
gJ1qZ5v44gKK1iBizUDCsOe57OwGg5nCs/rVhl3f3xi/0eX8epMkORg/UxfpP7WxiGPXLbKOr2Kz
9lb52EhjWMRhMca00w6KMfY3ITGPhsSYBjIBv7sx8nTOITLWNg70pgPdtAnjPjeNQEfn+aenneet
TQa6JkDvMeg8Bn3HoOsY9ByDjuORXedKHMcBnwUDHwYDnwYDHwcDnwcDHQgDemhABw3on3GgIwFA
7wzonBnRPaXEkQD3baBZCtUBPpECPpICPpPCV9hVatqiaYtquwg/vX16TPat+ph8vY1nn5Lvs7fb
dJ10GJ2hsCooqAoKqYICqqBwKiiYCnKXQ85y6HwayFEOuckjhXshrO/fr+W/+9BmCeGTWtu/TFfp
9TU7m8SsI5R2BBrrTj5JgmkCuB3Cxr5q2Jfdi4l3d7tlbwt6h+ogr5S5f6+Ym2ielmc4XMXfypOK
733AxeyK3ofaYV9eeQlLebCSC+kLxju/YHKTLkpnQnZRthTIK0gi00o0jh14WV3ApvC9Awh80xJM
FIlnGoEJJekWSmJaCa4EK8aeqHKsGHNOJdzLWHpyMV/G5Ca5ztPJdUwrMeGBYHigaRgmRtC0hBFb
QnHfGEpFl44ey5T1EXRuuC6YyarBIs/ixVV8zVb1K8q7ag93a//9TBJcDJgpIop40EPLHY096WQ3
BYNCx83mRGwHCsikpUBAZllqg6UOWOqCpUoGpiqQy6hlMCCBggFJ62BAAgUDEiiTEmmdtYX0ztqy
b4cP8m/s2iFUaoOlDnBfIBBv1w45AxIJGJBIOgQkkqMBiW1zlhD8eYTM92C+hyl8DyZMUfnp7Re6
7ICdlmu6/rygE93yxEx2TNZeAi/Fqos8vkpYtNLJjJ0UXeogy226iEvtkwXALJILZoZyYbN/+1L7
rhzYu4OiS9H0/OgxXK5NTJOQ3yTyhK1m42bLeHXQBJhOceeZBh0ah+r26a9nbWwXRoe2O90WRUqf
8iZZ7DRT2ISe0+uId3r5cMm5LK9fnjBP6oFqQs3iBFbocRwtX17Hcbh8ed1wx8vbnu+FvU6YL+8w
5CHzZWgA0xoPIwMWs+skL5jUWAV8LCpFae93qgJMqcUYv3nV/V7fRSVBamIkrYUEgc/RPuhVHK2D
XjXcoYmh1y/xW3mDIVvGdZLRB80WtLsu1cfzVZYtQKlYWq/s+CHf58+u4/n82XXDmdgOQ7+XidkN
BJh4/5Gf3x58xiezZcKcmPWz19kPaIdxdUVbBPihh7LaQmj7AUdTYJdxtAR22WANgVgW7ch7nVW7
u4XYxrABpvJ/Kmp+631zAEONnMiX1BpAUeTJtmBxNIRBJ+e9OnxLoPErhyLtB27STVpFIMSLRc6C
T+rOamp/evsr2JlsG+s/0Q30TPZa3WGcdpCnRbkjaReqQP/6DW4FlqwRwXctO7Q5xoTqQo7mUF04
XIOgHaYbOb1aRHUL0U1inq03ye+bbbxa3c7oY/LsOk9ZM7hM4tXBSgFsELIGhWck9CKe1UB5HUdz
KK8brDW4rh+RPm2hvMFoLeE7/SM/mRXx+nBTyuXtMk3WyeMNJJDWQBy/eVh9mwbCruNpIOy6yY0f
rC4FbQzlGHEfpAaZPvCkLR8sP3J51g/sOp4FBLtuMNM7vZUkZ3AlCTJ9Qp9Jl5HzW1pcXGfrohKL
kjhfsaJ5dpPkt08sIvzITCP1XUTQCcHme3yTPPj4T9j+w+uY/n3NJpNlkOq+gdxNN8HBgZjWoG9r
SMsQ9z+q+cBjc4BIlpmf2ZFFOMYBdhmHrdllw80Qo7DXGMCuF23xVXqTrNLLLFsU+/0t0LgvTTYk
bkDskGfOV17IM+krLxzwgBjHdUm/I2LYHYQbPlsvn9NZ39W922jnJ3psrJcnH7uRHfHM/9h1PPM/
dt2AnsTQiaJ+nkR2B9GN4Lq4nV9mRVYGfZSbDirZsIVMEEnTjWzC0xDoVTz9P4kmMtQXl8mKLfp2
nT642pMXzuESi8vK1YUchq4uHMzWEfF8q9cHX91BgNU3eZyuE+YjnF2kebGZxSnsJpbWt7vWCx5V
h13GYWl3OEXH7fVJuwN805+TfM666GWZFuogxmORsJkcXa/NtpXuHxeXZY9+k23pRw/mi3ECeUqe
5fv9lDB/OOU27Bc8FjqepOMUBX+FPU+4LG8w3Lw56HuyYiD5aMXTv79sYR0vCmrW+c66KxOXqnJG
VWNYtJk0jWlNEs1Hk2iaBmLyZ5pGYLImPp410TSQCWRkM0aeUjI2Y22TYethhi3TJkxyLdMI0OfV
qln4SHam9vYFA5MIlJiJQImZCJSYiUCJmQiUmImAiZmgp/vQ033o6T70dB96ug+eFQrlZQqhtEwh
lJUphJIyhVBOplDZlExQ+hcCnY1IoLMRCZT+hUBnIxLobEQferoPPd2Hnu5DT/ehp/vgyYwOdDKj
A53M6EAnM0KpX0Io80voKHkyozpJiEwrNK1Q0dQ/Zo5lsv6Y1qB5wp+z0x/bRCtEtSN2z5L8PD1i
tsB2I56gsPI6+srrPlH/u5sMllvCdaN+uSXoDcZPH1Kz8bFEtu0tTDxoi1ybuL9qY9y9iautcjzh
3x73Hjtw05/Xe9OfJ3jT3+CZIwZuFBFt6Tw7ABx23WGb8DmbRFTdaKjQUOh1OkWGcldnjB3jAzcG
2/J9nj3ins8CBg/6B4+vLZTPH25fAPQ2nbYFcFdnzF2hQ48avuPw5JEI6WWHbSLkHDH88j5DDRjQ
y3QaL7irI3W30MBtgG2R8rhyR0TEqXcMnsWTW6SswHAbxqHX6bRfnLs6AnYPDGtrFQX1cU868H1Q
0vZBSdsHJW0flLR9UNL21ZK0wYzmFpTR3BKU0XzHv1kKyXk+KOf5oJzng9nEfbVFZdA8UAb15tsp
Lkue/eOnNoqG9aAnu6Xj5mplsk+rHeVvjIs60t+Y10T7PxntbxrJFOJ7alY+thzpZGNwKgQGmoBx
JmCYCRhlAgaZgDEmoIsZ9DCD59uA/mXQvax0jANuCr0msx9+ftnqLBW39h3k6exDvP5mHKtKz2WN
bUez7SK7SsrY8/0Z4vfWO9ivskqXbDZ0MqOznlUSF5tyZhvnm5NqUFuusnN663Jce3gjONOeSxzT
ACayljHWNUuZp5Yypo2YvcumHejXDqo5X+8m4JkmYHawd9jBbtrISG1kZze6KCiP9rv7zPdn+5Uz
izWdPRYsvRttQ6wAisAzX7wK1qRf3qZKSFDLRnCbbVkg1f1q/4m1nJntTy+/hLHzxFJMGIOPZPAt
OyhzE39L2FB7eyewndBBN15ly21Cp1SHse8sAUWl5FRFtKGkm5T+5011xlpltXIWt0qW8erkTrml
V9IOJN/f6CCvBbvuPAFHcte0EZN14kHWCdMOJuCYNkYewcjVJ5vSgZ5+ldSAzGTPV/Rrv8s1BNrN
NnYzO5aP7Vg2DULbTcv/OG1hucCqW+42ZxnWX+bx+ew0ud6e05cyRlQ72NeY2cRKmLYwsRBwY2gT
QdEhGNw0FxNMUQumME3CxFWY1mBCLLhCLExzQRptYQyLM/DC2HVyMRjG5NMNxzC2N5EZHSIzTHOZ
2q5xY2/N/fQ1Ex7Z+M9rQAWzkjnQ0x3o6Q70dAd6ugM93YGe7kbA02lh8+lloQ0VOlChCxWqdcTJ
yKkfRs1GF4bQ8S4hdLxLCB3vEkLHu4TQ8S4hlIcObPQEbPUEbPYEbPcEbPgEbPlK5OMLbKgOtBSo
Q1lqg6UOWOqCpc06RGAdIrAOEViHCKxDBNYB6gdICB73E4LH/YTgcT8heNxPCB73E6p33I/TeDq5
GwUav2ymQHEaTyd3owBw+cPUf7tRoFHYfPpuFAB+6UCFLlSo1iEzfZLPWD2Tz7TOiUla58QkUE5M
AuXEJHejwIPDcELogJ0QOmAnBJ6+GwWAwkZGTgf85JqtntyPAtBvHfC3LvhbD8hv2Wz6rbOCEjAr
KOmQFZTcjwIPnrYbBZq/BTjsRgHoty5Y2qxDBNYB6gP2o0DzDkAPGESQLQKoH9iPAs1SoA4hlAlq
PwpAv3XBUnPslxmNzGhkRiMzGpnRaHqjUc8820ZqNVtr4K01pm0g2GXz5V27/VHeoRG/XLKqrhfG
cH03NR84O3c+1FV6xQ73unOlVLuX6cearWfnyWV8k2bbfOdNPWFGLrdt5MwVyx5zQu+QxOvn2+uC
3a4sZz65t+/ezpKrtGDx2/BRYe6xVnEsL3OXNuHwHCXo8JwB5Qx3YqDT67RAxxJ99NN1cTu/zIqs
HBXKXexVM2pxMFxkCbQ2uNg93R9Y9nz2iv5LsUnyauv9PE8L+pQ323W5if/PP7178xdKz/dtCvCp
q15Ts9HrWGaA2pXqLPLpG6SrtAyEeT77afd1l7sg7j/94y//9KXjEai11F+ud50cC8f9tsi+r9lp
lmef//r6za5awEB0GLr55cNZi0bo1xphepXlzz/Q9pccP6KQo99hl3EeSDjoeYR9jyPU5mRKEbYn
VhgEPMfQset4zh5k1w139iBU+05nD3JXZ4gG8J3+kZ/Minh9uAvk8nZJe7Pk8XYRiO4TAt/h6RPo
ZTx9Ar1suD4BqHqnPoG3MmOeUCqmDRCuIyrL67haARnwREqw9t3aARFyIuXA55KKsLwb8hxPS6/i
sDq9ajCbA/XuYnHeqoyxGBEyF7C4ZgJcZxAPeWR9z/PqLeFL0OIyWdGPfL8DALJuILo3d3i6coen
H3cGPFa435nCyhwoXDPoI/phN5N61gueL5ZdxmFWb7gv1uv1wXoDfK+fk3zOet5lmV4hLoqUvf88
mS2SVUonX9TA26JM7REXl2VHfZNt6QcN7rJ2AsHTcVAygWIVoUhFKE4RilKEYhShCMUAipcNoHjZ
AIqXDaB42QCKlw3AeNkQjBMNwTjREIwTDcE40RCMEw2hOFEoKCMCfMKQNxaKyIA8sRHgCw5C4MFB
CDw5CIFHByHggw1C4OEBGBUQ2pBHPgS94aENeoFt0Atsg17gpjdcHblSRAsY2NpDmcvT6cDrL29/
aXUealDrfbNlZnx0Kme/M2ZFmuHMGHbyKapME5hySipjffQpSoyJTVqKR9JSmOZhwuoehNWZFjH1
02NME8Cdm6Zm32MaeUvrggKdSWgxWkILBZJJNLcOEp23DlrQ1kEL2jpoCdg6aEFbB61jWwf7bduz
Omzbs+Bte+o4CUwrNK3Q+EnMJrTBNqH92mYnoR85NaP97//Jv6W3x4KCQt+ynNByX1hRr0ibg/sM
F/yzv+kgNRMwa/5PFjeyrDaY3CZx/q9Zc5sJYFP3mE2PTYQ7WBQciD5/Oiu+rouvF9s1ux0JQuKR
4IXtnzwrp+1nyTxPNjELSr/7mWeHURSQF4R2Ae8+nc0yOsnP6ZJwm8+T+5s5vmMRN3KjFywaWZWB
F37fp19Wcqfdoj3VdzwBbckR2JaeOY7LszGIXcYTNkgvG67vAKreqdvgrUy7qNDzMrh/54E5mS0T
ptce5pCmS+19DDi1PxgOHIo0vUs/iDDiCgJnF3LFgbMLBwwFh16gWzQ4d4U6hAbHtAncpJu00tnj
xSJnKcDryixtCfT2V7ByaotsBiR0IsK1E2h3JU9oeHXlcOHh8Dt0ChHvUaUObWGx27s7y9Pi272q
DkacekLN7vqE5+Mvr+MxObtuOINDte9kbu7qdNn5Q9drq/QyyxbF3m8O2VloLx+5FlcnX17HYefy
usHsDNa+i535qyNy74eMFUFDoCaQQE0ggZq0FqgJJFCzwtCBBGoHEqgdSKB2Hjyd7Atd6JeN6G3I
NRBBroGIAO8eEeDpEQHePYJcAxEUvh7ZAPkICl6PoNj1CApdj8AMxx7kmWClzedXpTb4WwcsdcHS
8TIck6MZjluKo1a/7H5HxVEHEkcdQJrdtX/glw70Sxf65cOnR1AytwiSpSMolVtEoPh1AiS0iwgQ
1R5BKfUiG3o6lFAvgnYQRP9/e2ev2jAMReFX6QNk0JV09fMAgS7J6EKgQwweAkmngqe+e62GQGsd
x5KbGrl4FZYso6M/X+k76AKBl+jHMKOGv+kfpUqYqmBqRPRjTqPpUQZNT2TQ9Kh0tmvcD2lOyuZg
l4P6fnxPADcxmAdTUdMOCUkvKRpR7XfjSx4rvi95qlPz/rQ/XjKuy02f9gWa9gWa9sXQtF8C1j9x
4E+Xu0ByF0juORBR+vWwVzzSem2Josejw8t2fDyiH+PR4XSpj3U7NSijWSt/L0LhiEXY9N0JxSjj
AiqsyCBM4vctPAAzi262b90XhSrdrmdFUEBprQkkE/AkwOBJRew3ueBByySM78H3nq8Qk5Crbc7n
uuky9DOS1ErqSchCY4xkuZnECpRW+UDzGa8veLHX0tG1yp30u4zV1x+xcAi+7Ydt+i/2TkeQwt2g
lXM/txPO8XTEYdeyzvvUmoMCnLFep9celMChhKI4k6vMV5kvVeaPhYnOMl9FxoaEjA0JGRsSMjak
ZGNDgvsugvsu+sN9l0EWMgaZaRhkIWOQlUZso0LIRoUyfjdRhnkDZaz2SzqR+49bYgHnT18/PgFg
henMdYYNAA==
"""


if __name__ == "__main__":
    raise SystemExit(main())
