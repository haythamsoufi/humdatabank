"""FDRS columns on the validation dashboard tracker."""

from __future__ import annotations

from app.models import FormData, FormItem
from app.services.data_quality.helpers import (
    compute_income_sources_ratio,
    is_reported_value,
    numeric_value,
)
from app.services.validation.pack_registry import ValidationTracker
from plugins.fdrs.data_quality import fdrs_v1_catalog as cat
from plugins.fdrs.data_quality.fdrs_v1_catalog import fdrs_compliance_doc_label_matches

SECTION_SPECS: tuple[dict[str, str], ...] = (
    {"key": "governance", "label": "Governance"},
    {"key": "finance", "label": "Finance"},
    {"key": "reach", "label": "Reach"},
)

DOCUMENT_SPECS: tuple[dict[str, str], ...] = (
    {"key": "annual_report", "label": "Annual Report"},
    {"key": "audited_financial", "label": "Audited Financial Statement"},
    {"key": "strategic_plan", "label": "Strategic Plan"},
    {"key": "unaudited_financial", "label": "Unaudited Financial Statement"},
)

REQUIRED_DOCUMENT_KEYS: tuple[str, ...] = ("annual_report", "audited_financial")


def indicator_code(bank) -> str | None:
    raw = getattr(bank, "fdrs_kpi_code", None)
    if not isinstance(raw, str):
        return None
    code = raw.strip()
    return code or None


def document_matches(label: str | None, doc_label: str) -> bool:
    return fdrs_compliance_doc_label_matches(label, doc_label)


def reporting_section_ratios(
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


FDRS_TRACKER = ValidationTracker(
    sections=SECTION_SPECS,
    documents=DOCUMENT_SPECS,
    section_ratios=reporting_section_ratios,
    document_matches=document_matches,
    indicator_code=indicator_code,
    required_document_keys=REQUIRED_DOCUMENT_KEYS,
)
