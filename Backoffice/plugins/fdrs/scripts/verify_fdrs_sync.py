#!/usr/bin/env python3
"""
Verify FDRS API values against the Backoffice synced database (template 21).

Fetches KPI × year × country rows from data-api.ifrc.org, looks up the same
data point in form_data, and writes an Excel workbook with:

  - fdrs_value / databank_value
  - status: matched | skipped_intentionally | missing | mismatch

Usage (from Backoffice/):
    python scripts/dev/verify_fdrs_sync.py --years 2024
    python scripts/dev/verify_fdrs_sync.py --years 2023,2024 --problems-only
    python scripts/dev/verify_fdrs_sync.py --kpi KPI_PeopleVol --iso3 KEN
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_scripts = Path(__file__).resolve().parents[3] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from _bootstrap import setup_cli_paths

setup_cli_paths(__file__, plugin_id="fdrs")

if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

from fdrs_data_fetcher import (  # noqa: E402
    DEFAULT_DATA_API_BASE,
    DEFAULT_FDRS_YEARS_END,
    DEFAULT_FDRS_YEARS_START,
    build_fdrs_table,
)
from fdrs_sync_constants import FdrsSyncCancelled  # noqa: E402
from fdrs_sync_verify import (  # noqa: E402
    DATA_POINT_COLUMNS,
    KPI_COVERAGE_COLUMNS,
    STATUS_MATCHED,
    STATUS_MISSING,
    STATUS_MISMATCH,
    STATUS_SKIPPED,
    SUMMARY_COLUMNS,
    DatabankValue,
    apply_mapping_skips,
    attach_classification,
    attach_databank_values,
    counts_by_status,
    group_snapshot_to_points,
    point_to_row,
    summarize_points,
)

logger = logging.getLogger(__name__)

FDRS_TEMPLATE_ID = 21


class FdrsVerifyCancelled(FdrsSyncCancelled):
    """User cancelled FDRS sync verification."""


def _parse_years(raw: Optional[str], *, test: bool = False) -> List[int]:
    if test:
        return [2024]
    if not (raw or "").strip():
        return list(range(DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END + 1))
    years: List[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if "-" in p:
            start_s, end_s = p.split("-", 1)
            years.extend(range(int(start_s.strip()), int(end_s.strip()) + 1))
        else:
            years.append(int(p))
    years = sorted(set(years))
    if not years:
        raise SystemExit("No valid years in --years.")
    return years


def _parse_states(raw: Optional[str]) -> Optional[List[int]]:
    if not (raw or "").strip():
        return None
    out: List[int] = []
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.append(int(p))
    return out or None


def _resolve_api_key(explicit: Optional[str] = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    if key:
        return key
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            cfg = (current_app.config.get("FDRS_DATA_API_KEY") or "").strip()
            if cfg:
                return cfg
    except Exception:
        pass
    raise RuntimeError(
        "FDRS_DATA_API_KEY is required (--api-key, env, or Backoffice/.env)."
    )


def _load_api_key(explicit: Optional[str]) -> str:
    try:
        return _resolve_api_key(explicit)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


def _load_databank_lookups(template_id: int = FDRS_TEMPLATE_ID) -> Tuple[
    Dict[Tuple[str, str], int],
    Dict[str, int],
    set,
    Dict[str, str],
    Dict[str, str],
    Dict[Tuple[str, str, int], DatabankValue],
]:
    """Assignments, KPI→item map, bank codes, names, and form_data keyed by (iso3, year, item_id)."""
    from import_fdrs_form_data import _fetch_databank_tables_local
    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country
    from app.models.forms import FormData

    assignment_rows, form_item_rows, indicator_bank_rows = _fetch_databank_tables_local(template_id)

    assignment_by_key: Dict[Tuple[str, str], int] = {}
    for r in assignment_rows:
        assignment_by_key[(r["period_name"], r["iso3"])] = int(r["assignment_entity_status_id"])

    bank_to_item: Dict[int, int] = {int(r["bank_id"]): int(r["item_id"]) for r in form_item_rows}
    base_to_item_id: Dict[str, int] = {}
    bank_kpi_codes: set = set()
    kpi_names: Dict[str, str] = {}
    for r in indicator_bank_rows:
        code = (r.get("fdrs_kpi_code") or "").strip()
        if not code:
            continue
        bank_kpi_codes.add(code)
        name = (r.get("name") or "").strip()
        if name:
            kpi_names[code] = name
        bank_id = int(r["id"])
        item_id = bank_to_item.get(bank_id)
        if item_id is not None:
            base_to_item_id[code] = item_id

    country_names: Dict[str, str] = {}
    for iso3, name in db.session.query(Country.iso3, Country.name).all():
        iso = (iso3 or "").strip()
        if iso:
            country_names[iso] = (name or "").strip()

    by_iso_year_item: Dict[Tuple[str, str, int], DatabankValue] = {}
    q = (
        db.session.query(
            FormData.value,
            FormData.numeric_value,
            FormData.imputed_value,
            FormData.imputed_numeric_value,
            FormData.data_not_available,
            FormData.not_applicable,
            FormData.disagg_data,
            FormData.disagg_type,
            FormData.form_item_id,
            AssignedForm.period_name,
            Country.iso3,
        )
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
        )
    )
    for row in q.yield_per(2000):
        iso3 = (row.iso3 or "").strip()
        year = (row.period_name or "").strip()
        item_id = int(row.form_item_id) if row.form_item_id is not None else None
        if not iso3 or not year or item_id is None:
            continue
        by_iso_year_item[(iso3, year, item_id)] = DatabankValue(
            value=row.value,
            numeric_value=row.numeric_value,
            imputed_value=row.imputed_value,
            imputed_numeric_value=row.imputed_numeric_value,
            data_not_available=bool(row.data_not_available),
            not_applicable=bool(row.not_applicable),
            disagg_data=row.disagg_data,
            disagg_type=row.disagg_type,
        )

    return assignment_by_key, base_to_item_id, bank_kpi_codes, country_names, kpi_names, by_iso_year_item


def _print_summary(points, output_path: str) -> None:
    counts = counts_by_status(points)
    total = sum(counts.values())
    logger.info("FDRS sync verification: %d data points", total)
    logger.info("  matched:                %s", counts[STATUS_MATCHED])
    logger.info("  skipped_intentionally:  %s", counts[STATUS_SKIPPED])
    logger.info("  missing:                %s", counts[STATUS_MISSING])
    logger.info("  mismatch:               %s", counts[STATUS_MISMATCH])
    logger.info("Wrote %s", output_path)
    problems = [p for p in points if p.status in (STATUS_MISSING, STATUS_MISMATCH)]
    for p in problems[:25]:
        row = point_to_row(p)
        logger.info(
            "  %s %s %s %s fdrs=%r db=%r (%s)",
            p.status,
            p.year,
            p.iso3 or p.don_code,
            p.base_kpi,
            row["fdrs_value"],
            row["databank_value"],
            p.detail,
        )
    if len(problems) > 25:
        logger.info("  ... and %d more problem rows", len(problems) - 25)


def execute_verification(
    *,
    years: List[int],
    output_path: str,
    skip_imputed: bool = False,
    fresh_imputed: bool = False,
    problems_only: bool = False,
    reported_states: Optional[List[int]] = None,
    iso3: Optional[str] = None,
    kpi: Optional[str] = None,
    api_key: Optional[str] = None,
    data_api_base: Optional[str] = None,
    template_id: int = FDRS_TEMPLATE_ID,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Compare FDRS API values to Backoffice form_data. Requires a Flask app context."""
    from flask import current_app, has_app_context
    from import_fdrs_form_data import write_rows_to_excel

    if not has_app_context():
        raise RuntimeError("execute_verification requires a Flask app context")

    def _raise_if_cancelled() -> None:
        if cancel_check and cancel_check():
            raise FdrsVerifyCancelled()

    def _emit(
        message: str,
        percent: Optional[float] = None,
        *,
        stage: str = "verify",
        current: Optional[int] = None,
        total: Optional[int] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        _raise_if_cancelled()
        if not progress_cb:
            return
        payload: Dict[str, Any] = {
            "stage": stage,
            "message": message,
            "percent": percent,
            "current": current,
            "total": total,
        }
        if stats is not None:
            payload["stats"] = stats
        progress_cb(payload)

    def _on_fetch(payload: Dict[str, Any]) -> None:
        _raise_if_cancelled()
        if progress_cb:
            progress_cb(payload)

    resolved_key = _resolve_api_key(api_key)
    base_url = (
        (data_api_base or "").strip().rstrip("/")
        or (current_app.config.get("FDRS_DATA_API_BASE") or "").strip().rstrip("/")
        or DEFAULT_DATA_API_BASE
    )
    cache_dir = os.path.join(current_app.instance_path, "fdrs_imputed_cache")
    year_list = list(years)
    if not year_list:
        year_list = list(range(DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END + 1))

    iso_filter = {s.strip().upper() for s in (iso3 or "").split(",") if s.strip()}
    kpi_filter = {s.strip() for s in (kpi or "").split(",") if s.strip()}

    logger.info("Fetching FDRS data-api (%s, years %s–%s)...", base_url, min(year_list), max(year_list))
    _emit(
        f"Fetching FDRS data-api ({min(year_list)}–{max(year_list)})...",
        2.0,
        stage="fetch_fdrs",
    )
    _fdrs_data, _disagg, _excl, snapshot_rows, _disability = build_fdrs_table(
        base_url=base_url,
        api_key=resolved_key,
        years=year_list,
        imputed_url=None,
        imputed_api_key=resolved_key,
        use_imputed_cache=not fresh_imputed,
        cache_dir=cache_dir,
        reported_import_states=reported_states,
        include_imputed=not skip_imputed,
        progress_cb=_on_fetch,
    )
    logger.info("FDRS snapshot rows: %d", len(snapshot_rows))
    _raise_if_cancelled()
    time.sleep(0.02)

    logger.info("Loading template %s form_data from Backoffice DB...", template_id)
    _emit("Loading Backoffice form_data...", 60.0, stage="load_databank")
    (
        assignment_by_key,
        base_to_item_id,
        bank_kpi_codes,
        country_names,
        kpi_names,
        by_iso_year_item,
    ) = _load_databank_lookups(template_id)
    logger.info(
        "Databank: assignments=%d mapped_kpis=%d form_data_rows=%d",
        len(assignment_by_key),
        len(base_to_item_id),
        len(by_iso_year_item),
    )
    _raise_if_cancelled()
    time.sleep(0.02)

    _emit("Comparing FDRS values to form_data...", 72.0, stage="classify")
    points = group_snapshot_to_points(snapshot_rows)
    if iso_filter:
        points = [p for p in points if (p.iso3 or "").upper() in iso_filter]
    if kpi_filter:
        points = [p for p in points if p.base_kpi in kpi_filter]
    apply_mapping_skips(
        points,
        assignment_by_key=assignment_by_key,
        base_to_item_id=base_to_item_id,
        bank_kpi_codes=bank_kpi_codes,
    )
    _raise_if_cancelled()
    attach_databank_values(
        points,
        by_iso_year_item=by_iso_year_item,
        country_names=country_names,
        kpi_names=kpi_names,
    )
    attach_classification(points)
    _raise_if_cancelled()
    time.sleep(0.02)

    export_points = points
    if problems_only:
        export_points = [p for p in points if p.status in (STATUS_MISSING, STATUS_MISMATCH)]

    counts = counts_by_status(points)
    stats = {
        "total": sum(counts.values()),
        "matched": counts[STATUS_MATCHED],
        "skipped_intentionally": counts[STATUS_SKIPPED],
        "missing": counts[STATUS_MISSING],
        "mismatch": counts[STATUS_MISMATCH],
        "exported": len(export_points),
        "problems_only": bool(problems_only),
        "years": year_list,
    }

    _emit("Writing Excel workbook...", 90.0, stage="write_excel", stats=stats)
    rows = [point_to_row(p) for p in export_points]
    summary_rows, coverage_rows = summarize_points(points)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    write_rows_to_excel(
        rows,
        output_path,
        columns=DATA_POINT_COLUMNS,
        extra_sheets=[
            ("summary", summary_rows, SUMMARY_COLUMNS),
            ("kpi_coverage", coverage_rows, KPI_COVERAGE_COLUMNS),
        ],
        sheet_title="data_points",
    )
    _print_summary(points, output_path)
    _emit("Completed", 100.0, stage="complete", stats=stats)
    stats["output_path"] = output_path
    stats["problem_count"] = counts[STATUS_MISSING] + counts[STATUS_MISMATCH]
    return stats


def run_verification(args: argparse.Namespace) -> int:
    from app import create_app
    from flask import current_app, has_app_context

    years = _parse_years(args.years, test=args.test)
    states = _parse_states(args.fdrs_reported_states)
    app = current_app._get_current_object() if has_app_context() else create_app()
    with app.app_context():
        output_path = args.output or os.path.join(
            current_app.instance_path, "fdrs_sync_verification.xlsx"
        )
        result = execute_verification(
            years=years,
            output_path=output_path,
            skip_imputed=bool(args.skip_imputed),
            fresh_imputed=bool(args.fresh_imputed),
            problems_only=bool(args.problems_only),
            reported_states=states,
            iso3=args.iso3,
            kpi=args.kpi,
            api_key=args.api_key,
            data_api_base=args.data_api_base,
        )
        if result.get("problem_count"):
            return 1
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare FDRS API KPI values to Backoffice form_data (template 21)."
    )
    parser.add_argument(
        "--years",
        help="Comma-separated years or a range (e.g. 2024 or 2020-2024). Default: 2010-2025.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Shortcut: year 2024 only.",
    )
    parser.add_argument(
        "--iso3",
        help="Optional comma-separated ISO3 filter (e.g. KEN,UGA).",
    )
    parser.add_argument(
        "--kpi",
        help="Optional comma-separated BaseKPI filter (e.g. KPI_PeopleVol,KPI_PStaff).",
    )
    parser.add_argument(
        "--api-key",
        help="data-api.ifrc.org key (default: FDRS_DATA_API_KEY).",
    )
    parser.add_argument(
        "--data-api-base",
        help=f"FDRS data API base (default: {DEFAULT_DATA_API_BASE}).",
    )
    parser.add_argument(
        "--fdrs-reported-states",
        help="Comma-separated IFRC State codes treated as importable reported values (same as the importer).",
    )
    parser.add_argument(
        "--skip-imputed",
        action="store_true",
        help="Do not fetch / compare imputed values (faster; reported values only).",
    )
    parser.add_argument(
        "--fresh-imputed",
        action="store_true",
        help="Ignore the imputed-values cache and refetch from the API.",
    )
    parser.add_argument(
        "--problems-only",
        action="store_true",
        help="Excel data_points sheet includes only missing and mismatch rows (summary still covers all).",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Excel path (default: instance/fdrs_sync_verification.xlsx).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug logging.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    return run_verification(args)


if __name__ == "__main__":
    sys.exit(main())
