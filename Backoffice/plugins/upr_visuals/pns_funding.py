"""PNS T22/T23 cross-submission funding lookups."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.form_items import FormItem
from app.models.forms import FormData
from app.models.organization import NationalSociety
from plugins.upr_visuals.catalog import (
    PNS_PLAN_ITEM_FALLBACKS,
    PNS_PLAN_LABEL_NEEDLES,
    PNS_PLAN_TEMPLATE_ID,
    PNS_REPORT_LABEL_NEEDLES,
    PNS_REPORT_TEMPLATE_ID,
    SUPPORT_AREA_CODES,
)
from plugins.upr_visuals.formatters import _year_token, to_number
from plugins.upr_visuals.matrix import (
    _funding_area_code,
    _funding_column_bucket,
    _is_support_funding_column,
    _iter_matrix_numbers,
    _matrix_cells,
    _resolve_item,
    _split_cell_key,
)
from app.utils.api_serialization import _resolve_matrix_cell

def _load_t23_pns_totals(host_ns_id: int, period_name: str, year: int | None) -> dict[str, Any]:
    item_id = _pns_report_funding_item_id()
    if not item_id:
        return {"funding": 0.0, "expenditure": 0.0, "transferred": 0.0, "assignments": 0}
    period_names = [period_name]
    if year and str(year) not in period_names:
        period_names.append(str(year))
    entries = (
        db.session.query(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == PNS_REPORT_TEMPLATE_ID)
        .filter(AssignedForm.period_name.in_(period_names))
        .filter(FormData.form_item_id == item_id)
        .all()
    )
    return sum_t23_host_cells(entries, host_ns_id)


def _load_t23_funding_by_pns(host_ns_id: int, period_name: str, year: int | None) -> dict[int, float]:
    item_id = _pns_report_funding_item_id()
    if not item_id:
        return {}
    rows = _pns_country_matrix_rows(PNS_REPORT_TEMPLATE_ID, item_id, _period_names(period_name, year))
    if not rows:
        return {}
    pns_ns_by_aes = _pns_ns_id_by_aes([aes for _entry, aes in rows])
    return t23_host_funding_by_pns([entry for entry, _aes in rows], host_ns_id, pns_ns_by_aes)


def _load_t22_funding_by_pns(host_country_id: int, period_name: str, year: int | None) -> dict[int, float]:
    item_id = _pns_plan_funding_item_id()
    if not item_id:
        return {}
    rows = _pns_country_matrix_rows(PNS_PLAN_TEMPLATE_ID, item_id, _period_names(period_name, year))
    if not rows:
        return {}
    pns_ns_by_aes = _pns_ns_id_by_aes([aes for _entry, aes in rows])
    return t22_host_funding_by_pns([entry for entry, _aes in rows], host_country_id, pns_ns_by_aes)


def _period_names(period_name: str, year: int | None) -> list[str]:
    names: list[str] = []
    if period_name:
        names.append(period_name)
    if year and str(year) not in names:
        names.append(str(year))
    return names


def _pns_country_matrix_rows(template_id: int, item_id: int, period_names: list[str]):
    if not item_id or not period_names:
        return []
    return (
        db.session.query(FormData, AssignmentEntityStatus)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == int(template_id))
        .filter(AssignedForm.period_name.in_(period_names))
        .filter(FormData.form_item_id == int(item_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .all()
    )


def _pns_ns_id_by_aes(assignments: list[AssignmentEntityStatus]) -> dict[int, int]:
    country_ids = sorted({int(aes.entity_id) for aes in assignments if aes.entity_id})
    if not country_ids:
        return {}
    ns_rows = (
        NationalSociety.query.filter(NationalSociety.country_id.in_(country_ids))
        .filter(NationalSociety.is_active.is_(True))
        .order_by(NationalSociety.display_order.asc().nullslast(), NationalSociety.id.asc())
        .all()
    )
    country_to_ns: dict[int, int] = {}
    for ns in ns_rows:
        country_to_ns.setdefault(int(ns.country_id), int(ns.id))
    return {
        int(aes.id): country_to_ns[int(aes.entity_id)]
        for aes in assignments
        if aes.entity_id and int(aes.entity_id) in country_to_ns
    }


def sum_t23_host_cells(entries: list, host_ns_id: int) -> dict[str, Any]:
    """Sum published T23 funding-matrix cells whose row is this host National Society."""
    funding = expenditure = transferred = 0.0
    assignments = 0
    prefix = f"{int(host_ns_id)}_"
    for entry in entries:
        cells = _matrix_cells(entry)
        hit = False
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_ns_id):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if not number:
                continue
            hit = True
            lower = (col or "").lower()
            if "expend" in lower:
                expenditure += number
            elif "transfer" in lower:
                transferred += number
            elif "fund" in lower:
                funding += number
        if hit:
            assignments += 1
    return {
        "funding": funding,
        "expenditure": expenditure,
        "transferred": transferred,
        "assignments": assignments,
    }


def _pns_report_funding_item_id() -> int | None:
    """Published T23 funding matrix — label may be blank (currently item 1433)."""
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_REPORT_TEMPLATE_ID)
    version_id = getattr(template, "published_version_id", None) if template else None
    return _pns_report_funding_item_id_for_version(version_id)


@lru_cache(maxsize=8)
def _pns_report_funding_item_id_for_version(version_id: int | None) -> int | None:
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_REPORT_TEMPLATE_ID)
    if getattr(template, "published_version_id", None) != version_id:
        return None
    items = _plain_template_items(template)
    labeled = _resolve_item(items, PNS_REPORT_LABEL_NEEDLES["funding"], 0)
    if labeled:
        return labeled.id
    for item in items:
        label = (item.label or "").lower()
        if "staff" in label or "comment" in label:
            continue
        cfg = item.config if isinstance(getattr(item, "config", None), dict) else {}
        blob = str(cfg).lower()
        if "total funding" in blob and "total expenditure" in blob:
            return item.id
    scanned = _scan_template_matrix_item(PNS_REPORT_TEMPLATE_ID, "total funding")
    if scanned:
        return scanned
    return None


def _pns_plan_funding_item_id() -> int | None:
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_PLAN_TEMPLATE_ID)
    version_id = getattr(template, "published_version_id", None) if template else None
    return _pns_plan_funding_item_id_for_version(version_id)


@lru_cache(maxsize=8)
def _pns_plan_funding_item_id_for_version(version_id: int | None) -> int | None:
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(PNS_PLAN_TEMPLATE_ID)
    if getattr(template, "published_version_id", None) != version_id:
        return PNS_PLAN_ITEM_FALLBACKS["funding"]
    items = _plain_template_items(template)
    item = _resolve_item(items, PNS_PLAN_LABEL_NEEDLES["funding"], PNS_PLAN_ITEM_FALLBACKS["funding"])
    return item.id if item else PNS_PLAN_ITEM_FALLBACKS["funding"]


def _plain_template_items(template) -> list:
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return []
    return FormItem.query.filter(FormItem.version_id == version_id, FormItem.archived.is_(False)).all()


def _scan_template_matrix_item(template_id: int, needle: str) -> int | None:
    entries = (
        db.session.query(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == int(template_id))
        .limit(80)
        .all()
    )
    needle = needle.lower()
    for entry in entries:
        if any(needle in str(key).lower() for key in _matrix_cells(entry)):
            return entry.form_item_id
    return None


def _find_country_aes_for_year(
    template_id: int,
    country_id: int,
    year: int,
    *,
    annual_only: bool = False,
) -> AssignmentEntityStatus | None:
    rows = (
        AssignmentEntityStatus.query.options(
            joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignmentEntityStatus.entity_type == "country")
        .filter(AssignmentEntityStatus.entity_id == int(country_id))
        .filter(AssignedForm.template_id == int(template_id))
        .all()
    )
    exact = None
    yearly = None
    for aes in rows:
        pname = (aes.assigned_form.period_name if aes.assigned_form else "") or ""
        if pname == str(year):
            exact = aes
            break
        if _year_token(pname) != year:
            continue
        if annual_only and pname.lower().startswith("jan-jun"):
            continue
        yearly = yearly or aes
    return exact or yearly


def pns_area_funding_from_plan_cells(cells: dict[str, Any]) -> dict[int, dict[str, float]]:
    """Per-PNS Strategic Priority / Enabling Functions amounts from a T24 funding matrix."""
    grouped: dict[int, dict[str, float]] = {}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        try:
            ns_id = int(row)
        except (TypeError, ValueError):
            continue
        code = _funding_area_code(col)
        if not code:
            continue
        rec = grouped.setdefault(ns_id, {area: 0.0 for area in SUPPORT_AREA_CODES})
        rec[code] = rec.get(code, 0.0) + number
    return grouped


def pns_funding_from_plan_cells(cells: dict[str, Any]) -> dict[int, float]:
    """Per-PNS funding requirement from T24 hybrid matrix rows keyed by NationalSociety.id."""
    by_ns: dict[int, float] = {}
    totals: dict[int, float] = {}
    for key, raw in cells.items():
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        row, col = _split_cell_key(key)
        try:
            ns_id = int(row)
        except (TypeError, ValueError):
            continue
        bucket = _funding_column_bucket(col)
        if bucket == "row_total":
            totals[ns_id] = totals.get(ns_id, 0.0) + number
            continue
        if bucket in {"longer_term", "emergency"}:
            by_ns[ns_id] = by_ns.get(ns_id, 0.0) + number
    for ns_id, total in totals.items():
        if not by_ns.get(ns_id):
            by_ns[ns_id] = total
    return by_ns


def t23_host_funding_by_pns(
    entries: list,
    host_ns_id: int,
    pns_ns_by_aes: dict[int, int],
) -> dict[int, float]:
    """Per-PNS Total Funding from the published T23 funding matrix for this host NS."""
    by_pns: dict[int, float] = {}
    prefix = f"{int(host_ns_id)}_"
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        cells = _matrix_cells(entry)
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_ns_id) or not _is_support_funding_column(col):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if number:
                by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + number
    return by_pns


def t22_host_funding_by_pns(
    entries: list,
    host_country_id: int,
    pns_ns_by_aes: dict[int, int],
) -> dict[int, float]:
    """Per-PNS host-country totals from T22 item 1303 (`{country_id}_Total` or SP sum)."""
    by_pns: dict[int, float] = {}
    prefix = f"{int(host_country_id)}_"
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        cells = _matrix_cells(entry)
        total = 0.0
        areas = 0.0
        for key, raw in cells.items():
            if not str(key).startswith(prefix):
                continue
            row, col = _split_cell_key(str(key))
            if str(row) != str(host_country_id):
                continue
            number = to_number(_resolve_matrix_cell(raw))
            if not number:
                continue
            bucket = _funding_column_bucket(col)
            if bucket == "row_total" or (col or "").strip().lower() == "total":
                total += number
            elif bucket in {"longer_term", "emergency"}:
                areas += number
        value = total or areas
        if value:
            by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + value
    return by_pns


