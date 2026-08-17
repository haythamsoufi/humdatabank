#!/usr/bin/env python3
"""
Per-country Unified Country Plan Excel template round-trip for Template 24 (planning).

Uses the structured IFRC planning workbook (named cells + Excel tables) for export/import
from a single country assignment (aes_id). Workbook: app/static/templates/unified_country_plan.xlsx
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(os.path.dirname(script_dir))
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

from import_fdrs_form_data import upsert_form_data_rows  # noqa: E402
from import_upr_excel_data import (  # noqa: E402
    COMMENT_INDICATOR_LABELS,
    EMERGENCY_APPEALS_COLUMN,
    FUNDING_MATRIX_BY_YEAR_OFFSET,
    ITEM_BILATERAL_SUPPORT,
    ITEM_EMERGENCY_APPEALS,
    ITEM_LONGER_TERM_PROGRAMMES,
    PLANNING_EA_FUNDING_AREAS,
    build_import_context,
    humanize_comment_label,
    parse_value_num,
    round_to_period,
    upsert_upr_discussion_comments,
    _ensure_funding_ea_col_header,
    _matrix_row,
    _resolve_emergency_row_key,
    _resolve_ns_row_id,
    _scalar_row,
    _year_offset,
)
from upr_country_reporting_excel_template import (  # noqa: E402
    GENERIC_FORM_EXPORT_SHEETS,
    _load_form_data_map,
    _matrix_cell_scalar,
    _matrix_cells,
    _normalize_matrix_cells,
    _normalize_workbook_header,
    _quiet_openpyxl_io,
    _scalar_value,
    dedupe_upr_import_warnings,
    read_named_cell,
    read_named_table,
    write_named_cell,
    write_table_cell,
)

PLANNING_COUNTRY_TEMPLATE_ID = 24  # Unified Country Plan

PEOPLE_SHEET = "People to be reached"
PEOPLE_TABLE = "Data_People"
SUPPORT_SHEET = "Planned Bilateral Support"
SUPPORT_TABLE = "Data_Support"
FUNDING_SHEET = "Funding requirements"
FUNDING_TABLE = "Data_FR"

SP_AREAS: Tuple[str, ...] = ("SP2", "SP1", "SP3", "SP4", "SP5")
FUNDING_AREAS_PER_YEAR: Tuple[str, ...] = ("EA1", "EA2", "EA3", *SP_AREAS, "EFs")

NS_DATA_BANK_IDS: Dict[str, int] = {
    "volunteers": 724,
    "staff": 727,
    "local_units": 723,
    "branches": 1117,
}

NS_DATA_NAMED_CELLS: Dict[str, str] = {
    "volunteers": "Data_vol",
    "staff": "Data_staff",
    "local_units": "Data_units",
    "branches": "Data_branches",
}

UNIFIED_COUNTRY_PLAN_REQUIRED_NAMED_RANGES: Tuple[str, ...] = (
    "Version",
    "Data_Country",
    *NS_DATA_NAMED_CELLS.values(),
)

UNIFIED_COUNTRY_PLAN_REQUIRED_TABLES: Tuple[Tuple[str, str], ...] = (
    (PEOPLE_SHEET, PEOPLE_TABLE),
    (SUPPORT_SHEET, SUPPORT_TABLE),
    (FUNDING_SHEET, FUNDING_TABLE),
)

UNIFIED_COUNTRY_PLAN_COMPATIBLE_ROUND_PREFIXES: Tuple[str, ...] = ("P",)

COMMENT_NAMED_TO_SLUG: Dict[str, str] = {
    "Comments_keyfigures": "comments_keyfigures",
    "Comments_reach": "comments_reach",
    "Comments_support": "comments_support",
    "Comments_fundingrequirements": "comments_fundingrequirements",
}

EA_SLOT_NAMED_CELLS: Tuple[Tuple[str, str, str, str], ...] = (
    ("Reach_EA1", "Data_MDR1", "Data_EA1", "EA1"),
    ("Reach_EA2", "Data_MDR2", "Data_EA2", "EA2"),
    ("Reach_EA3", "Data_MDR3", "Data_EA3", "EA3"),
)

_FUNDING_HEADER_RE = re.compile(r"^(.+)_(\d{4})$")


def _require_openpyxl():
    import openpyxl  # noqa: F401


def period_to_workbook_version(period_name: str) -> str:
    """Map assignment period name to planning workbook Version cell (e.g. 2027 -> P27.V1.0)."""
    period = (period_name or "").strip()
    match = re.match(r"^(\d{4})$", period)
    if match:
        year = int(match.group(1))
        return f"P{year - 2000}.V1.0"
    return "P27.V1.0"


def planning_base_year(period_name: str) -> Optional[int]:
    period = (period_name or "").strip()
    match = re.match(r"^(\d{4})$", period)
    if match:
        return int(match.group(1))
    return None


def planning_year_triplet(period_name: str) -> Tuple[int, int, int]:
    base = planning_base_year(period_name) or 2027
    return base, base + 1, base + 2


def funding_column_header(area: str, year: int) -> str:
    return f"{area}_{year}"


def parse_funding_column_header(header: str) -> Optional[Tuple[str, int]]:
    text = str(header or "").strip()
    if not text or text.upper() == "NS":
        return None
    match = _FUNDING_HEADER_RE.match(text)
    if not match:
        return None
    area, year_text = match.group(1), match.group(2)
    return area, int(year_text)


def parse_version(wb) -> Tuple[str, str]:
    raw = read_named_cell(wb, "Version")
    text = str(raw or "").strip()
    if not text:
        return "", ""
    round_code = text.split(".")[0].upper()
    period = round_to_period(round_code) or ""
    return round_code, period


def _workbook_table_exists(wb, sheet_name: str, table_name: str) -> bool:
    if sheet_name not in wb.sheetnames:
        return False
    return table_name in wb[sheet_name].tables


def _rewrite_table_header(wb, sheet_name: str, table_name: str, header: str, new_value: str) -> None:
    from openpyxl.utils import range_boundaries

    ws = wb[sheet_name]
    tbl = ws.tables[table_name]
    min_col, min_row, max_col, _max_row = range_boundaries(tbl.ref)
    target = _normalize_workbook_header(header)
    for col in range(min_col, max_col + 1):
        raw = ws.cell(min_row, col).value
        h = str(raw).strip() if raw is not None else ""
        if h == header or _normalize_workbook_header(h) == target:
            ws.cell(min_row, col).value = new_value
            # Keep Excel table metadata in sync with the header row (prevents table*.xml repair errors).
            col_idx = col - min_col
            if tbl.tableColumns and 0 <= col_idx < len(tbl.tableColumns):
                tbl.tableColumns[col_idx].name = new_value
            return


def rewrite_planning_year_headers(wb, period_name: str) -> None:
    """Align Data_People year rows and Data_FR column headers with the assignment period."""
    y0, y1, y2 = planning_year_triplet(period_name)

    _, people_rows = read_named_table(wb, PEOPLE_SHEET, PEOPLE_TABLE)
    for offset, year in enumerate((y0, y1, y2)):
        if offset < len(people_rows):
            write_table_cell(wb, PEOPLE_SHEET, PEOPLE_TABLE, offset, "Year", year)

    headers, _ = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
    funding_headers = [h for h in headers if parse_funding_column_header(h)]
    # The workbook uses 9 EA+SP columns for year 1 but only 6 SP columns for years 2–3,
    # so idx // len(FUNDING_AREAS_PER_YEAR) must not be used to infer the target year.
    template_years = sorted({parse_funding_column_header(h)[1] for h in funding_headers})
    target_years = (y0, y1, y2)
    year_map = {
        template_years[i]: target_years[i]
        for i in range(min(len(template_years), len(target_years)))
    }
    for header in funding_headers:
        parsed = parse_funding_column_header(header)
        if not parsed:
            continue
        area, old_year = parsed
        new_year = year_map.get(old_year, old_year)
        new_header = funding_column_header(area, new_year)
        if new_header != header:
            _rewrite_table_header(wb, FUNDING_SHEET, FUNDING_TABLE, header, new_header)


def _load_assignment_meta(aes_id: int):
    from app.models.assignments import AssignmentEntityStatus
    from app.utils.api_serialization import _country_for_aes

    aes = AssignmentEntityStatus.query.get(aes_id)
    if not aes:
        raise ValueError(f"Assignment {aes_id} not found")
    country = _country_for_aes(aes)
    country_name = (country.name if country else "") or ""
    iso3 = (country.iso3 if country else "") or ""
    period = (aes.assigned_form.period_name if aes.assigned_form else "") or ""
    template_id = int(getattr(aes.assigned_form, "template_id", 0) or 0)
    if template_id != PLANNING_COUNTRY_TEMPLATE_ID:
        raise ValueError(
            f"Assignment {aes_id} is template {template_id}, not T{PLANNING_COUNTRY_TEMPLATE_ID}"
        )
    return aes, country_name.strip(), iso3.strip().upper(), period.strip()


def validate_unified_country_plan_import_file(
    wb,
    *,
    expected_country: str = "",
    expected_period: str = "",
) -> Dict[str, Any]:
    """Validate workbook structure and assignment match before import."""
    errors: List[str] = []
    warnings: List[str] = []
    preview: Dict[str, Any] = {
        "country": None,
        "period": None,
        "round_code": None,
    }

    generic_hits = [name for name in GENERIC_FORM_EXPORT_SHEETS if name in wb.sheetnames]
    if generic_hits:
        errors.append(
            "This file looks like a generic form Excel export (sheets: "
            f"{', '.join(generic_hits)}), not a Unified Country Plan workbook. "
            "Use Export Unified Country Plan from this assignment."
        )

    for named_range in UNIFIED_COUNTRY_PLAN_REQUIRED_NAMED_RANGES:
        if named_range not in wb.defined_names:
            errors.append(
                f"Missing named range {named_range!r}. "
                "Download a current Unified Country Plan template from this assignment."
            )

    for sheet_name, table_name in UNIFIED_COUNTRY_PLAN_REQUIRED_TABLES:
        if not _workbook_table_exists(wb, sheet_name, table_name):
            if sheet_name not in wb.sheetnames:
                errors.append(f"Missing sheet {sheet_name!r}.")
            else:
                errors.append(
                    f"Missing table {table_name!r} on sheet {sheet_name!r}. "
                    "Older IFRC templates are not compatible with this import."
                )

    round_code, period_name = parse_version(wb)
    preview["round_code"] = round_code or None
    preview["period"] = period_name or None
    country_name = str(read_named_cell(wb, "Data_Country") or "").strip()
    preview["country"] = country_name or None

    if not round_code:
        errors.append(
            "Missing or unreadable Version cell. "
            "Use a Unified Country Plan template exported from this assignment."
        )
    elif not any(round_code.startswith(prefix) for prefix in UNIFIED_COUNTRY_PLAN_COMPATIBLE_ROUND_PREFIXES):
        errors.append(
            f"Unsupported workbook version {round_code!r}. "
            f"Expected a planning round code starting with "
            f"{' or '.join(UNIFIED_COUNTRY_PLAN_COMPATIBLE_ROUND_PREFIXES)}."
        )

    if expected_period and period_name and period_name != expected_period:
        warnings.append(
            f"Workbook period {period_name!r} differs from this assignment ({expected_period!r}). "
            "Values will be loaded into the current assignment."
        )

    if expected_country and country_name and country_name.lower() != expected_country.lower():
        errors.append(
            f"Workbook country {country_name!r} does not match this assignment ({expected_country!r})."
        )

    return {
        "valid": not errors,
        "message": errors[0] if errors else "Workbook is valid.",
        "errors": errors,
        "warnings": warnings,
        "preview": preview,
    }


def _cell_is_tick(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) == 1.0
    text = str(value).strip().lower()
    return text in ("1", "x", "yes", "true")


def _parse_funding_row_entity(ns_label: Any) -> Tuple[str, str]:
    text = str(ns_label or "").replace("\r\n", "\n").strip()
    lower = text.lower()
    if lower == "ifrc secretariat":
        return "ifrc", "IFRC Secretariat"
    if "host national society" in lower:
        return "hns", "HNS"
    if "\n" in text:
        text = text.split("\n", 1)[-1].strip()
    return "pns", text


def _workbook_reach_ea_codes(wb, *, iso3: str, rnd: str) -> Dict[Tuple[str, str, str], str]:
    codes: Dict[Tuple[str, str, str], str] = {}
    for _reach, mdr_name, _ea_name, area in EA_SLOT_NAMED_CELLS:
        code = str(read_named_cell(wb, mdr_name) or "").strip().upper()
        if code:
            codes[(iso3, rnd, area)] = code
    return codes


def _import_reach_matrices(
    wb,
    ctx,
    *,
    aes_id: int,
    iso3: str,
    period: str,
    rnd: str,
    warnings: List[str],
) -> Dict[int, Dict[str, Any]]:
    matrices: Dict[int, Dict[str, Any]] = defaultdict(dict)
    reach_ea_codes = _workbook_reach_ea_codes(wb, iso3=iso3, rnd=rnd)

    _, people_rows = read_named_table(wb, PEOPLE_SHEET, PEOPLE_TABLE)
    for row in people_rows:
        year_val = row.get("Year")
        if year_val in (None, ""):
            continue
        try:
            row_year = str(int(float(str(year_val))))
        except (ValueError, TypeError):
            continue
        if _year_offset(period, row_year) is None:
            warnings.append(f"Reach row year {row_year!r} is outside the planning window for {period}.")
            continue
        for area in SP_AREAS:
            amount = parse_value_num(row.get(area))
            if amount is None:
                continue
            matrices[ITEM_LONGER_TERM_PROGRAMMES][f"{row_year}_{area}"] = amount

    for reach_name, mdr_name, _ea_name, area in EA_SLOT_NAMED_CELLS:
        amount = parse_value_num(read_named_cell(wb, reach_name))
        if amount is None:
            continue
        ea_code = read_named_cell(wb, mdr_name)
        cell_key = _resolve_emergency_row_key(ctx, iso3=iso3, area=area, ea_code=ea_code)
        if not cell_key:
            warnings.append(f"Could not resolve emergency appeal row for {area} on Reach sheet.")
            continue
        matrices[ITEM_EMERGENCY_APPEALS][cell_key] = amount
        code_text = str(ea_code or "").strip().upper()
        if code_text:
            reach_ea_codes[(iso3, rnd, area)] = code_text

    return matrices


def _import_support_matrix(wb, ctx, *, aes_id: int, warnings: List[str]) -> Dict[str, Any]:
    cells: Dict[str, Any] = {}
    _, rows = read_named_table(wb, SUPPORT_SHEET, SUPPORT_TABLE)
    for row in rows:
        ns_name = str(row.get("NS") or "").strip()
        if not ns_name:
            continue
        ns_id = _resolve_ns_row_id(ctx, ns_name)
        if ns_id is None:
            continue
        for area in (*SP_AREAS, "EFs"):
            if _cell_is_tick(row.get(area)):
                cells[f"{ns_id}_{area}"] = 1
    return cells


def _import_funding_matrices(
    wb,
    ctx,
    *,
    aes_id: int,
    iso3: str,
    period: str,
    rnd: str,
    warnings: List[str],
) -> Dict[int, Dict[str, Any]]:
    matrices: Dict[int, Dict[str, Any]] = defaultdict(dict)
    reach_ea_codes = _workbook_reach_ea_codes(wb, iso3=iso3, rnd=rnd)
    headers, rows = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
    funding_headers = [h for h in headers if parse_funding_column_header(h)]

    matrix_cells: Dict[Tuple[int, int], Dict[str, Any]] = defaultdict(dict)

    for row in rows:
        entity, ns_name = _parse_funding_row_entity(row.get("NS"))
        for header in funding_headers:
            parsed = parse_funding_column_header(header)
            if not parsed:
                continue
            area, year = parsed
            offset = _year_offset(period, year)
            if offset is None:
                continue
            amount = parse_value_num(row.get(header))
            if amount is None:
                continue
            item_id = FUNDING_MATRIX_BY_YEAR_OFFSET.get(offset)
            if not item_id:
                continue
            if area in PLANNING_EA_FUNDING_AREAS:
                if not _ensure_funding_ea_col_header(
                    matrix_cells,
                    ctx,
                    aes_id=aes_id,
                    funding_item_id=item_id,
                    iso3=iso3,
                    rnd=rnd,
                    area=area,
                    ea_code_raw=reach_ea_codes.get((iso3, rnd, area)),
                    reach_ea_codes=reach_ea_codes,
                ):
                    warnings.append(f"Could not resolve EA column header for {area} ({year}).")
                    continue
            if entity == "hns":
                row_key = "HNS"
            elif entity == "ifrc":
                row_key = "IFRC Secretariat"
            else:
                ns_id = _resolve_ns_row_id(ctx, ns_name)
                if ns_id is None:
                    continue
                row_key = str(ns_id)
            matrix_cells[(aes_id, item_id)][f"{row_key}_{area}"] = amount

    for (aid, item_id), cells in matrix_cells.items():
        if aid == aes_id and cells:
            matrices[item_id].update(cells)
    return matrices


def _import_comments_from_workbook(wb, aes_id: int) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for named_cell, slug in COMMENT_NAMED_TO_SLUG.items():
        if named_cell not in wb.defined_names:
            continue
        text = str(read_named_cell(wb, named_cell) or "").strip()
        if not text:
            continue
        entries.append(
            {
                "aes_id": aes_id,
                "body": f"{humanize_comment_label(slug)}: {text}",
                "source": "upr_excel_import",
            }
        )
    return entries


def _ns_fields_from_workbook(wb, ctx) -> Dict[str, Dict[str, Any]]:
    fields: Dict[str, Dict[str, Any]] = {}
    bank_map = ctx.items_by_bank_id.get(PLANNING_COUNTRY_TEMPLATE_ID, {})
    for _key, bank_id in NS_DATA_BANK_IDS.items():
        item_id = bank_map.get(bank_id)
        if not item_id:
            continue
        cell_name = NS_DATA_NAMED_CELLS[_key]
        raw = read_named_cell(wb, cell_name)
        if raw is None or str(raw).strip() == "":
            continue
        fields[str(item_id)] = {"value": raw}
    return fields


def _workbook_matrices_from_payload(
    wb,
    ctx,
    *,
    aes_id: int,
    iso3: str,
    period: str,
    warnings: List[str],
) -> Dict[int, Dict[str, Any]]:
    rnd, _ = parse_version(wb)
    reach = _import_reach_matrices(
        wb, ctx, aes_id=aes_id, iso3=iso3, period=period, rnd=rnd, warnings=warnings
    )
    support = _import_support_matrix(wb, ctx, aes_id=aes_id, warnings=warnings)
    funding = _import_funding_matrices(
        wb, ctx, aes_id=aes_id, iso3=iso3, period=period, rnd=rnd, warnings=warnings
    )
    matrices: Dict[int, Dict[str, Any]] = {}
    for item_id, cells in reach.items():
        if cells:
            matrices[item_id] = dict(cells)
    if support:
        matrices[ITEM_BILATERAL_SUPPORT] = support
    for item_id, cells in funding.items():
        if cells:
            matrices[item_id] = dict(cells)
    return matrices


def build_unified_country_plan_client_payload(
    aes_id: int,
    wb,
    ctx,
    *,
    iso3: str,
    period: str,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    warn = warnings if warnings is not None else []
    matrices = _workbook_matrices_from_payload(
        wb, ctx, aes_id=aes_id, iso3=iso3, period=period, warnings=warn
    )
    return {
        "fields": _ns_fields_from_workbook(wb, ctx),
        "matrices": {str(k): v for k, v in matrices.items()},
        "dynamic_indicators": [],
        "repeat_slots": [],
        "meta": {"iso3": iso3, "period": period},
    }


def _parse_emergency_row_id(row_id: str) -> Tuple[str, str]:
    text = (row_id or "").strip()
    if text.endswith(")"):
        open_idx = text.rfind("(")
        if open_idx > 0:
            return text[:open_idx].strip(), text[open_idx + 1 : -1].strip()
    return text, ""


def _export_reach_to_workbook(wb, entry_954, entry_960) -> None:
    cells_954 = _normalize_matrix_cells(_matrix_cells(entry_954))
    _, people_rows = read_named_table(wb, PEOPLE_SHEET, PEOPLE_TABLE)
    for offset, row in enumerate(people_rows):
        year_val = row.get("Year")
        if year_val in (None, ""):
            continue
        try:
            row_year = str(int(float(str(year_val))))
        except (ValueError, TypeError):
            continue
        for area in SP_AREAS:
            val = _matrix_cell_scalar(cells_954.get(f"{row_year}_{area}"))
            if val is not None:
                write_table_cell(wb, PEOPLE_SHEET, PEOPLE_TABLE, offset, area, val)

    cells_960 = _normalize_matrix_cells(_matrix_cells(entry_960))
    suffix = f"_{EMERGENCY_APPEALS_COLUMN}"
    ea_entries: List[Tuple[str, Any]] = []
    for key, raw in cells_960.items():
        if not str(key).endswith(suffix):
            continue
        row_id = str(key)[: -len(suffix)]
        val = _matrix_cell_scalar(raw)
        if val is None:
            continue
        ea_entries.append((row_id, val))
    ea_entries.sort(key=lambda item: item[0])
    for idx, (reach_name, mdr_name, ea_name, _area) in enumerate(EA_SLOT_NAMED_CELLS):
        if idx >= len(ea_entries):
            break
        row_id, val = ea_entries[idx]
        name, code = _parse_emergency_row_id(row_id)
        write_named_cell(wb, reach_name, val)
        if code:
            write_named_cell(wb, mdr_name, code)
        if name:
            write_named_cell(wb, ea_name, name)


def _export_support_to_workbook(wb, entry_955, ctx) -> None:
    cells = _normalize_matrix_cells(_matrix_cells(entry_955))
    if not cells:
        return
    _, rows = read_named_table(wb, SUPPORT_SHEET, SUPPORT_TABLE)
    for offset, row in enumerate(rows):
        ns_name = str(row.get("NS") or "").strip()
        if not ns_name:
            continue
        ns_id = ctx.ns_name_to_id.get(ns_name.lower())
        if ns_id is None:
            continue
        for area in (*SP_AREAS, "EFs"):
            if _cell_is_tick(cells.get(f"{ns_id}_{area}")):
                write_table_cell(wb, SUPPORT_SHEET, SUPPORT_TABLE, offset, area, 1)


def _export_funding_to_workbook(wb, entries, period: str, ctx) -> None:
    headers, rows = read_named_table(wb, FUNDING_SHEET, FUNDING_TABLE)
    funding_headers = [h for h in headers if parse_funding_column_header(h)]
    for offset, item_id in FUNDING_MATRIX_BY_YEAR_OFFSET.items():
        cells = _normalize_matrix_cells(_matrix_cells(entries.get(item_id)))
        if not cells:
            continue
        for row_offset, row in enumerate(rows):
            entity, ns_name = _parse_funding_row_entity(row.get("NS"))
            for header in funding_headers:
                parsed = parse_funding_column_header(header)
                if not parsed:
                    continue
                area, year = parsed
                if _year_offset(period, year) != offset:
                    continue
                if entity == "hns":
                    row_key = "HNS"
                elif entity == "ifrc":
                    row_key = "IFRC Secretariat"
                else:
                    ns_id = _resolve_ns_row_id(ctx, ns_name)
                    if ns_id is None:
                        continue
                    row_key = str(ns_id)
                val = _matrix_cell_scalar(cells.get(f"{row_key}_{area}"))
                if val is not None:
                    write_table_cell(wb, FUNDING_SHEET, FUNDING_TABLE, row_offset, header, val)


def _load_discussion_comments_for_export(aes_id: int) -> Dict[str, str]:
    from app.models import SubmissionDiscussionComment

    slug_by_label = {humanize_comment_label(slug): slug for slug in COMMENT_INDICATOR_LABELS}
    out: Dict[str, str] = {}
    rows = (
        SubmissionDiscussionComment.query.filter_by(assignment_entity_status_id=int(aes_id))
        .order_by(SubmissionDiscussionComment.created_at.asc())
        .all()
    )
    for row in rows:
        body = (row.body or "").strip()
        if not body:
            continue
        for label, slug in slug_by_label.items():
            prefix = f"{label}:"
            if body.startswith(prefix):
                out[slug] = body[len(prefix) :].strip()
                break
    return out


def _export_comments_to_workbook(wb, aes_id: int) -> None:
    by_slug = _load_discussion_comments_for_export(aes_id)
    for named_cell, slug in COMMENT_NAMED_TO_SLUG.items():
        text = by_slug.get(slug)
        if text and named_cell in wb.defined_names:
            write_named_cell(wb, named_cell, text)


def build_unified_country_plan_export(aes_id: int, template_path: str, output_path: str) -> Dict[str, Any]:
    """Fill Unified Country Plan template with assignment data and save to output_path."""
    _require_openpyxl()
    import openpyxl

    _aes, country_name, iso3, period = _load_assignment_meta(aes_id)
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Unified Country Plan template not found: {template_path}")

    with _quiet_openpyxl_io():
        wb = openpyxl.load_workbook(template_path)
    rewrite_planning_year_headers(wb, period)
    write_named_cell(wb, "Version", period_to_workbook_version(period))
    write_named_cell(wb, "Data_Country", country_name)

    ctx = build_import_context([PLANNING_COUNTRY_TEMPLATE_ID])
    entries = _load_form_data_map(aes_id)
    for key, bank_id in NS_DATA_BANK_IDS.items():
        item_id = ctx.items_by_bank_id.get(PLANNING_COUNTRY_TEMPLATE_ID, {}).get(bank_id)
        if not item_id:
            continue
        value = _scalar_value(entries.get(item_id))
        if value is not None:
            write_named_cell(wb, NS_DATA_NAMED_CELLS[key], value)

    _export_reach_to_workbook(
        wb,
        entries.get(ITEM_LONGER_TERM_PROGRAMMES),
        entries.get(ITEM_EMERGENCY_APPEALS),
    )
    _export_support_to_workbook(wb, entries.get(ITEM_BILATERAL_SUPPORT), ctx)
    _export_funding_to_workbook(wb, entries, period, ctx)
    _export_comments_to_workbook(wb, aes_id)

    with _quiet_openpyxl_io():
        wb.save(output_path)
    wb.close()

    safe_country = re.sub(r"[^\w\-]+", "_", country_name or iso3 or "country").strip("_") or "country"
    safe_period = re.sub(r"[^\w\-]+", "_", period or "period").strip("_") or "period"
    filename = f"Unified_Country_Plan_{safe_country}_{safe_period}.xlsx"
    return {"filename": filename, "aes_id": aes_id}


def _payload_to_import_rows(
    aes_id: int,
    payload: Dict[str, Any],
    *,
    iso3: str,
    period: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item_id, field_data in (payload.get("fields") or {}).items():
        built = _scalar_row(
            aes_id=aes_id,
            item_id=int(item_id),
            value=field_data.get("value"),
            iso3=iso3,
            period=period,
            debug_kpi=f"field_{item_id}",
        )
        if built:
            rows.append(built)
    for item_id, cells in (payload.get("matrices") or {}).items():
        if not cells:
            continue
        rows.append(
            _matrix_row(
                aes_id=aes_id,
                item_id=int(item_id),
                cells=cells,
                iso3=iso3,
                period=period,
                debug_kpi=f"matrix_{item_id}",
            )
        )
    return rows


def run_unified_country_plan_import(
    aes_id: int,
    workbook_path: str,
    *,
    dry_run: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    """Import a filled Unified Country Plan workbook into the assignment."""
    _require_openpyxl()
    import openpyxl

    from app.extensions import db
    from app.models.form_items import FormItem

    _aes, country_name, iso3, period = _load_assignment_meta(aes_id)
    ctx = build_import_context([PLANNING_COUNTRY_TEMPLATE_ID])

    with _quiet_openpyxl_io():
        wb = openpyxl.load_workbook(workbook_path, data_only=True)
    try:
        validation = validate_unified_country_plan_import_file(
            wb,
            expected_country=country_name,
            expected_period=period,
        )
        if not validation.get("valid"):
            return {
                "success": False,
                "errors": len(validation.get("errors") or []),
                "message": validation.get("message") or "Validation failed.",
                "warnings": validation.get("warnings") or [],
            }

        warnings: List[str] = list(validation.get("warnings") or [])
        payload = build_unified_country_plan_client_payload(
            aes_id,
            wb,
            ctx,
            iso3=iso3,
            period=period,
            warnings=warnings,
        )
        warnings.extend(ctx.warnings)
        warnings = dedupe_upr_import_warnings(warnings)
        discussion_entries = _import_comments_from_workbook(wb, aes_id)

        field_count = len(payload.get("fields") or {})
        matrix_count = sum(len(v or {}) for v in (payload.get("matrices") or {}).values())
        updated_count = field_count + matrix_count

        if not persist:
            return {
                "success": True,
                "stage_only": True,
                "payload": payload,
                "warnings": warnings,
                "updated_count": updated_count,
            }

        import_rows = _payload_to_import_rows(aes_id, payload, iso3=iso3, period=period)
        valid_item_ids = {
            int(fid)
            for (fid,) in db.session.query(FormItem.id)
            .filter(FormItem.template_id == PLANNING_COUNTRY_TEMPLATE_ID)
            .all()
        }
        stats = upsert_form_data_rows(
            import_rows,
            dry_run=dry_run,
            valid_form_item_ids=valid_item_ids,
        )
        discussion_stats = upsert_upr_discussion_comments(discussion_entries, dry_run=dry_run)
        stats.update(discussion_stats)
        stats["success"] = True
        stats["warnings"] = warnings
        stats["updated_count"] = int(stats.get("inserted", 0) or 0) + int(stats.get("updated", 0) or 0)
        stats["updated_count"] += int(discussion_stats.get("discussion_inserted", 0) or 0)
        return stats
    finally:
        wb.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Country Plan Excel round-trip (T24)")
    parser.add_argument("--aes-id", type=int, required=True)
    parser.add_argument(
        "--template",
        default=os.path.join(backoffice_dir, "app", "static", "templates", "unified_country_plan.xlsx"),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build_unified_country_plan_export(args.aes_id, args.template, args.output), indent=2))
