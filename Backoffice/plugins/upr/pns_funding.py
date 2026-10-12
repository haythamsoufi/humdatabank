"""PNS T22/T23 cross-submission funding lookups."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue
from app.models.form_items import FormItem
from app.models.forms import FormData
from app.models.organization import NationalSociety
from plugins.upr.catalog import (
    PNS_PLAN_ITEM_FALLBACKS,
    PNS_PLAN_LABEL_NEEDLES,
    PNS_PLAN_TEMPLATE_ID,
    PNS_REPORT_LABEL_NEEDLES,
    PNS_REPORT_TEMPLATE_ID,
    SUPPORT_AREA_CODES,
)
from plugins.upr.formatters import _year_token, to_number
from plugins.upr.matrix import (
    _funding_area_code,
    _funding_column_bucket,
    _iter_matrix_numbers,
    _matrix_cells,
    _resolve_item,
    _split_cell_key,
)
from app.utils.api_serialization import _resolve_matrix_cell

# --------------------------------------------------------------------------- #
# Published T23 (PNS Reporting) funding-matrix columns.
#
# The reporting National Society fills one row per host NS it supports, keyed
# ``{host_ns_id}_{column}``. The published matrix has exactly these value
# columns (see ``import_upr_excel_data.T23_PNS_FUNDING_COLUMNS``):
#
#   - "Total Funding"             → reported funding
#   - "Total Expenditure"         → reported expenditure
#   - "Total Transferred to HNS"  → reported transfer to the host NS
#
# A "Funding Requirement" column is also present: it is a *planning* figure
# copied from the Unified Country Plan and must never be read as a reported
# amount. We identify columns by exact (whitespace/case-normalized) name so a
# requirement value can never leak into a reported figure.
# --------------------------------------------------------------------------- #
T23_COL_FUNDING = "total funding"
T23_COL_EXPENDITURE = "total expenditure"
T23_COL_TRANSFERRED = "total transferred to hns"

# Canonical name → accepted (normalized) header spellings. Keep this tight: the
# importer writes the canonical names, these variants only guard against minor
# header drift in the published form definition.
_T23_COLUMN_ALIASES: dict[str, frozenset[str]] = {
    T23_COL_FUNDING: frozenset({T23_COL_FUNDING}),
    T23_COL_EXPENDITURE: frozenset({T23_COL_EXPENDITURE}),
    T23_COL_TRANSFERRED: frozenset({
        T23_COL_TRANSFERRED,
        "total transferred",
        "transferred to hns",
    }),
}

# Reported-funding selection order for the support visual's single amount:
# Total Funding first, then Total Expenditure, then Total Transferred to HNS.
T23_FUNDING_PRIORITY: tuple[str, ...] = (
    T23_COL_FUNDING,
    T23_COL_EXPENDITURE,
    T23_COL_TRANSFERRED,
)


def _normalize_column(col: str | None) -> str:
    """Lowercase, trim, and collapse internal whitespace for header matching."""
    return re.sub(r"\s+", " ", str(col or "").strip()).casefold()


def t23_funding_column(col: str | None) -> str | None:
    """Canonical T23 value column for *col*, or ``None`` (incl. Funding Requirement)."""
    text = _normalize_column(col)
    if not text:
        return None
    for canonical, aliases in _T23_COLUMN_ALIASES.items():
        if text in aliases:
            return canonical
    return None


def t23_host_row_metrics(cells: dict[str, Any], host_ns_id: int) -> dict[str, float]:
    """Total Funding / Expenditure / Transferred for *host_ns_id*'s row in *cells*.

    Only the three canonical columns are summed; anything else (Funding
    Requirement, SP/EF splits, etc.) is ignored. Returns an empty dict when the
    host NS has no reported value on this matrix.
    """
    prefix = f"{int(host_ns_id)}_"
    metrics: dict[str, float] = {}
    for key, raw in cells.items():
        key_s = str(key)
        if not key_s.startswith(prefix):
            continue
        row, col = _split_cell_key(key_s)
        if str(row) != str(host_ns_id):
            continue
        canonical = t23_funding_column(col)
        if not canonical:
            continue
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        metrics[canonical] = metrics.get(canonical, 0.0) + number
    return metrics


def t23_reported_funding(metrics: dict[str, float]) -> float:
    """Reported funding with fallback: Total Funding → Expenditure → Transferred."""
    for column in T23_FUNDING_PRIORITY:
        value = metrics.get(column)
        if value:
            return value
    return 0.0

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
    return t22_host_funding_by_pns([entry for entry, _aes in rows], host_country_id, pns_ns_by_aes, year)


@dataclass(frozen=True)
class PnsPlanOverride:
    """A PNS's own T22 figure for one host country and one plan year.

    ``total`` is the sum of the PNS's SP/EF cells for that year (else the year's total column).
    It is ``0`` when the PNS submitted its form but left this host country blank. ``areas``
    holds the non-zero SP1-SP5 / EFs amounts the PNS entered.
    """

    total: float = 0.0
    areas: dict[str, float] = field(default_factory=dict)


# ``{ns_id: {plan_year: override}}`` for PNSs that self-reported in T22.
PnsPlanOverrides = dict[int, dict[int, PnsPlanOverride]]

# A PNS counts as having self-reported once its T22 assignment is submitted or approved.
T22_SELF_REPORTED_STATUSES = (
    AssignmentEntityStatusValue.submitted,
    AssignmentEntityStatusValue.approved,
)

# T22 item 1303 columns are saved resolved per assignment: ``SP1_[assignment_year]`` ->
# ``SP1_2026``, ``SP1_[[assignment_year]+1]`` -> ``SP1_2027`` (key ``{host_country_id}_SP1_2026``).
# Rows saved before the multi-year columns existed use plain ``SP1`` / ``Total``.
_T22_YEAR_COLUMN = re.compile(r"^(?P<code>SP[1-5]|EFs|fr_tot|confirmedfn)_(?P<year>\d{4})$", re.IGNORECASE)


def t22_funding_cells_by_year(
    cells: dict[str, Any],
    host_country_id: int,
    first_year: int | None,
) -> dict[int, PnsPlanOverride]:
    """Read this host country's row of a PNS's T22 funding matrix, one entry per plan year.

    Year-suffixed columns (``SP1_2027``) belong to that year; the SP/EF cells win and the year's
    total column (``fr_tot_2027``) is only a fallback. Legacy plain ``SP1`` / ``Total`` cells
    belong to *first_year*, where ``Total`` wins as it always did. Blank cells count as zero.
    """
    prefix = f"{int(host_country_id)}_"
    areas: dict[int, dict[str, float]] = {}
    totals: dict[int, float] = {}
    legacy_areas: dict[str, float] = {}
    legacy_total = 0.0
    for key, raw in cells.items():
        if not str(key).startswith(prefix):
            continue
        row, col = _split_cell_key(str(key))
        if str(row) != str(host_country_id):
            continue
        number = to_number(_resolve_matrix_cell(raw))
        if not number:
            continue
        col = (col or "").strip()
        match = _T22_YEAR_COLUMN.match(col)
        if match:
            code, year = match.group("code"), int(match.group("year"))
            if code.lower() == "fr_tot":
                totals[year] = totals.get(year, 0.0) + number
            elif code.lower() != "confirmedfn":
                area = "EFs" if code.lower() == "efs" else code.upper()
                areas.setdefault(year, {})
                areas[year][area] = areas[year].get(area, 0.0) + number
            continue
        if col.lower() == "total":
            legacy_total += number
            continue
        code = _funding_area_code(col)
        if code:
            legacy_areas[code] = legacy_areas.get(code, 0.0) + number
    out: dict[int, PnsPlanOverride] = {}
    for year in sorted(set(areas) | set(totals)):
        year_areas = areas.get(year, {})
        out[year] = PnsPlanOverride(total=sum(year_areas.values()) or totals.get(year, 0.0), areas=year_areas)
    legacy_year = first_year if first_year is not None else 0  # 0 = year unknown
    if legacy_year not in out and (legacy_total or legacy_areas):
        out[legacy_year] = PnsPlanOverride(
            total=legacy_total or sum(legacy_areas.values()),
            areas=legacy_areas,
        )
    return out


def load_t22_pns_overrides(
    host_country_id: int,
    period_name: str,
    year: int | None,
) -> PnsPlanOverrides:
    """Per-PNS (``NationalSociety.id``) T22 figures for PNSs that have self-reported.

    Every PNS whose T22 assignment for the period is submitted/approved is authoritative for
    *this* host country, even when its row is empty (a year it left blank reads as zero via
    :func:`overrides_for_year`). PNSs that have not submitted are absent, so the host's own T24
    figure still applies to them. *year* is the assignment (first plan) year.
    """
    item_id = _pns_plan_funding_item_id()
    names = _period_names(period_name, year)
    if not item_id or not names:
        return {}
    aes_rows = (
        AssignmentEntityStatus.query.join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(AssignedForm.template_id == PNS_PLAN_TEMPLATE_ID)
        .filter(AssignedForm.period_name.in_(names))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .filter(AssignmentEntityStatus.entity_id != int(host_country_id))
        .filter(AssignmentEntityStatus.status.in_(T22_SELF_REPORTED_STATUSES))
        .all()
    )
    if not aes_rows:
        return {}
    entries = {
        int(entry.assignment_entity_status_id): entry
        for entry in db.session.query(FormData)
        .filter(FormData.assignment_entity_status_id.in_([aes.id for aes in aes_rows]))
        .filter(FormData.form_item_id == int(item_id))
        .all()
    }
    pns_ns_by_aes = _pns_ns_id_by_aes(aes_rows)
    overrides: PnsPlanOverrides = {}
    for aes in aes_rows:
        ns_id = pns_ns_by_aes.get(int(aes.id))
        if not ns_id:
            continue
        by_year = t22_funding_cells_by_year(_matrix_cells(entries.get(int(aes.id))), host_country_id, year)
        previous = overrides.get(int(ns_id))
        if previous is None or (
            sum(o.total for o in by_year.values()) > sum(o.total for o in previous.values())
        ):
            overrides[int(ns_id)] = by_year
    return overrides


def overrides_for_year(overrides: PnsPlanOverrides, year: int) -> dict[int, PnsPlanOverride]:
    """``{ns_id: override}`` for one plan year; a PNS with nothing for that year reads as zero."""
    return {ns_id: by_year.get(year, PnsPlanOverride()) for ns_id, by_year in overrides.items()}


def strip_pns_rows(cells: dict[str, Any], ns_ids: set[int] | frozenset[int]) -> dict[str, Any]:
    """Drop T24 funding cells whose row is one of *ns_ids* (numeric National Society rows)."""
    if not ns_ids:
        return cells
    kept: dict[str, Any] = {}
    for key, raw in cells.items():
        row, _col = _split_cell_key(str(key))
        if row.isdigit() and int(row) in ns_ids:
            continue
        kept[key] = raw
    return kept


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
    """Sum published T23 funding-matrix cells whose row is this host National Society.

    Each metric (Total Funding / Total Expenditure / Total Transferred to HNS)
    is kept separate for the financial network block. ``Funding Requirement`` is
    a planning figure and is never counted.
    """
    funding = expenditure = transferred = 0.0
    assignments = 0
    for entry in entries:
        metrics = t23_host_row_metrics(_matrix_cells(entry), host_ns_id)
        if not metrics:
            continue
        assignments += 1
        funding += metrics.get(T23_COL_FUNDING, 0.0)
        expenditure += metrics.get(T23_COL_EXPENDITURE, 0.0)
        transferred += metrics.get(T23_COL_TRANSFERRED, 0.0)
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
    """Per-PNS reported funding from the published T23 matrix for this host NS.

    For each reporting NS we read its row for *host_ns_id* and take, in order,
    Total Funding → Total Expenditure → Total Transferred to HNS (first
    non-empty wins). ``Funding Requirement`` is a planning figure and is never
    used.
    """
    by_pns: dict[int, float] = {}
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        metrics = t23_host_row_metrics(_matrix_cells(entry), host_ns_id)
        value = t23_reported_funding(metrics)
        if value:
            by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + value
    return by_pns


def t22_host_funding_by_pns(
    entries: list,
    host_country_id: int,
    pns_ns_by_aes: dict[int, int],
    year: int | None = None,
) -> dict[int, float]:
    """Per-PNS host-country totals from T22 item 1303 for the first plan year *year*.

    Reads the year's SP/EF columns (``SP1_2026``) or, for rows saved before the multi-year
    columns, the legacy ``{country_id}_Total`` / plain SP sum.
    """
    by_pns: dict[int, float] = {}
    for entry in entries:
        pns_ns_id = pns_ns_by_aes.get(int(getattr(entry, "assignment_entity_status_id", 0) or 0))
        if not pns_ns_id:
            continue
        by_year = t22_funding_cells_by_year(_matrix_cells(entry), host_country_id, year)
        if year is None and by_year:
            year_key = min(by_year)
        else:
            year_key = year
        value = by_year[year_key].total if year_key in by_year else 0.0
        if value:
            by_pns[int(pns_ns_id)] = by_pns.get(int(pns_ns_id), 0.0) + value
    return by_pns


