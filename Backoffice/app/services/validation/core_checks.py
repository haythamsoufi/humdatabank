"""General validation checks that every data-quality template can run.

These cover blank required indicators, values that disappeared since last year,
and variation against prior-year history. Product plugins add their own rules
on top and do not repeat these.
"""

from __future__ import annotations

from app.models.validation import ValidationKpiCheckType, ValidationThreshold
from app.services.data_quality.helpers import is_reported_value, numeric_value, parse_period_year
from app.services.validation.history import (
    CHECK_TYPE_PAST_YEAR,
    baseline_value,
    threshold_exceeded,
    ytd_pct,
)
from app.services.validation.types import CheckResult
from app.utils.data_quality_constants import RULE_PACK_CORE

# English text used when an admin has not saved a question template yet.
CORE_QUESTION_DEFAULTS: dict[str, tuple[str, bool]] = {
    "indicator_not_reported": ("This indicator is not reported.", False),
    "not_reported": (
        "This indicator was reported last year but is missing this year.",
        False,
    ),
    "past_year_threshold": (
        "This value changed by more than the allowed threshold compared to the prior year:",
        True,
    ),
    "past_3years_avg": (
        "This value changed by more than the allowed threshold compared to the three-year average:",
        True,
    ),
}


def format_core_question_suffix(rule_code: str, context: dict) -> str:
    """Percent change appended to variation questions."""
    if rule_code in ("past_year_threshold", "past_3years_avg"):
        pct = context.get("ytd_pct") or context.get("yoy_pct")
        if pct is not None:
            return f"{pct * 100:.2f}%"
    return ""


def _query_rows(query) -> list:
    """Return query rows. Stubs that only set ``.first()`` still work."""
    rows = query.all()
    if isinstance(rows, list):
        return rows
    one = query.first()
    return [one] if one is not None else []


def _index_by_kpi(rows: list) -> dict[str, object]:
    indexed: dict[str, object] = {}
    for row in rows:
        code = getattr(row, "kpi_code", None)
        if isinstance(code, str) and code:
            indexed[code] = row
    return indexed


def _is_required(item) -> bool:
    config = getattr(item, "config", None)
    if not isinstance(config, dict):
        return False
    return bool(config.get("is_required"))


def run_core_checks(ctx, *, required_indicator_codes: tuple[str, ...] | frozenset[str] = ()) -> list[CheckResult]:
    """Missing-data and historical-variation checks for one assignment."""
    if not getattr(ctx, "kpi_data", None):
        return []

    required = set(required_indicator_codes)
    year = parse_period_year(ctx.period_name)
    check_by_kpi = _index_by_kpi(
        _query_rows(ValidationKpiCheckType.query.filter_by(template_id=ctx.template_id))
    )
    thresh_by_kpi: dict[str, object] = {}
    if ctx.country_id:
        thresh_by_kpi = _index_by_kpi(
            _query_rows(
                ValidationThreshold.query.filter_by(
                    country_id=ctx.country_id,
                    template_id=ctx.template_id,
                )
            )
        )

    results: list[CheckResult] = []
    for kpi_code, (entry, item) in ctx.kpi_data.items():
        form_item_id = item.id if item else None
        blank = not is_reported_value(entry)
        flagged_blank = False
        if blank and (kpi_code in required or _is_required(item)):
            flagged_blank = True
            results.append(
                CheckResult(
                    rule_code="indicator_not_reported",
                    form_item_id=form_item_id,
                    fired=True,
                    severity="warning",
                    kpi_code=kpi_code,
                )
            )

        if year and ctx.country_id:
            check_row = check_by_kpi.get(kpi_code)
            thresh_row = thresh_by_kpi.get(kpi_code)
            threshold = getattr(thresh_row, "threshold_fraction", None) if thresh_row else None
            if check_row and threshold is not None:
                current = numeric_value(entry)
                hist = ctx.history_by_kpi.get(kpi_code, {})
                baseline = baseline_value(hist, year, check_row.check_type)
                change = ytd_pct(current, baseline)
                if threshold_exceeded(change, threshold):
                    rule = (
                        "past_year_threshold"
                        if check_row.check_type == CHECK_TYPE_PAST_YEAR
                        else "past_3years_avg"
                    )
                    results.append(
                        CheckResult(
                            rule_code=rule,
                            form_item_id=form_item_id,
                            fired=True,
                            severity="warning",
                            kpi_code=kpi_code,
                            context={
                                "ytd_pct": change,
                                "threshold": threshold,
                                "current": current,
                                "baseline": baseline,
                            },
                        )
                    )

        prior = ctx.history_by_kpi.get(kpi_code, {}).get((year - 1) if year else 0)
        if year and prior and prior != 0 and blank and not flagged_blank:
            results.append(
                CheckResult(
                    rule_code="not_reported",
                    form_item_id=form_item_id,
                    fired=True,
                    severity="warning",
                    kpi_code=kpi_code,
                    context={"prior_year": year - 1, "prior_value": prior},
                )
            )
    return results


def register_core_validation_pack() -> None:
    """Register the built-in pack. Safe to call more than once."""
    from app.services.validation.pack_registry import ValidationPack, register_pack
    from app.services.validation.rule_registry import CORE_RULES

    register_pack(
        ValidationPack(
            code=RULE_PACK_CORE,
            label="General checks",
            run_checks=run_core_checks,
            rules=CORE_RULES,
            format_suffix=format_core_question_suffix,
        )
    )
