"""Register the FDRS matrix validation pack with the core registry."""

from __future__ import annotations

from plugins.fdrs.data_quality import fdrs_v1_catalog as cat
from plugins.fdrs.validation.fdrs_matrix.rules import NON_ZERO_KPI_CODES, run_fdrs_matrix_rules
from app.services.validation.pack_registry import ValidationPack, register_pack
from app.services.validation.rule_registry import FDRS_MATRIX_V1_RULES
from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1

FDRS_THRESHOLD_KPI_CODES = tuple(sorted(
    set(cat.GOVERNANCE_KPI_CODES)
    | set(cat.REACH_KPI_CODES)
    | {cat.FINANCE_TOTAL_INCOME, cat.FINANCE_TOTAL_EXPENDITURE}
))


def format_fdrs_question_suffix(rule_code: str, context: dict) -> str:
    """Computed ending for FDRS question templates that need a value."""
    if rule_code in ("past_year_threshold", "past_3years_avg"):
        pct = context.get("ytd_pct") or context.get("yoy_pct")
        if pct is not None:
            return f"{pct * 100:.2f}%"
    if rule_code == "higher_than_pop":
        pop = context.get("population")
        if pop is not None:
            return f"{int(pop):,}"
    if rule_code == "significant_pop":
        ratio = context.get("ratio")
        if ratio is not None:
            return f"{ratio * 100:.2f}%"
    if rule_code == "branches_higher_units":
        units = context.get("local_units")
        if units is not None:
            return f"{int(units):,}"
    if rule_code == "fiscal_year":
        days = context.get("fiscal_days")
        if days is not None:
            return str(int(days))
    if rule_code == "awsd_check":
        awsd = context.get("awsd_deaths")
        if awsd is not None:
            return f"{int(awsd):,}"
    if rule_code == "typeofprograms":
        progs = context.get("programmes") or []
        if progs:
            return ", ".join(progs) + "."
    return ""


def register_fdrs_validation_pack() -> None:
    register_pack(
        ValidationPack(
            code=RULE_PACK_FDRS_MATRIX_V1,
            label="FDRS matrix v1",
            run_checks=run_fdrs_matrix_rules,
            rules=FDRS_MATRIX_V1_RULES,
            format_suffix=format_fdrs_question_suffix,
            threshold_kpi_codes=FDRS_THRESHOLD_KPI_CODES,
            required_indicator_codes=tuple(sorted(NON_ZERO_KPI_CODES)),
            tracker_id="fdrs",
        )
    )
