"""FDRS-specific AI/analytics presets over the generic bulk form-field query.

Cross-country FDRS income-by-source analysis. Kept for programmatic/API use;
the AI agent itself uses ``get_form_field_values_for_all_countries`` (core,
generic) with matrix share parameters directly instead of calling through
this preset.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.services.ai.data.form_retrieval import get_form_field_values_for_all_countries
from plugins.fdrs.data_quality.fdrs_v1_catalog import FINANCE_TOTAL_INCOME

_FDRS_HOME_GOV_ROW = "Home Government"
_FDRS_FOREIGN_GOV_ROW = "Foreign Government"
_FDRS_INCOME_MATRIX_COLUMN = "Funding"


def get_fdrs_income_sources_for_all_countries(
    assignment_period: Optional[str] = None,
    min_share_pct: Optional[float] = None,
    source_type: Optional[str] = None,
    max_countries: int = 250,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Cross-country FDRS income-by-source analysis (preset wrapper over bulk form-field query).

    Kept for programmatic/API use; the AI agent uses get_form_field_values_for_all_countries
    with matrix share parameters instead.
    """
    source_norm = (source_type or "any").strip().lower().replace(" ", "_")
    if source_norm not in {"any", "home_government", "foreign_government"}:
        source_norm = "any"

    share_rows = [_FDRS_HOME_GOV_ROW, _FDRS_FOREIGN_GOV_ROW]
    threshold_rows = share_rows
    if source_norm == "home_government":
        threshold_rows = [_FDRS_HOME_GOV_ROW]
    elif source_norm == "foreign_government":
        threshold_rows = [_FDRS_FOREIGN_GOV_ROW]

    base = get_form_field_values_for_all_countries(
        field_label_or_name="income sources",
        template_identifier="FDRS",
        assignment_period=assignment_period,
        matrix_share_rows=share_rows,
        matrix_share_column=_FDRS_INCOME_MATRIX_COLUMN,
        min_share_pct=min_share_pct,
        share_match="any",
        share_threshold_rows=threshold_rows,
        denominator_kpi_code=FINANCE_TOTAL_INCOME,
        max_countries=max_countries,
        on_progress=on_progress,
    )
    if not base.get("success"):
        return base

    rows = base.get("rows") or []
    rows_out: List[Dict[str, Any]] = []
    for row in rows:
        sb = row.get("share_breakdown") or {}
        home = sb.get(_FDRS_HOME_GOV_ROW) or {}
        foreign = sb.get(_FDRS_FOREIGN_GOV_ROW) or {}
        rows_out.append({
            "country_id": row.get("country_id"),
            "country_name": row.get("country_name"),
            "iso3": row.get("iso3"),
            "region": row.get("region"),
            "period": row.get("period_used"),
            "total_income_chf": row.get("share_denominator"),
            "home_government_chf": home.get("amount"),
            "foreign_government_chf": foreign.get("amount"),
            "home_government_pct": home.get("share_pct"),
            "foreign_government_pct": foreign.get("share_pct"),
            "data_status": row.get("data_status"),
            "assignment_name": "FDRS",
        })

    return {
        "success": True,
        "template_name": "FDRS",
        "matrix_field": base.get("field_label_resolved") or "Income Sources",
        "assignment_period": assignment_period,
        "min_share_pct": min_share_pct,
        "source_type": source_norm,
        "rows": rows_out,
        "count": len(rows_out),
        "note": base.get("note") or (
            "Data comes from the FDRS Income Sources matrix (form template 21), not Indicator Bank "
            "indicator names. Percentages use Total income (KPI_IncomeLC_CHF) when reported for the "
            "same assignment; otherwise the matrix row sum is used as denominator."
        ),
        "note_platform_region": base.get("note_platform_region"),
    }
