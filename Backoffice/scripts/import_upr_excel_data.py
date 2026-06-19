#!/usr/bin/env python3
"""
Import Unified Planning & Reporting (UPR) Excel data into form submissions.

Reads the ``UPR Data`` sheet from UPR Master.xlsx and maps rows into form_data for
configured templates (currently planning: template 24, PNS staff: template 22).

Usage:
    python scripts/import_upr_excel_data.py --input path/to/UPR\\ Master.xlsx
    python scripts/import_upr_excel_data.py --input path/to/file.xlsx --rounds P25,P26 --dry-run
    python scripts/import_upr_excel_data.py --input path/to/file.xlsx --templates 24,22
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(script_dir)
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

if "FLASK_CONFIG" not in os.environ:
    os.environ["FLASK_CONFIG"] = "development"

from import_fdrs_form_data import (  # noqa: E402
    COL_ASSIGNMENT,
    COL_DISAGG,
    COL_ITEM,
    COL_NA,
    COL_DATA_NA,
    COL_IMPUTED,
    COL_PREFILLED,
    COL_PUBLIC,
    COL_SUBMITTED,
    COL_VALUE,
    FdrsSyncCancelled,
    upsert_form_data_rows,
    write_rows_to_excel,
)

UPR_DATA_SHEET = "UPR Data"
HEADER_ROW_INDEX = 2  # 0-based row 3 in Excel

# Templates supported by this importer (extensible for reporting templates later).
UPR_TEMPLATE_PROFILES: Dict[int, Dict[str, Any]] = {
    24: {
        "name": "Unified Country Plan",
        "round_prefixes": ("P",),
        "sections": frozenset({"Reach", "NS Data", "Funding", "Comments", "Support"}),
    },
    22: {
        "name": "Annual Planning - International Bilateral Support",
        "round_prefixes": ("P",),
        "sections": frozenset({"Staff"}),
    },
}

STAFF_INDICATOR_COLUMNS: Dict[str, str] = {
    "# of international delegates integrated with the HNS": "intl_delegates_hns",
    "# of international delegates integrated with the IFRC": "intl_delegates_ifrc",
    "# of national staff hired through the HNS (PNS operating under HNS legal umbrella)": "national_staff_hns_hns",
    "# of national staff hired through the HNS (PNS operating under IFRC legal umbrella)": "national_staff_hns_ifrc",
    "# of national staff hired through the IFRC (PNS operating under IFRC legal umbrella)": "national_staff_ifrc_ifrc",
}

STAFF_MATRIX_LABEL = "PNS staff contributions"

FUNDING_MATRIX_BY_YEAR_OFFSET = {
    0: {"hns_ifrc": 967, "pns": 970},
    1: {"hns_ifrc": 968, "pns": 973},
    2: {"hns_ifrc": 974, "pns": 975},
}

ITEM_LONGER_TERM_PROGRAMMES = 954
ITEM_EMERGENCY_APPEALS = 960
ITEM_BILATERAL_SUPPORT = 955
ITEM_COMMENTS = 956
ITEM_FUNDING_REQUIREMENTS_T22 = 1303  # Template 22 – Funding Requirements (rows=country_map)
EMERGENCY_APPEALS_COLUMN = "Total People to be reached"

# Excel Comments_* indicator codes → labels shown in the form textarea.
COMMENT_INDICATOR_LABELS: Dict[str, str] = {
    "comments_fundingrequirements": "Funding requirements",
    "comments_keyfigures": "Key figures",
    "comments_reach": "People to be reached",
    "comments_support": "Bilateral support",
}

AGGREGATE_ATTRIBUTE = frozenset({"Total", "SubTotal"})
AGGREGATE_AREA = frozenset({"Total", "SubTotal", "EAs"})


class UprImportCancelled(FdrsSyncCancelled):
    """Raised when a UPR Excel import is cancelled."""


@dataclass
class UprImportContext:
    """Resolved template items and assignment lookups."""

    template_ids: List[int]
    assignment_by_period_iso: Dict[Tuple[str, str], int] = field(default_factory=dict)
    # Per-template assignment maps (avoids ISO3 key collisions between tpl 24 and tpl 22).
    assignment_by_template: Dict[int, Dict[Tuple[str, str], int]] = field(default_factory=dict)
    items_by_bank_id: Dict[int, Dict[int, int]] = field(default_factory=dict)  # template_id -> bank_id -> item_id
    item_ids_by_label: Dict[int, Dict[str, int]] = field(default_factory=dict)
    staff_matrix_item_id: int = 1367  # Template 22 – PNS staff contributions matrix (fixed)
    ns_name_to_id: Dict[str, int] = field(default_factory=dict)
    # NS name (lower) → home country ISO3 (for PNS funding → template 22 lookup)
    ns_home_country_iso3: Dict[str, str] = field(default_factory=dict)
    # ISO3 → Country.id (used as row key in country_map list_library matrices)
    country_id_by_iso3: Dict[str, int] = field(default_factory=dict)
    emergency_ops_by_iso: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    emergency_ops_ordered_by_iso: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    emergency_matrix_plugin_config: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def round_to_period(round_code: str) -> Optional[str]:
    """Map UPR round code to assignment period name (e.g. P26 -> 2026)."""
    r = (round_code or "").strip().upper()
    if not r:
        return None
    if r.startswith("P") and len(r) >= 3 and r[1:].isdigit():
        return str(2000 + int(r[1:]))
    if r.startswith("AR") and len(r) >= 4 and r[2:].isdigit():
        return str(2000 + int(r[2:]))
    if r.startswith("MYR") and len(r) >= 5 and r[3:].isdigit():
        return str(2000 + int(r[3:]))
    return None


def normalize_indicator_id(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return None


def parse_value_num(raw: Any) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def is_aggregate_row(row: Dict[str, Any]) -> bool:
    """Skip rollup rows (EAs, section totals).

    NS Data and Comments use Area=Total for real data rows, not rollups.
    """
    sec = (row.get("Section") or "").strip()
    area = (row.get("Area") or "").strip()
    if area == "EAs":
        return True
    if area in AGGREGATE_AREA and sec not in ("NS Data", "Comments"):
        return True
    return False


def humanize_comment_label(indicator: str) -> str:
    """Map Excel Comments_* codes to readable section labels."""
    key = (indicator or "").strip().lower()
    if key in COMMENT_INDICATOR_LABELS:
        return COMMENT_INDICATOR_LABELS[key]
    if key.startswith("comments_"):
        slug = key[len("comments_") :].replace("_", " ").strip()
        if slug:
            return slug[0].upper() + slug[1:]
    label = (indicator or "").strip()
    return label or "Comment"


def parse_comment_value(row: Dict[str, Any]) -> Optional[str]:
    """Comment text lives in Value (not ValueNum). UPR Value is the same column duplicated in some exports."""
    for key in ("Value", "UPR Value"):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def summarize_warnings(warnings: List[str]) -> Dict[str, Any]:
    """Deduplicate warnings for display, preserving first-seen order and repeat counts."""
    counts: Dict[str, int] = {}
    order: List[str] = []
    for message in warnings:
        if message not in counts:
            order.append(message)
            counts[message] = 0
        counts[message] += 1
    summarized = [
        f"{message} (×{counts[message]})" if counts[message] > 1 else message
        for message in order
    ]
    return {
        "warnings": summarized,
        "warning_count": len(warnings),
        "warning_unique_count": len(order),
    }


def load_upr_data_sheet(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("Excel support requires openpyxl: pip install openpyxl") from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if UPR_DATA_SHEET not in wb.sheetnames:
        wb.close()
        raise ValueError(f"Sheet {UPR_DATA_SHEET!r} not found in workbook")
    ws = wb[UPR_DATA_SHEET]
    headers: List[str] = []
    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == HEADER_ROW_INDEX:
            headers = [str(h).strip() if h is not None else "" for h in row]
            continue
        if i < HEADER_ROW_INDEX:
            continue
        if not any(c is not None and str(c).strip() for c in row):
            continue
        record = {}
        for j, h in enumerate(headers):
            if not h:
                continue
            val = row[j] if j < len(row) else None
            record[h] = val
        rows.append(record)
    wb.close()
    return headers, rows


def analyze_workbook(path: str) -> Dict[str, Any]:
    """Summarize workbook for the import wizard."""
    headers, rows = load_upr_data_sheet(path)
    rounds: Set[str] = set()
    sections: Set[str] = set()
    years: Set[str] = set()
    iso3s: Set[str] = set()
    by_template_section: Dict[str, int] = defaultdict(int)

    for row in rows:
        rnd = str(row.get("Round") or "").strip()
        sec = str(row.get("Section") or "").strip()
        yr = row.get("Year")
        iso3 = str(row.get("ISO3") or "").strip()
        if rnd:
            rounds.add(rnd)
        if sec:
            sections.add(sec)
        if yr not in (None, ""):
            years.add(str(yr).strip())
        if iso3:
            iso3s.add(iso3)
        for tid, profile in UPR_TEMPLATE_PROFILES.items():
            prefixes = profile.get("round_prefixes") or ()
            if sec in profile.get("sections", frozenset()) and any(rnd.startswith(p) for p in prefixes):
                by_template_section[f"{tid}:{sec}"] += 1

    planning_rounds = sorted(r for r in rounds if r.startswith("P"))
    return {
        "success": True,
        "sheet": UPR_DATA_SHEET,
        "headers": headers,
        "total_rows": len(rows),
        "rounds": sorted(rounds),
        "planning_rounds": planning_rounds,
        "sections": sorted(sections),
        "years": sorted(years),
        "countries": len(iso3s),
        "templates": [
            {"id": tid, "name": prof["name"], "sections": sorted(prof["sections"])}
            for tid, prof in UPR_TEMPLATE_PROFILES.items()
        ],
        "row_counts_by_template_section": dict(by_template_section),
    }


def _build_ns_name_index() -> Dict[str, int]:
    from app.models.organization import NationalSociety

    out: Dict[str, int] = {}
    for ns in NationalSociety.query.filter_by(is_active=True).all():
        name = (ns.name or "").strip()
        if name:
            out[name.lower()] = int(ns.id)
    return out


def _build_ns_home_country_index() -> Tuple[Dict[str, str], Dict[str, int]]:
    """Build two indexes from the NationalSociety table in one pass.

    Returns:
        ns_home_iso3  – NS name (lower) → home country ISO3
        country_id    – ISO3 (upper) → Country.id  (for country_map matrix row keys)
    """
    from app.models.organization import NationalSociety
    from app.models.core import Country
    from app.extensions import db

    rows = (
        db.session.query(NationalSociety.name, Country.iso3, Country.id)
        .join(Country, Country.id == NationalSociety.country_id)
        .filter(NationalSociety.is_active == True, Country.iso3.isnot(None))
        .all()
    )
    ns_home: Dict[str, str] = {}
    cid: Dict[str, int] = {}
    for ns_name, iso3, c_id in rows:
        name_key = (ns_name or "").strip().lower()
        iso3_up = iso3.strip().upper()
        if name_key:
            ns_home[name_key] = iso3_up
        if iso3_up:
            cid[iso3_up] = int(c_id)
    # Also fill country_id for countries that may not have an active NS
    for c in Country.query.filter(Country.iso3.isnot(None)).all():
        iso3_up = c.iso3.strip().upper()
        if iso3_up not in cid:
            cid[iso3_up] = int(c.id)
    return ns_home, cid


def _load_emergency_matrix_plugin_config(template_id: int = 24) -> Dict[str, Any]:
    """Plugin filter config from the Emergency Appeals matrix (item 960)."""
    from app.models.form_items import FormItem

    item = FormItem.query.get(ITEM_EMERGENCY_APPEALS)
    if not item or int(item.template_id or 0) != template_id:
        return {}
    matrix_cfg = (item.config or {}).get("matrix_config") or {}
    plugin_cfg = matrix_cfg.get("plugin_config") or {}
    return plugin_cfg if isinstance(plugin_cfg, dict) else {}


def _emergency_go_config(plugin_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Map matrix plugin_config keys to get_emergency_operations_data config."""
    operation_types = plugin_cfg.get("emops_operation_types") or plugin_cfg.get("operation_types") or ["All"]
    show_closed = plugin_cfg.get("emops_show_closed_operations")
    if show_closed is None:
        show_closed = plugin_cfg.get("show_closed_operations", True)
    cfg: Dict[str, Any] = {
        "operation_types": operation_types,
        "show_closed_operations": bool(show_closed),
    }
    end_date_gt = plugin_cfg.get("emops_end_date_gt") or plugin_cfg.get("end_date_gt")
    if end_date_gt:
        cfg["end_date_gt"] = str(end_date_gt)
    start_date = plugin_cfg.get("emops_start_date") or plugin_cfg.get("start_date")
    if start_date:
        cfg["start_date"] = str(start_date)
    return cfg


def _emergency_op_row_id(op: Dict[str, Any]) -> str:
    """Matrix row id for emergency_operations list_library (name_with_code)."""
    name = (op.get("name") or "").strip()
    code = (op.get("code") or "").strip()
    return f"{name} ({code})" if code else name


def _fetch_emergency_ops_for_country(iso3: str, plugin_cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Fetch GO emergency operations for a country; return ordered list and code index."""
    from app.services.emergency_section_binding import _fetch_ordered_operations

    go_cfg = _emergency_go_config(plugin_cfg)
    ops = _fetch_ordered_operations(iso3.upper(), go_cfg)
    by_code = {(op.get("code") or "").strip().upper(): op for op in ops if (op.get("code") or "").strip()}
    return ops, by_code


def _ensure_emergency_ops(ctx: UprImportContext, iso3: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    key = iso3.upper()
    if key not in ctx.emergency_ops_ordered_by_iso:
        ordered, by_code = _fetch_emergency_ops_for_country(key, ctx.emergency_matrix_plugin_config)
        ctx.emergency_ops_ordered_by_iso[key] = ordered
        ctx.emergency_ops_by_iso[key] = by_code
    return ctx.emergency_ops_ordered_by_iso[key], ctx.emergency_ops_by_iso[key]


def _parse_ea_slot(area: str) -> Optional[int]:
    area = (area or "").strip().upper()
    if area in ("EA1", "EA2", "EA3"):
        return int(area[-1])
    return None


def _resolve_emergency_row_key(
    ctx: UprImportContext,
    *,
    iso3: str,
    area: str,
    ea_code: Any,
) -> Optional[str]:
    """Resolve Emergency Appeals matrix row key from Excel EA slot and/or EA Code."""
    ordered, by_code = _ensure_emergency_ops(ctx, iso3)
    code = (str(ea_code).strip().upper() if ea_code not in (None, "") else "")
    op: Optional[Dict[str, Any]] = None

    if code:
        op = by_code.get(code)
        if op is None:
            ctx.warnings.append(f"Emergency appeal code {code!r} not found in GO API for {iso3}")
            return None
    else:
        slot = _parse_ea_slot(area)
        if slot is None:
            return None
        if slot < 1 or slot > len(ordered):
            ctx.warnings.append(
                f"No EA Code for {area} and only {len(ordered)} appeal(s) in GO API for {iso3} — skipped"
            )
            return None
        op = ordered[slot - 1]
        ctx.warnings.append(
            f"Reach {area} for {iso3} missing EA Code — using GO slot {slot}: {_emergency_op_row_id(op)!r}"
        )

    row_id = _emergency_op_row_id(op)
    if not row_id:
        return None
    return f"{row_id}_{EMERGENCY_APPEALS_COLUMN}"


def _load_assignment_map(template_ids: List[int]) -> Dict[int, Dict[Tuple[str, str], int]]:
    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country

    by_template: Dict[int, Dict[Tuple[str, str], int]] = {tid: {} for tid in template_ids}
    for template_id, period_name, aes_id, iso3_raw in (
        db.session.query(
            AssignedForm.template_id,
            AssignedForm.period_name,
            AssignmentEntityStatus.id,
            Country.iso3,
        )
        .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignedForm.template_id.in_(template_ids),
            AssignmentEntityStatus.entity_type == "country",
        )
        .all()
    ):
        tid = int(template_id)
        pn = (period_name or "").strip()
        iso3 = (iso3_raw or "").strip().upper()
        if pn and iso3 and aes_id is not None and tid in by_template:
            by_template[tid][(pn, iso3)] = int(aes_id)
    return by_template


def _load_items_by_bank(template_ids: List[int]) -> Dict[int, Dict[int, int]]:
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplateVersion

    out: Dict[int, Dict[int, int]] = {tid: {} for tid in template_ids}
    items = (
        FormItem.query.join(FormTemplateVersion, FormItem.version_id == FormTemplateVersion.id)
        .filter(
            FormItem.template_id.in_(template_ids),
            FormItem.archived == False,
            FormTemplateVersion.status == "published",
            FormItem.indicator_bank_id.isnot(None),
        )
        .all()
    )
    for item in items:
        if item.template_id and item.indicator_bank_id:
            out.setdefault(int(item.template_id), {})[int(item.indicator_bank_id)] = int(item.id)
    return out


def _load_items_by_label(template_ids: List[int]) -> Dict[int, Dict[str, int]]:
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplateVersion

    out: Dict[int, Dict[str, int]] = {tid: {} for tid in template_ids}
    items = (
        FormItem.query.join(FormTemplateVersion, FormItem.version_id == FormTemplateVersion.id)
        .filter(
            FormItem.template_id.in_(template_ids),
            FormItem.archived == False,
            FormTemplateVersion.status == "published",
        )
        .all()
    )
    for item in items:
        label = (item.label or "").strip().lower()
        if label and item.template_id:
            out.setdefault(int(item.template_id), {})[label] = int(item.id)
    return out


def build_import_context(template_ids: List[int]) -> UprImportContext:
    ids = [int(t) for t in template_ids]
    ctx = UprImportContext(template_ids=ids)
    ctx.assignment_by_template = _load_assignment_map(ids)
    # Template-24 map kept on ctx for backward-compat with _resolve_aes (Reach, Support, NS Data, Comments)
    ctx.assignment_by_period_iso = ctx.assignment_by_template.get(24, {})
    ctx.items_by_bank_id = _load_items_by_bank(ids)
    ctx.item_ids_by_label = _load_items_by_label(ids)
    ctx.ns_name_to_id = _build_ns_name_index()
    ctx.ns_home_country_iso3, ctx.country_id_by_iso3 = _build_ns_home_country_index()
    if 24 in ids:
        ctx.emergency_matrix_plugin_config = _load_emergency_matrix_plugin_config(24)
    return ctx


def _resolve_aes(ctx: UprImportContext, period: str, iso3: str) -> Optional[int]:
    return ctx.assignment_by_period_iso.get((period, iso3.upper()))


def _resolve_ns_row_id(ctx: UprImportContext, ns_name: str) -> Optional[int]:
    key = (ns_name or "").strip().lower()
    if not key:
        return None
    ns_id = ctx.ns_name_to_id.get(key)
    if ns_id is None:
        ctx.warnings.append(f"National Society not found: {ns_name!r}")
    return ns_id


def _matrix_row(
    *,
    aes_id: int,
    item_id: int,
    cells: Dict[str, Any],
    iso3: str,
    period: str,
    debug_kpi: str,
) -> Dict[str, str]:
    return {
        "_debug_iso3": iso3,
        "_debug_year": period,
        "_debug_kpi_code": debug_kpi,
        COL_ASSIGNMENT: str(aes_id),
        COL_PUBLIC: "",
        COL_ITEM: str(item_id),
        COL_VALUE: "",
        COL_DISAGG: json.dumps(cells),
        COL_DATA_NA: "",
        COL_NA: "",
        COL_PREFILLED: "",
        COL_IMPUTED: "",
        COL_SUBMITTED: "",
    }


def _format_scalar_value(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num.is_integer():
        return str(int(num))
    return str(value)


def _scalar_row(
    *,
    aes_id: int,
    item_id: int,
    value: Any,
    iso3: str,
    period: str,
    debug_kpi: str,
) -> Dict[str, str]:
    if value is None:
        return {}
    return {
        "_debug_iso3": iso3,
        "_debug_year": period,
        "_debug_kpi_code": debug_kpi,
        COL_ASSIGNMENT: str(aes_id),
        COL_PUBLIC: "",
        COL_ITEM: str(item_id),
        COL_VALUE: _format_scalar_value(value),
        COL_DISAGG: "",
        COL_DATA_NA: "",
        COL_NA: "",
        COL_PREFILLED: "",
        COL_IMPUTED: "",
        COL_SUBMITTED: "",
    }


def _year_offset(base_period: str, year_val: Any) -> Optional[int]:
    try:
        base = int(str(base_period).strip())
        year = int(float(str(year_val).strip()))  # float-safe: handles "2026.0" from Excel
    except (ValueError, TypeError):
        return None
    offset = year - base
    if offset not in (0, 1, 2):
        return None
    return offset


def _filter_rows(
    rows: List[Dict[str, Any]],
    *,
    template_ids: List[int],
    rounds: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    allowed_sections: Set[str] = set()
    allowed_prefixes: Set[str] = set()
    for tid in template_ids:
        prof = UPR_TEMPLATE_PROFILES.get(tid)
        if not prof:
            continue
        allowed_sections.update(prof.get("sections", frozenset()))
        allowed_prefixes.update(prof.get("round_prefixes", ()))

    out = []
    for row in rows:
        sec = str(row.get("Section") or "").strip()
        rnd = str(row.get("Round") or "").strip().upper()
        if sec not in allowed_sections:
            continue
        if allowed_prefixes and not any(rnd.startswith(p) for p in allowed_prefixes):
            continue
        if rounds and rnd not in rounds:
            continue
        if is_aggregate_row(row):
            continue
        out.append(row)
    return out


def transform_to_import_rows(
    rows: List[Dict[str, Any]],
    ctx: UprImportContext,
    *,
    template_ids: Optional[List[int]] = None,
    rounds: Optional[Set[str]] = None,
) -> List[Dict[str, str]]:
    """Transform UPR Excel rows into ready-to-import form_data rows."""
    tids = template_ids or ctx.template_ids
    filtered = _filter_rows(rows, template_ids=tids, rounds=rounds)

    matrix_cells: Dict[Tuple[int, int], Dict[str, Any]] = defaultdict(dict)
    comment_parts: Dict[int, List[str]] = defaultdict(list)
    import_rows: List[Dict[str, str]] = []

    # T22 PNS funding staging — collected across all rows then converted to matrix cells.
    # Keyed by (pns_aes_id, host_country_id, area) → (country_val, pns_val).
    # Separate from matrix_cells so we can compute isModified per (aes, country) after all rows.
    pns_t22_staging: Dict[Tuple[int, int, str], Tuple[Optional[float], Optional[float]]] = {}
    pns_t22_has_pns: Set[Tuple[int, int]] = set()  # (pns_aes_id, host_country_id) with any pns_val

    for row in filtered:
        iso3 = str(row.get("ISO3") or "").strip().upper()
        rnd = str(row.get("Round") or "").strip().upper()
        sec = str(row.get("Section") or "").strip()
        period = round_to_period(rnd)
        if not iso3 or not period:
            continue

        value_num = parse_value_num(row.get("ValueNum"))
        indicator = str(row.get("Indicator") or "").strip()
        indicator_id = normalize_indicator_id(row.get("indicatorId"))
        entity = str(row.get("Entity") or "").strip()
        ns_name = str(row.get("NS") or "").strip()
        area = str(row.get("Area") or "").strip()
        year_val = row.get("Year")

        # --- Template 24: NS Data ---
        if 24 in tids and sec == "NS Data":
            if not indicator_id:
                continue
            aes_id = _resolve_aes(ctx, period, iso3)
            item_id = ctx.items_by_bank_id.get(24, {}).get(indicator_id)
            if not aes_id or not item_id:
                continue
            if value_num is None:
                continue
            built = _scalar_row(
                aes_id=aes_id,
                item_id=item_id,
                value=value_num,
                iso3=iso3,
                period=period,
                debug_kpi=indicator or f"bank_{indicator_id}",
            )
            if built:
                import_rows.append(built)
            continue

        # --- Template 24: Comments ---
        if 24 in tids and sec == "Comments":
            aes_id = _resolve_aes(ctx, period, iso3)
            if not aes_id:
                continue
            text_val = parse_comment_value(row)
            if not text_val:
                continue
            key = aes_id
            comment_parts[key].append(f"{humanize_comment_label(indicator)}: {text_val}")
            continue

        # --- Template 24: Support (bilateral ticks) ---
        if 24 in tids and sec == "Support":
            if indicator_id != 3 and indicator.lower() != "bilateral support":
                continue
            if value_num != 1:
                continue
            if not area or area in AGGREGATE_AREA:
                continue
            aes_id = _resolve_aes(ctx, period, iso3)
            ns_id = _resolve_ns_row_id(ctx, ns_name)
            if not aes_id or ns_id is None:
                continue
            cell_key = f"{ns_id}_{area}"
            matrix_cells[(aes_id, ITEM_BILATERAL_SUPPORT)][cell_key] = 1
            continue

        # --- Funding (Template 24: country/HNS/IFRC data; Template 22: PNS-reported data) ---
        if sec == "Funding":
            if indicator_id != 2 and indicator.lower() != "funding requirement":
                continue
            if not area or area in AGGREGATE_AREA:
                continue
            if year_val in (None, ""):
                ctx.warnings.append(f"Funding row missing Year for {iso3} {rnd}")
                continue
            offset = _year_offset(period, year_val)
            if offset is None:
                continue

            ent_upper = entity.upper()

            # ── HNS / IFRC Secretariat → always country-reported → template 24 ──
            if 24 in tids and ent_upper in ("HNS", "IFRC SECRETARIAT"):
                country_val = parse_value_num(row.get("Country Value"))
                if country_val is None:
                    country_val = value_num  # older export fallback
                if not country_val:
                    continue
                aes_id = ctx.assignment_by_template.get(24, {}).get((period, iso3))
                if not aes_id:
                    continue
                item_map = FUNDING_MATRIX_BY_YEAR_OFFSET.get(offset)
                if not item_map:
                    continue
                row_key = "HNS" if ent_upper == "HNS" else "IFRC Secretariat"
                matrix_cells[(aes_id, item_map["hns_ifrc"])][f"{row_key}_{area}"] = country_val
                continue

            # ── PNS entity — Country Value and PNS Value are independent ──
            # A single row can carry both; process each column to its target template.
            if ent_upper != "PNS":
                continue

            country_val = parse_value_num(row.get("Country Value"))
            pns_val = parse_value_num(row.get("PNS Value"))

            # Country Value → template 24 (always, any source that has it)
            if country_val and 24 in tids:
                t24_aes = ctx.assignment_by_template.get(24, {}).get((period, iso3))
                item_map = FUNDING_MATRIX_BY_YEAR_OFFSET.get(offset)
                if t24_aes and item_map:
                    ns_id = _resolve_ns_row_id(ctx, ns_name)
                    if ns_id is not None:
                        matrix_cells[(t24_aes, item_map["pns"])][f"{ns_id}_{area}"] = country_val

            # T22: stage Country Value + PNS Value together; build {original, modified, isModified}
            # cells after the row loop (isModified flag is per host-country, not per cell).
            if 22 in tids and offset == 0 and (country_val or pns_val):
                pns_iso3 = ctx.ns_home_country_iso3.get(ns_name.lower())
                if not pns_iso3:
                    if pns_val:
                        ctx.warnings.append(f"Cannot resolve home country for NS: {ns_name!r}")
                else:
                    pns_aes = ctx.assignment_by_template.get(22, {}).get((period, pns_iso3))
                    if not pns_aes:
                        if pns_val:
                            ctx.warnings.append(
                                f"No template 22 assignment for {pns_iso3} {period} (NS: {ns_name!r})"
                            )
                    else:
                        host_cid = ctx.country_id_by_iso3.get(iso3)
                        if not host_cid:
                            if pns_val:
                                ctx.warnings.append(f"Cannot resolve Country.id for ISO3: {iso3!r}")
                        else:
                            key = (pns_aes, host_cid, area)
                            prev_cv, prev_pv = pns_t22_staging.get(key, (None, None))
                            pns_t22_staging[key] = (
                                country_val if country_val is not None else prev_cv,
                                pns_val if pns_val is not None else prev_pv,
                            )
                            if pns_val:
                                pns_t22_has_pns.add((pns_aes, host_cid))
            continue

        # --- Template 24: Reach ---
        if 24 in tids and sec == "Reach":
            if indicator.lower() != "people to be reached":
                continue
            if not area or area in AGGREGATE_AREA:
                continue
            aes_id = _resolve_aes(ctx, period, iso3)
            if not aes_id or not value_num:
                continue
            if area.startswith("EA") and area != "EAs":
                cell_key = _resolve_emergency_row_key(
                    ctx,
                    iso3=iso3,
                    area=area,
                    ea_code=row.get("EA Code"),
                )
                if not cell_key:
                    continue
                matrix_cells[(aes_id, ITEM_EMERGENCY_APPEALS)][cell_key] = value_num
            elif area.startswith("SP"):
                if year_val in (None, ""):
                    ctx.warnings.append(f"Reach row missing Year for {iso3} {rnd} {area}")
                    continue
                row_year = str(int(float(str(year_val)))) if str(year_val).strip() else ""
                cell_key = f"{row_year}_{area}"
                matrix_cells[(aes_id, ITEM_LONGER_TERM_PROGRAMMES)][cell_key] = value_num
            continue

        # --- Template 22: Staff ---
        if 22 in tids and sec == "Staff":
            col_name = STAFF_INDICATOR_COLUMNS.get(indicator)
            if not col_name:
                continue
            if (entity or "").strip().upper() != "PNS":
                continue
            aes_id = _resolve_aes(ctx, period, iso3)
            ns_id = _resolve_ns_row_id(ctx, ns_name)
            if not aes_id or ns_id is None or not value_num:
                continue
            cell_key = f"{ns_id}_{col_name}"
            matrix_cells[(aes_id, ctx.staff_matrix_item_id)][cell_key] = value_num

    # Convert T22 PNS funding staging into structured matrix cells.
    # Each cell stores {original (country value), modified (PNS value), isModified}.
    # isModified is per-cell: True only when the PNS's value differs from the country's value.
    # If the PNS kept the same value, it is not considered modified.
    # If the PNS didn't report for this host country at all, isModified is always False.
    for (pns_aes, host_cid, area), (cv, pv) in pns_t22_staging.items():
        pns_reported = (pns_aes, host_cid) in pns_t22_has_pns
        orig_num = cv or 0
        mod_num = pv or 0  # treat None as 0 for comparison
        is_modified = pns_reported and (mod_num != orig_num)
        matrix_cells[(pns_aes, ITEM_FUNDING_REQUIREMENTS_T22)][f"{host_cid}_{area}"] = {
            "original": orig_num,
            "modified": pv if pv is not None else "",
            "isModified": is_modified,
        }

    # Build reverse map: aes_id → (iso3, period) covering ALL templates, not just template 24.
    aes_meta: Dict[int, Tuple[str, str]] = {}
    for tpl_map in ctx.assignment_by_template.values():
        for (pn, iso), aid in tpl_map.items():
            aes_meta.setdefault(aid, (iso, pn))

    for aes_id, parts in comment_parts.items():
        if not parts:
            continue
        iso3, period = aes_meta.get(aes_id, ("", ""))
        import_rows.append(
            _scalar_row(
                aes_id=aes_id,
                item_id=ITEM_COMMENTS,
                value="\n".join(p for p in parts if p and str(p).strip()),
                iso3=iso3,
                period=period,
                debug_kpi="comments",
            )
        )

    for (aes_id, item_id), cells in matrix_cells.items():
        if not cells:
            continue
        iso3, period = aes_meta.get(aes_id, ("", ""))
        import_rows.append(
            _matrix_row(
                aes_id=aes_id,
                item_id=item_id,
                cells=cells,
                iso3=iso3,
                period=period,
                debug_kpi=f"matrix_{item_id}",
            )
        )

    return import_rows


def run_upr_import(
    input_path: str,
    *,
    template_ids: Optional[List[int]] = None,
    rounds: Optional[List[str]] = None,
    dry_run: bool = False,
    batch_size: int = 1000,
    preview_excel_path: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    ensure_staff_matrix: bool = True,  # kept for API backward compat, no longer used
) -> Dict[str, Any]:
    """Load UPR Excel, transform, and upsert into form_data."""
    from app.extensions import db
    from contextlib import nullcontext

    tids = template_ids or list(UPR_TEMPLATE_PROFILES.keys())
    for tid in tids:
        if tid not in UPR_TEMPLATE_PROFILES:
            raise ValueError(f"Template {tid} is not configured for UPR Excel import")

    round_set = {r.strip().upper() for r in rounds if r and str(r).strip()} if rounds else None

    def _progress(stage: str, message: str, percent: float, **extra: Any) -> None:
        if not progress_cb:
            return
        payload = {"stage": stage, "message": message, "percent": percent, **extra}
        progress_cb(payload)

    # Reuse an existing Flask app context (e.g. from a web request or the async
    # worker thread) instead of creating a nested one. Only push a fresh context
    # when running from the CLI or any other context-free environment.
    try:
        from flask import current_app as _cur
        _cur._get_current_object()
        _ctx = nullcontext()
    except RuntimeError:
        from app import create_app
        _ctx = create_app().app_context()

    stats: Dict[str, Any] = {"loaded": 0, "skipped": 0, "inserted": 0, "updated": 0, "errors": 0, "warnings": []}

    with _ctx:
        _progress("read", "Reading UPR Data sheet...", 5.0)
        _, rows = load_upr_data_sheet(input_path)
        ctx = build_import_context(tids)

        _progress("transform", "Mapping Excel rows to form items...", 15.0)
        import_rows = transform_to_import_rows(rows, ctx, template_ids=tids, rounds=round_set)
        stats.update(summarize_warnings(ctx.warnings))
        stats["transformed"] = len(import_rows)

        if preview_excel_path and import_rows:
            write_rows_to_excel(import_rows, preview_excel_path)

        valid_item_ids: Optional[Set[int]] = None
        if tids:
            from app.models.form_items import FormItem

            valid_item_ids = set(
                fid for (fid,) in db.session.query(FormItem.id).filter(FormItem.template_id.in_(tids)).all()
            )

        def _emit(payload: Dict[str, Any]) -> None:
            if cancel_check and cancel_check():
                db.session.rollback()
                raise UprImportCancelled()
            if progress_cb:
                progress_cb(payload)

        upsert_stats = upsert_form_data_rows(
            import_rows,
            dry_run=dry_run,
            batch_size=batch_size,
            valid_form_item_ids=valid_item_ids,
            progress_cb=_emit,
            cancel_check=cancel_check,
            progress_start_pct=25.0,
            progress_end_pct=100.0,
            stats=stats,
        )
        upsert_stats.update(summarize_warnings(ctx.warnings))
        upsert_stats["transformed"] = len(import_rows)
        if preview_excel_path:
            upsert_stats["preview_path"] = preview_excel_path
        _progress("complete", "UPR import completed.", 100.0, stats=upsert_stats)
        return upsert_stats


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import UPR Master Excel into form data")
    parser.add_argument("--input", required=True, help="Path to UPR Master.xlsx")
    parser.add_argument(
        "--templates",
        default=",".join(str(t) for t in UPR_TEMPLATE_PROFILES),
        help="Comma-separated template IDs (default: 24,22)",
    )
    parser.add_argument("--rounds", default="", help="Comma-separated round codes (e.g. P25,P26). Default: all planning rounds.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--preview-excel", default="", help="Write ready-to-import preview Excel")
    parser.add_argument("--analyze-only", action="store_true", help="Print workbook summary and exit")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        logger.error("File not found: %s", args.input)
        return 1

    if args.analyze_only:
        summary = analyze_workbook(args.input)
        print(json.dumps(summary, indent=2))
        return 0

    template_ids = [int(x.strip()) for x in args.templates.split(",") if x.strip()]
    rounds = [x.strip() for x in args.rounds.split(",") if x.strip()] or None
    preview = args.preview_excel or None

    try:
        stats = run_upr_import(
            args.input,
            template_ids=template_ids,
            rounds=rounds,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            preview_excel_path=preview,
        )
    except UprImportCancelled:
        logger.warning("Import cancelled")
        return 2

    print(json.dumps(stats, indent=2))
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
