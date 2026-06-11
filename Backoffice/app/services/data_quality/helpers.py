"""Shared helpers for data quality and validation scoring."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app import db
from app.models import Country, FormData, FormItem, IndicatorBank, AssignmentEntityStatus, AssignedForm
from app.models.enums import DocumentStatus
from app.models.forms import FormSection


def parse_period_year(period_name: str) -> int | None:
    import re

    if not period_name:
        return None
    years = re.findall(r"20\d{2}", str(period_name))
    if not years:
        return None
    return int(years[0])


def is_reported_value(entry: FormData | None) -> bool:
    if entry is None:
        return False
    if entry.data_not_available or entry.not_applicable:
        return True
    if entry.value is not None and str(entry.value).strip() not in ("", "0", "0.0"):
        return True
    if entry.disagg_data:
        total = entry.total_value
        if total is not None and float(total) != 0:
            return True
    return False


def _sum_numeric_mapping(mapping: dict) -> float:
    total = 0.0
    for key, val in mapping.items():
        if key in ("direct", "indirect"):
            continue
        if isinstance(val, dict):
            total += _sum_numeric_mapping(val)
        else:
            try:
                total += float(val or 0)
            except (TypeError, ValueError):
                pass
    return total


def form_item_label(item: FormItem | None, fallback_code: str) -> str:
    if item and item.label:
        return str(item.label).strip()
    bank = getattr(item, "indicator_bank", None) if item else None
    if bank and getattr(bank, "name", None):
        return str(bank.name).strip()
    return fallback_code


def parse_disagg_sex_age_totals(disagg_data: dict | None) -> tuple[float, float]:
    """
    Extract sex- and age-covered totals from FDRS disagg payloads.

    Supports modes: sex_age (male_5_17, …), sex, age, and nested direct/indirect buckets.
    Returns (sex_total, age_total).
    """
    if not disagg_data or not isinstance(disagg_data, dict):
        return 0.0, 0.0

    mode = (disagg_data.get("mode") or "").lower()
    values = disagg_data.get("values") or {}
    if not isinstance(values, dict):
        return 0.0, 0.0

    buckets: list[dict] = [values]
    direct = values.get("direct")
    if isinstance(direct, dict):
        buckets.append(direct)

    sex_total = 0.0
    age_total = 0.0
    cell_total = 0.0

    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        for key, val in bucket.items():
            if key in ("direct", "indirect") or isinstance(val, dict):
                continue
            try:
                fv = float(val or 0)
            except (TypeError, ValueError):
                continue
            cell_total += fv
            kl = str(key).lower()
            if kl in ("male", "female", "non_binary", "non-binary"):
                sex_total += fv
                age_total += fv
            elif kl.startswith("male") or kl.startswith("female") or kl.startswith("non_binary"):
                sex_total += fv
                age_total += fv
            elif mode == "age":
                age_total += fv

    if mode == "sex" and sex_total == 0:
        sex_total = cell_total
    if mode == "age" and age_total == 0:
        age_total = cell_total
    if mode == "sex_age":
        if sex_total == 0:
            sex_total = cell_total
        if age_total == 0:
            age_total = cell_total

    return sex_total, age_total


def numeric_value(entry: FormData | None) -> float | None:
    if entry is None:
        return None
    if entry.data_not_available or entry.not_applicable:
        return None
    tv = entry.total_value
    if tv is None:
        return None
    try:
        return float(tv)
    except (TypeError, ValueError):
        return None


def get_assignment_aes(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
) -> AssignmentEntityStatus | None:
    return (
        AssignmentEntityStatus.query.join(AssignedForm)
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.period_name == period_name,
            AssignmentEntityStatus.entity_type == entity_type,
            AssignmentEntityStatus.entity_id == entity_id,
        )
        .options(joinedload(AssignmentEntityStatus.assigned_form))
        .first()
    )


def list_assignment_periods(
    template_id: int,
    entity_type: str,
    entity_id: int,
) -> list[str]:
    """Reporting periods that have an assignment for this template + entity."""
    rows = (
        db.session.query(AssignedForm.period_name)
        .join(
            AssignmentEntityStatus,
            AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
        )
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == entity_type,
            AssignmentEntityStatus.entity_id == entity_id,
            AssignedForm.period_name.isnot(None),
        )
        .distinct()
        .all()
    )
    periods = [r[0] for r in rows if r[0]]

    def _sort_key(period_name: str) -> tuple[int, str]:
        year = parse_period_year(period_name)
        return (year or 0, period_name)

    return sorted(periods, key=_sort_key, reverse=True)


def list_exploration_period_names(template_id: int | None = None) -> list[str]:
    """
    Distinct reporting periods for Data Explorer filters.

    Includes all assignment lifecycle states (active, closed, deactivated) and
    any period that still has saved FormData rows.
    """
    from sqlalchemy import union

    af_q = db.session.query(AssignedForm.period_name.label("period_name")).filter(
        AssignedForm.period_name.isnot(None),
    )
    if template_id is not None:
        af_q = af_q.filter(AssignedForm.template_id == int(template_id))

    fd_q = (
        db.session.query(AssignedForm.period_name.label("period_name"))
        .join(
            AssignmentEntityStatus,
            AssignmentEntityStatus.assigned_form_id == AssignedForm.id,
        )
        .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .filter(AssignedForm.period_name.isnot(None))
    )
    if template_id is not None:
        fd_q = fd_q.filter(AssignedForm.template_id == int(template_id))

    combined = union(af_q, fd_q).subquery()
    rows = db.session.query(combined.c.period_name).distinct().all()
    periods = [r[0] for r in rows if r[0]]
    return sorted(periods, key=lambda p: (parse_period_year(p) or 0, p), reverse=True)


def resolve_assignment_aes(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
) -> tuple[AssignmentEntityStatus | None, str]:
    """
    Resolve assignment for a period string.

    Tries an exact ``AssignedForm.period_name`` match first, then matches by year
    (e.g. user enters ``2024`` when the assignment period is ``FDRS 2024``).
    """
    import re

    exact = get_assignment_aes(template_id, entity_type, entity_id, period_name)
    if exact:
        return exact, period_name

    target_year = parse_period_year(period_name)
    if target_year is None:
        return None, period_name

    for pn in list_assignment_periods(template_id, entity_type, entity_id):
        years = re.findall(r"20\d{2}", str(pn))
        if any(int(y) == target_year for y in years):
            aes = get_assignment_aes(template_id, entity_type, entity_id, pn)
            if aes:
                return aes, pn
    return None, period_name


def sum_matrix_disagg_values(disagg_data: dict | None) -> float:
    """Sum numeric cell values from a matrix FormData payload."""
    if not disagg_data or not isinstance(disagg_data, dict):
        return 0.0

    if "values" in disagg_data and isinstance(disagg_data["values"], dict):
        payload = disagg_data["values"]
    else:
        payload = disagg_data

    total = 0.0
    for key, val in payload.items():
        if key in ("mode", "values", "direct", "indirect"):
            continue
        if isinstance(val, dict):
            total += sum_matrix_disagg_values(val)
        else:
            try:
                total += float(val or 0)
            except (TypeError, ValueError):
                pass
    return total


def _find_income_sources_matrix_item(
    template_id: int,
    version_id: int | None,
) -> FormItem | None:
    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.item_type == "matrix",
            FormItem.archived == False,
        ).all()
    )
    if version_id:
        items = [i for i in items if i.version_id == version_id or i.version_id is None]

    for item in items:
        label = (item.label or "").lower()
        if "income" in label and "source" in label:
            return item
    return None


def _matrix_row_has_value(disagg_data: dict, row_name: str, column_names: list[str]) -> bool:
    for column in column_names:
        key = f"{row_name}_{column}"
        try:
            if float(disagg_data.get(key) or 0) != 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def compute_income_sources_ratio(
    aes_id: int,
    template_id: int,
    version_id: int | None,
    kpi_data: dict,
    income_source_kpi_codes: tuple[str, ...],
    total_income: float,
) -> float:
    """
    Score income-by-source reporting.

    - Legacy layouts: sum of per-KPI source fields vs total income.
    - FDRS matrix layout (template 21): share of matrix rows with values,
      boosted when the matrix sum reconciles with total income.
    """
    source_sum = 0.0
    for code in income_source_kpi_codes:
        entry = kpi_data.get(code, (None, None))[0]
        v = numeric_value(entry)
        if v is not None:
            source_sum += v
    if source_sum > 0 and total_income > 0:
        return min(1.0, source_sum / total_income)

    matrix_item = _find_income_sources_matrix_item(template_id, version_id)
    if not matrix_item:
        return 0.0

    entry = FormData.query.filter_by(
        assignment_entity_status_id=aes_id,
        form_item_id=matrix_item.id,
    ).first()
    if not entry or not entry.disagg_data:
        return 0.0

    matrix_sum = sum_matrix_disagg_values(entry.disagg_data)
    reconciliation = min(1.0, matrix_sum / total_income) if total_income > 0 else 0.0

    matrix_config = (matrix_item.config or {}).get("matrix_config") or {}
    rows = matrix_config.get("rows") or []
    columns = [c.get("name") for c in (matrix_config.get("columns") or []) if c.get("name")]
    if not rows or not columns:
        return reconciliation

    filled_rows = sum(
        1 for row in rows if _matrix_row_has_value(entry.disagg_data, row, columns)
    )
    row_coverage = filled_rows / len(rows)
    return max(row_coverage, reconciliation)


def load_form_data_by_kpi(
    aes_id: int,
    template_id: int,
    version_id: int | None,
) -> dict[str, tuple[FormData | None, FormItem | None]]:
    """Map fdrs_kpi_code -> (FormData, FormItem) for published items."""
    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.archived == False,
            FormItem.indicator_bank_id.isnot(None),
        )
        .options(joinedload(FormItem.indicator_bank))
        .all()
    )
    if version_id:
        items = [i for i in items if i.version_id == version_id or i.version_id is None]

    kpi_to_item: dict[str, FormItem] = {}
    for item in items:
        bank = item.indicator_bank
        if not bank or not bank.fdrs_kpi_code:
            continue
        code = bank.fdrs_kpi_code.strip()
        if code and code not in kpi_to_item:
            kpi_to_item[code] = item

    item_ids = [i.id for i in kpi_to_item.values()]
    data_rows = (
        FormData.query.filter(
            FormData.assignment_entity_status_id == aes_id,
            FormData.form_item_id.in_(item_ids),
        ).all()
        if item_ids
        else []
    )
    data_by_item = {d.form_item_id: d for d in data_rows}

    result: dict[str, tuple[FormData | None, FormItem | None]] = {}
    for code, item in kpi_to_item.items():
        result[code] = (data_by_item.get(item.id), item)
    return result


def section_name_matches(section: FormSection, keywords: tuple[str, ...]) -> bool:
    name = (section.name or "").lower()
    display = (getattr(section, "display_name", None) or "").lower()
    blob = f"{name} {display}"
    return any(kw in blob for kw in keywords)


def validation_question_counts(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
) -> dict[str, int]:
    from app.models.validation import ValidationQuestion

    base = ValidationQuestion.query.filter(
        ValidationQuestion.template_id == template_id,
        ValidationQuestion.entity_type == entity_type,
        ValidationQuestion.entity_id == entity_id,
        ValidationQuestion.period_name == period_name,
    )
    asked = base.count()
    answered = base.filter(ValidationQuestion.status == "answered").count()
    open_count = base.filter(ValidationQuestion.status == "open").count()
    waived = base.filter(ValidationQuestion.status == "waived").count()
    return {"asked": asked, "answered": answered, "open": open_count, "waived": waived}


def build_compliance_document_lookups(submitted_docs, item_id_to_doc_type):
    """
    Build presence, pending-validation, and cell-status lookups for FDRS compliance documents.

    Returns:
        present_lookup: (aes_id, doc_type) -> True when any submitted document exists
        pending_lookup: (aes_id, doc_type) -> True when a pending-validation document exists
        status_lookup: (aes_id, doc_type) -> missing | pending | approved | rejected
    """
    present_lookup: dict[tuple[int, str], bool] = {}
    pending_lookup: dict[tuple[int, str], bool] = {}
    status_lookup: dict[tuple[int, str], str] = {}
    for doc in submitted_docs or []:
        doc_type = item_id_to_doc_type.get(doc.form_item_id)
        if not doc_type:
            continue
        key = (doc.assignment_entity_status_id, doc_type)
        present_lookup[key] = True
        normalized = DocumentStatus.normalize(getattr(doc, "status", None))
        current = status_lookup.get(key)
        if normalized == DocumentStatus.PENDING:
            status_lookup[key] = "pending"
            pending_lookup[key] = True
        elif normalized == DocumentStatus.APPROVED:
            if current != "pending":
                status_lookup[key] = "approved"
        elif normalized == DocumentStatus.REJECTED:
            if current not in ("pending", "approved"):
                status_lookup[key] = "rejected"
    for key in present_lookup:
        status_lookup.setdefault(key, "approved")
    return present_lookup, pending_lookup, status_lookup


def compliance_doc_status_counts_toward_requirement(status: str | None) -> bool:
    """True when an approved document counts toward the compliance requirement."""
    return status == "approved"


def active_country_map_query():
    """Active countries from the country map (Country.status == 'Active')."""
    return Country.query.filter_by(status="Active").order_by(Country.name)


def fdrs_compliance_doc_label_matches(label: str | None, doc_type: str) -> bool:
    """
    Return True when a FDRS document-field label maps to a compliance doc type.

    Uses substring matching for flexibility (e.g. "Our Audited Financial Statements"),
    but excludes unaudited statements from counting as audited.
    """
    normalized = (label or "").strip().lower()
    if not normalized:
        return False

    target = (doc_type or "").strip().lower()
    if not target:
        return False

    if target == "audited financial statement" and "unaudited financial statement" in normalized:
        return False

    return target in normalized
