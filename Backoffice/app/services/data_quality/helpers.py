"""Shared helpers for data quality and validation scoring."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app import db
from app.models import FormData, FormItem, IndicatorBank, AssignmentEntityStatus, AssignedForm
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
