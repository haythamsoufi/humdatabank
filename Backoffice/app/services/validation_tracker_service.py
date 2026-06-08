"""Validation dashboard tracker — assignment progress by country and reporting period."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from app import db
from app.models import FormData, FormItem, SubmittedDocument
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.enums import status_display_label
from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.helpers import (
    active_country_map_query,
    compute_income_sources_ratio,
    fdrs_compliance_doc_label_matches,
    is_reported_value,
    load_form_data_by_kpi,
    numeric_value,
    parse_period_year,
    resolve_assignment_aes,
)
from app.services.validation_dashboard_service import global_periods_for_template

# Document types shown as upload columns (FDRS template 21).
TRACKER_DOCUMENT_SPECS: tuple[dict[str, str], ...] = (
    {"key": "annual_report", "label": "Annual Report"},
    {"key": "audited_financial", "label": "Audited Financial Statement"},
    {"key": "strategic_plan", "label": "Strategic Plan"},
    {"key": "unaudited_financial", "label": "Unaudited Financial Statement"},
)

TRACKER_SECTION_SPECS: tuple[dict[str, str], ...] = (
    {"key": "governance", "label": "Governance"},
    {"key": "finance", "label": "Finance"},
    {"key": "reach", "label": "Reach"},
)

_STATUS_RANK = {
    "approved": 5,
    "submitted": 4,
    "sent_for_review": 3,
    "requires_revision": 3,
    "in_progress": 2,
    "pending": 1,
}


def _status_value(aes: AssignmentEntityStatus | None) -> str:
    if aes is None:
        return "no_assignment"
    raw = aes.status.value if hasattr(aes.status, "value") else str(aes.status)
    return raw or "pending"


def _section_fill_status(ratio: float) -> str:
    if ratio <= 0:
        return "not_started"
    if ratio >= 0.999:
        return "complete"
    return "in_progress"


def _overall_completion_rate(section_ratios: dict[str, float]) -> float:
    if not section_ratios:
        return 0.0
    values = list(section_ratios.values())
    return round(sum(values) / len(values) * 100, 1)


def _reporting_section_ratios(
    kpi_data: dict[str, tuple[FormData | None, FormItem | None]],
    *,
    aes_id: int,
    template_id: int,
    version_id: int | None,
) -> dict[str, float]:
    gov_reported = sum(
        1 for code in cat.GOVERNANCE_KPI_CODES if is_reported_value(kpi_data.get(code, (None, None))[0])
    )
    gov_ratio = gov_reported / len(cat.GOVERNANCE_KPI_CODES) if cat.GOVERNANCE_KPI_CODES else 0.0

    income_entry = kpi_data.get(cat.FINANCE_TOTAL_INCOME, (None, None))[0]
    expend_entry = kpi_data.get(cat.FINANCE_TOTAL_EXPENDITURE, (None, None))[0]
    income_reported = 1.0 if is_reported_value(income_entry) else 0.0
    expend_reported = 1.0 if is_reported_value(expend_entry) else 0.0
    total_income = numeric_value(income_entry) or 0.0
    income_sources_ratio = compute_income_sources_ratio(
        aes_id,
        template_id,
        version_id,
        kpi_data,
        cat.INCOME_SOURCE_KPI_CODES,
        total_income,
    )
    finance_ratio = income_reported * 0.35 + expend_reported * 0.35 + income_sources_ratio * 0.30

    reach_reported = sum(
        1 for code in cat.REACH_KPI_CODES if is_reported_value(kpi_data.get(code, (None, None))[0])
    )
    reach_ratio = reach_reported / len(cat.REACH_KPI_CODES) if cat.REACH_KPI_CODES else 0.0

    return {
        "governance": round(gov_ratio, 3),
        "finance": round(finance_ratio, 3),
        "reach": round(reach_ratio, 3),
    }


def _document_field_map(template_id: int) -> dict[str, list[int]]:
    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.item_type == "document_field",
            FormItem.archived == False,  # noqa: E712
        ).all()
    )
    mapping: dict[str, list[int]] = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
    for item in items:
        label = (item.label or "").strip()
        for spec in TRACKER_DOCUMENT_SPECS:
            if fdrs_compliance_doc_label_matches(label, spec["label"]) or label == spec["label"]:
                mapping[spec["key"]].append(item.id)
                break
    return mapping


def _bulk_kpi_data_by_aes(
    aes_ids: list[int],
    template_id: int,
    version_id: int | None,
) -> dict[int, dict[str, tuple[FormData | None, FormItem | None]]]:
    if not aes_ids:
        return {}

    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.archived == False,  # noqa: E712
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
            FormData.assignment_entity_status_id.in_(aes_ids),
            FormData.form_item_id.in_(item_ids),
        ).all()
        if item_ids
        else []
    )

    data_by_aes_item: dict[tuple[int, int], FormData] = {}
    for row in data_rows:
        data_by_aes_item[(row.assignment_entity_status_id, row.form_item_id)] = row

    result: dict[int, dict[str, tuple[FormData | None, FormItem | None]]] = {}
    for aes_id in aes_ids:
        per_aes: dict[str, tuple[FormData | None, FormItem | None]] = {}
        for code, item in kpi_to_item.items():
            per_aes[code] = (data_by_aes_item.get((aes_id, item.id)), item)
        result[aes_id] = per_aes
    return result


def build_tracker_data(template_id: int, period_name: str) -> dict[str, Any]:
    """Rows, aggregate stats, and map payload for the validation dashboard tracker tab."""
    assignment = (
        AssignedForm.query.filter(
            AssignedForm.template_id == template_id,
            AssignedForm.period_name == period_name,
        ).first()
    )

    countries = active_country_map_query().all()

    doc_field_map = _document_field_map(template_id)
    all_doc_item_ids = [iid for ids in doc_field_map.values() for iid in ids]

    template = assignment.template if assignment else None
    version_id = template.published_version_id if template else None
    delegation_review_enabled = bool(assignment and assignment.requires_delegation_review)

    aes_by_country: dict[int, AssignmentEntityStatus] = {}
    resolved_period_by_country: dict[int, str] = {}
    if assignment:
        aes_rows = (
            AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.assigned_form_id == assignment.id,
                AssignmentEntityStatus.entity_type == "country",
            ).all()
        )
        for aes in aes_rows:
            aes_by_country[aes.entity_id] = aes
            resolved_period_by_country[aes.entity_id] = period_name
    else:
        for country in countries:
            aes, resolved = resolve_assignment_aes(template_id, "country", country.id, period_name)
            if aes:
                aes_by_country[country.id] = aes
                resolved_period_by_country[country.id] = resolved

    aes_ids = [aes.id for aes in aes_by_country.values()]
    kpi_by_aes = _bulk_kpi_data_by_aes(aes_ids, template_id, version_id)

    submitted_docs: list[SubmittedDocument] = []
    if aes_ids and all_doc_item_ids:
        submitted_docs = (
            SubmittedDocument.query.filter(
                SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                SubmittedDocument.form_item_id.in_(all_doc_item_ids),
            ).all()
        )
    doc_lookup: set[tuple[int, str]] = set()
    reverse_item_key: dict[int, str] = {}
    for key, item_ids in doc_field_map.items():
        for item_id in item_ids:
            reverse_item_key[item_id] = key
    for doc in submitted_docs:
        doc_key = reverse_item_key.get(doc.form_item_id)
        if doc_key:
            doc_lookup.add((doc.assignment_entity_status_id, doc_key))

    rows: list[dict[str, Any]] = []
    map_countries: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    section_complete_counts = {spec["key"]: 0 for spec in TRACKER_SECTION_SPECS}
    docs_both_required = 0

    for country in countries:
        aes = aes_by_country.get(country.id)
        if not aes:
            continue

        status = _status_value(aes)
        status_counts[status] = status_counts.get(status, 0) + 1

        sections: dict[str, str] = {spec["key"]: "not_started" for spec in TRACKER_SECTION_SPECS}
        section_ratios: dict[str, float] = {spec["key"]: 0.0 for spec in TRACKER_SECTION_SPECS}
        kpi_data = kpi_by_aes.get(aes.id)
        if kpi_data is None:
            kpi_data = load_form_data_by_kpi(aes.id, template_id, version_id)
        ratios = _reporting_section_ratios(
            kpi_data,
            aes_id=aes.id,
            template_id=template_id,
            version_id=version_id,
        )
        for key, ratio in ratios.items():
            section_ratios[key] = ratio
            fill = _section_fill_status(ratio)
            sections[key] = fill
            if fill == "complete":
                section_complete_counts[key] = section_complete_counts.get(key, 0) + 1

        documents: dict[str, bool] = {spec["key"]: False for spec in TRACKER_DOCUMENT_SPECS}
        for spec in TRACKER_DOCUMENT_SPECS:
            documents[spec["key"]] = (aes.id, spec["key"]) in doc_lookup

        has_ar = documents.get("annual_report", False)
        has_afs = documents.get("audited_financial", False)
        if has_ar and has_afs:
            docs_both_required += 1

        row = {
            "country_id": country.id,
            "country_name": country.name,
            "country_iso3": country.iso3,
            "region": country.region,
            "period_name": resolved_period_by_country.get(country.id),
            "assignment_id": aes.assigned_form_id,
            "status": status,
            "status_label": status_display_label(status),
            "submitted_at": aes.submitted_at.isoformat() if aes.submitted_at else None,
            "sections": sections,
            "section_ratios": section_ratios,
            "completion_rate": _overall_completion_rate(section_ratios),
            "documents": documents,
        }
        rows.append(row)

        map_countries.append(
            {
                "country_id": country.id,
                "iso3": country.iso3,
                "label": country.name,
                "status": status,
                "status_rank": _STATUS_RANK.get(status, 0),
            }
        )

    submitted_like = sum(
        1 for r in rows
        if r["status"] in (
            ("submitted", "approved", "sent_for_review")
            if delegation_review_enabled
            else ("submitted", "approved")
        )
    )
    approved_count = sum(1 for r in rows if r["status"] == "approved")

    stats = {
        "country_count": len(rows),
        "assigned_count": len(rows),
        "by_status": status_counts,
        "delegation_review_enabled": delegation_review_enabled,
        "submitted_count": submitted_like,
        "approved_count": approved_count,
        "in_progress_count": status_counts.get("in_progress", 0),
        "pending_count": status_counts.get("pending", 0),
        "documents_both_required_count": docs_both_required,
        "section_complete_counts": section_complete_counts,
        "reporting_year": parse_period_year(period_name),
    }

    return {
        "template_id": template_id,
        "period_name": period_name,
        "delegation_review_enabled": delegation_review_enabled,
        "rows": rows,
        "stats": stats,
        "map": {"countries": map_countries},
        "documents_meta": [{"key": s["key"], "label": s["label"]} for s in TRACKER_DOCUMENT_SPECS],
        "sections_meta": [{"key": s["key"], "label": s["label"]} for s in TRACKER_SECTION_SPECS],
    }


def tracker_periods_for_template(template_id: int) -> list[str]:
    return global_periods_for_template(template_id)
