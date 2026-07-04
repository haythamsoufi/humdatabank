#!/usr/bin/env python3
"""Remove false ``no`` values written by UPR Master sync Yes/No default fill.

Before the fix in ``import_upr_excel_data.py``, the importer defaulted missing core
Yes/No indicators to ``no`` for every T33 assignment in the database, including
rounds absent from UPR Master (e.g. MYR26 when the workbook only has MYR25).

This script deletes ``form_data`` rows where:
  - form item is a core Yes/No indicator on template 33 (published version)
  - scalar value is ``no`` (not data-not-available)
  - assignment round+country was **not** present in the supplied UPR Master file

Usage (from Backoffice/):
    python scripts/cleanup_upr_false_yes_no_defaults.py \\
        --input "instance/upr_import_uploads/....xlsx" --dry-run

    python scripts/cleanup_upr_false_yes_no_defaults.py \\
        --input "UPR Master.xlsx" --force

Optional filters:
    --since 2026-06-28   only rows created on/after this date (ISO)
    --period "Jan-Jun 2026"  limit to assignments with this period name
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from import_upr_excel_data import (  # noqa: E402
    REPORTING_COUNTRY_TEMPLATE_ID,
    UPR_TEMPLATE_PROFILES,
    build_import_context,
    load_upr_data_sheet,
    round_to_period,
    _load_core_yes_no_item_ids,
    _load_other_indicators_section_id,
    _load_yes_no_bank_ids,
)

logger = logging.getLogger(__name__)


def _parse_since(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if len(text) == 10:
        dt = datetime.strptime(text, "%Y-%m-%d")
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _reporting_aes_ids_from_excel_rows(
    rows: List[Dict[str, Any]],
    assignment_map: Dict[Tuple[str, str], int],
) -> Set[int]:
    """T33 assignment ids for reporting round+country pairs present in Excel."""
    t33_sections = UPR_TEMPLATE_PROFILES[REPORTING_COUNTRY_TEMPLATE_ID]["sections"]
    out: Set[int] = set()
    seen: Set[Tuple[str, str]] = set()
    for row in rows:
        rnd = str(row.get("Round") or "").strip().upper()
        if not (rnd.startswith("AR") or rnd.startswith("MYR")):
            continue
        sec = str(row.get("Section") or "").strip()
        if sec not in t33_sections:
            continue
        iso3 = str(row.get("ISO3") or "").strip().upper()
        if not iso3:
            continue
        period = round_to_period(rnd)
        if not period:
            continue
        key = (period, iso3)
        if key in seen:
            continue
        seen.add(key)
        aes_id = assignment_map.get(key)
        if aes_id is not None:
            out.add(int(aes_id))
    return out


def _reporting_period_iso_pairs_from_excel(rows: List[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    """Round+country pairs present in UPR Master reporting sections (no DB lookup)."""
    t33_sections = UPR_TEMPLATE_PROFILES[REPORTING_COUNTRY_TEMPLATE_ID]["sections"]
    out: Set[Tuple[str, str]] = set()
    for row in rows:
        rnd = str(row.get("Round") or "").strip().upper()
        if not (rnd.startswith("AR") or rnd.startswith("MYR")):
            continue
        sec = str(row.get("Section") or "").strip()
        if sec not in t33_sections:
            continue
        iso3 = str(row.get("ISO3") or "").strip().upper()
        if not iso3:
            continue
        period = round_to_period(rnd)
        if period:
            out.add((period, iso3))
    return out


def find_false_yes_no_defaults(
    *,
    input_path: str,
    since: Optional[datetime] = None,
    period_filter: Optional[str] = None,
) -> Dict[str, Any]:
    from app import create_app
    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.forms import FormData
    from sqlalchemy import func

    _, rows = load_upr_data_sheet(input_path)
    allowed_pairs = _reporting_period_iso_pairs_from_excel(rows)
    rounds_in_excel = sorted(
        {str(r.get("Round") or "").strip().upper() for r in rows if r.get("Round")}
    )
    reporting_rounds = sorted(r for r in rounds_in_excel if r.startswith(("AR", "MYR")))

    app = create_app()
    with app.app_context():
        ctx = build_import_context([REPORTING_COUNTRY_TEMPLATE_ID])
        tpl_map = ctx.assignment_by_template.get(REPORTING_COUNTRY_TEMPLATE_ID, {})
        allowed_aes_ids = _reporting_aes_ids_from_excel_rows(rows, tpl_map)
        core_item_ids = list(ctx.core_yes_no_item_ids)
        if not core_item_ids:
            pub_vid = ctx.published_version_ids.get(REPORTING_COUNTRY_TEMPLATE_ID)
            other_section_id = _load_other_indicators_section_id()
            yes_no_bank_ids = _load_yes_no_bank_ids()
            if pub_vid:
                core_item_ids = _load_core_yes_no_item_ids(
                    REPORTING_COUNTRY_TEMPLATE_ID,
                    pub_vid,
                    other_section_id=other_section_id,
                    yes_no_bank_ids=yes_no_bank_ids,
                )

        if not core_item_ids:
            return {
                "allowed_pairs": len(allowed_pairs),
                "allowed_aes_ids": len(allowed_aes_ids),
                "reporting_rounds": reporting_rounds,
                "candidates": [],
                "message": "No core Yes/No form items found on template 33.",
            }

        query = (
            FormData.query.filter(
                FormData.form_item_id.in_(core_item_ids),
                FormData.assignment_entity_status_id.isnot(None),
                func.lower(FormData.value) == "no",
                FormData.data_not_available.isnot(True),
                FormData.disagg_data.is_(None),
            )
        )
        if since is not None:
            query = query.filter(FormData.created_at >= since)

        candidates = query.all()

        to_delete: List[FormData] = []
        for fd in candidates:
            aes_id = int(fd.assignment_entity_status_id)
            if aes_id in allowed_aes_ids:
                continue
            if period_filter:
                aes = db.session.get(AssignmentEntityStatus, aes_id)
                if not aes:
                    continue
                af = db.session.get(AssignedForm, aes.assigned_form_id)
                if not af or af.period_name != period_filter:
                    continue
            to_delete.append(fd)

        by_period: Counter = Counter()
        sample: List[Dict[str, Any]] = []
        for fd in to_delete:
            aes_id = int(fd.assignment_entity_status_id)
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            af = db.session.get(AssignedForm, aes.assigned_form_id) if aes else None
            period_name = af.period_name if af else "?"
            by_period[period_name] += 1
            if len(sample) < 10:
                iso3 = "?"
                if aes and aes.entity_type == "country":
                    from app.models.core import Country

                    country = db.session.get(Country, aes.entity_id)
                    iso3 = country.iso3 if country else "?"
                sample.append(
                    {
                        "form_data_id": fd.id,
                        "aes_id": aes_id,
                        "form_item_id": fd.form_item_id,
                        "period": period_name,
                        "iso3": iso3,
                        "created_at": str(fd.created_at),
                    }
                )

        return {
            "input_path": input_path,
            "reporting_rounds_in_excel": reporting_rounds,
            "allowed_pairs": len(allowed_pairs),
            "allowed_aes_ids": len(allowed_aes_ids),
            "core_yes_no_items": len(core_item_ids),
            "scanned_no_rows": len(candidates),
            "to_delete_count": len(to_delete),
            "to_delete_ids": [int(fd.id) for fd in to_delete],
            "by_period": dict(by_period),
            "sample": sample,
        }


def delete_false_yes_no_defaults(
    *,
    input_path: str,
    since: Optional[datetime] = None,
    period_filter: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    from app import create_app
    from app.extensions import db
    from app.models.forms import FormData

    result = find_false_yes_no_defaults(
        input_path=input_path,
        since=since,
        period_filter=period_filter,
    )
    ids = result.get("to_delete_ids") or []
    result["dry_run"] = dry_run
    result["deleted"] = 0

    if dry_run or not ids:
        return result

    app = create_app()
    with app.app_context():
        deleted = (
            FormData.query.filter(FormData.id.in_(ids)).delete(synchronize_session=False)
        )
        db.session.commit()
        result["deleted"] = deleted
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Delete false UPR Master Yes/No default 'no' form_data rows."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to UPR Master.xlsx (defines which round+country pairs are valid)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would be deleted (default when --force is omitted)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Actually delete matching form_data rows",
    )
    parser.add_argument(
        "--since",
        default="",
        help="Only consider rows created on/after this ISO date/time (e.g. 2026-06-28)",
    )
    parser.add_argument(
        "--period",
        default="",
        help='Only delete for assignments with this period name (e.g. "Jan-Jun 2026")',
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        logger.error("Input file not found: %s", input_path)
        return 1

    if "FLASK_CONFIG" not in os.environ:
        os.environ["FLASK_CONFIG"] = "development"

    since = _parse_since(args.since or None)
    period_filter = args.period.strip() or None
    dry_run = args.dry_run or not args.force

    result = delete_false_yes_no_defaults(
        input_path=str(input_path),
        since=since,
        period_filter=period_filter,
        dry_run=dry_run,
    )

    logger.info("UPR Master: %s", result.get("input_path"))
    logger.info("Reporting rounds in Excel: %s", ", ".join(result.get("reporting_rounds_in_excel") or []))
    logger.info("Allowed round+country pairs: %s", result.get("allowed_pairs"))
    logger.info("Core Yes/No form items (T33): %s", result.get("core_yes_no_items"))
    logger.info("Scalar 'no' rows scanned: %s", result.get("scanned_no_rows"))
    logger.info("False defaults to remove: %s", result.get("to_delete_count"))

    by_period = result.get("by_period") or {}
    if by_period:
        logger.info("By assignment period:")
        for period_name, count in sorted(by_period.items()):
            logger.info("  %s: %s", period_name, count)

    for row in result.get("sample") or []:
        logger.info(
            "  sample id=%s aes=%s item=%s %s %s created=%s",
            row["form_data_id"],
            row["aes_id"],
            row["form_item_id"],
            row["iso3"],
            row["period"],
            row["created_at"],
        )

    if dry_run:
        logger.info("[DRY RUN] No changes made. Re-run with --force to delete.")
    else:
        logger.info("Deleted %s form_data row(s).", result.get("deleted"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
