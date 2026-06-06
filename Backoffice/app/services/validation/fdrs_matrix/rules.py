"""
FDRS matrix v1 validation rules (see IFRC Docs/fdrs-automatic-validation-checks-spec.md).
"""

from __future__ import annotations

from app.models.validation import CountryAttribute, CountryYearReference, ValidationKpiCheckType, ValidationThreshold
from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.helpers import is_reported_value, numeric_value, parse_period_year
from app.services.validation.fdrs_matrix.history import (
    CHECK_TYPE_3YEAR_AVG,
    CHECK_TYPE_PAST_YEAR,
    DEATH_KPI_CODES,
    baseline_value,
    threshold_exceeded,
    ytd_pct,
)
from app.services.validation.types import CheckResult

NON_ZERO_KPI_CODES = frozenset({
    "KPI_GB",
    "KPI_PStaff",
    "KPI_PeopleVol",
    "KPI_noLocalUnits",
    "KPI_noBranches",
    "KPI_expenditureLC_CHF",
    "KPI_IncomeLC_CHF",
})

HEALTH_SUB_KPI_CODES = frozenset({
    "KPI_TrainFA",
    "KPI_DonBlood",
    "KPI_ReachHI",
    "KPI_ReachHPM",
})

THEMATIC_REACH_FOR_TYPEOF = frozenset({
    "KPI_ReachDRR",
    "KPI_ReachS",
    "KPI_ReachL",
    "KPI_ReachH",
    "KPI_ReachHPM",
    "KPI_ReachHI",
    "KPI_ReachWASH",
    "KPI_ReachM",
    "KPI_Climate",
    "KPI_ClimateHeat",
    "KPI_ReachCTP",
    "KPI_ReachSI",
    "KPI_ReachRCRCEd",
})


def run_fdrs_matrix_rules(ctx) -> list[CheckResult]:
    """Run all FDRS matrix rules against a ValidationContext."""
    results: list[CheckResult] = []
    year = parse_period_year(ctx.period_name)
    country_id = ctx.country_id

    for kpi_code, (entry, item) in ctx.kpi_data.items():
        if kpi_code in DEATH_KPI_CODES:
            nv = numeric_value(entry)
            if kpi_code == "KPI_noVolDeathsDuty_Tot" and nv is not None and nv >= 1:
                results.append(
                    CheckResult(
                        rule_code="volunteer_deaths",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="info",
                        kpi_code=kpi_code,
                        context={"deaths": nv},
                    )
                )
            if kpi_code == "KPI_PStaffDeathsDuty_Tot" and nv is not None and nv >= 1:
                results.append(
                    CheckResult(
                        rule_code="staff_deaths",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="info",
                        kpi_code=kpi_code,
                        context={"deaths": nv},
                    )
                )

        fired_indicator_not_reported = False
        if kpi_code in NON_ZERO_KPI_CODES:
            if not is_reported_value(entry):
                fired_indicator_not_reported = True
                results.append(
                    CheckResult(
                        rule_code="indicator_not_reported",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="warning",
                        kpi_code=kpi_code,
                    )
                )

        if year and country_id and kpi_code not in DEATH_KPI_CODES:
            check_row = ValidationKpiCheckType.query.filter_by(
                kpi_code=kpi_code, template_id=ctx.template_id
            ).first()
            thresh_row = ValidationThreshold.query.filter_by(
                country_id=country_id, kpi_code=kpi_code, template_id=ctx.template_id
            ).first()
            threshold = thresh_row.threshold_fraction if thresh_row else None
            current = numeric_value(entry)
            hist = ctx.history_by_kpi.get(kpi_code, {})
            if check_row and threshold is not None:
                bl = baseline_value(hist, year, check_row.check_type)
                ytd = ytd_pct(current, bl)
                if threshold_exceeded(ytd, threshold):
                    rule = (
                        "past_year_threshold"
                        if check_row.check_type == CHECK_TYPE_PAST_YEAR
                        else "past_3years_avg"
                    )
                    results.append(
                        CheckResult(
                            rule_code=rule,
                            form_item_id=item.id if item else None,
                            fired=True,
                            severity="warning",
                            kpi_code=kpi_code,
                            context={"ytd_pct": ytd, "threshold": threshold, "current": current, "baseline": bl},
                        )
                    )

        prior = ctx.history_by_kpi.get(kpi_code, {}).get((year - 1) if year else 0)
        if year and prior and prior != 0 and not is_reported_value(entry) and not fired_indicator_not_reported:
            results.append(
                CheckResult(
                    rule_code="not_reported",
                    form_item_id=item.id if item else None,
                    fired=True,
                    severity="warning",
                    kpi_code=kpi_code,
                    context={"prior_year": year - 1, "prior_value": prior},
                )
            )

    branches = numeric_value(ctx.kpi_data.get("KPI_noBranches", (None, None))[0])
    units = numeric_value(ctx.kpi_data.get("KPI_noLocalUnits", (None, None))[0])
    if branches is not None and units is not None and branches > units:
        item = ctx.kpi_data.get("KPI_noBranches", (None, None))[1]
        results.append(
            CheckResult(
                rule_code="branches_higher_units",
                form_item_id=item.id if item else None,
                fired=True,
                severity="warning",
                context={"branches": branches, "local_units": units},
            )
        )

    health_total = numeric_value(ctx.kpi_data.get("KPI_ReachH", (None, None))[0])
    if health_total is not None:
        for code in HEALTH_SUB_KPI_CODES:
            sub = numeric_value(ctx.kpi_data.get(code, (None, None))[0])
            if sub is not None and sub > health_total:
                item = ctx.kpi_data.get(code, (None, None))[1]
                results.append(
                    CheckResult(
                        rule_code="higher_health",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="warning",
                        kpi_code=code,
                        context={"sub_value": sub, "health_total": health_total},
                    )
                )

    if year and country_id:
        cyr = CountryYearReference.query.filter_by(country_id=country_id, year=year).first()
        population = cyr.world_bank_population if cyr else None
        if population:
            for code in cat.REACH_KPI_CODES:
                entry, item = ctx.kpi_data.get(code, (None, None))
                nv = numeric_value(entry)
                if nv is not None:
                    if nv >= population:
                        results.append(
                            CheckResult(
                                rule_code="higher_than_pop",
                                form_item_id=item.id if item else None,
                                fired=True,
                                severity="error",
                                kpi_code=code,
                                context={"value": nv, "population": population},
                            )
                        )
                    elif nv / population >= 0.30:
                        results.append(
                            CheckResult(
                                rule_code="significant_pop",
                                form_item_id=item.id if item else None,
                                fired=True,
                                severity="warning",
                                kpi_code=code,
                                context={"value": nv, "population": population, "ratio": nv / population},
                            )
                        )

    drer = numeric_value(ctx.kpi_data.get("KPI_ReachDRER", (None, None))[0])
    ltspd = numeric_value(ctx.kpi_data.get("KPI_ReachLTSPD", (None, None))[0])
    if (drer is None or drer == 0) and (ltspd is None or ltspd == 0):
        reported_programmes = []
        for code in THEMATIC_REACH_FOR_TYPEOF:
            nv = numeric_value(ctx.kpi_data.get(code, (None, None))[0])
            if nv is not None and nv > 0:
                reported_programmes.append(code)
        if reported_programmes:
            item = ctx.kpi_data.get("KPI_ReachDRER", (None, None))[1]
            results.append(
                CheckResult(
                    rule_code="typeofprograms",
                    form_item_id=item.id if item else None,
                    fired=True,
                    severity="warning",
                    context={"programmes": reported_programmes},
                )
            )

    if country_id:
        attr = CountryAttribute.query.filter_by(country_id=country_id).first()
        if attr and attr.grbmp:
            migration = numeric_value(ctx.kpi_data.get("KPI_ReachM", (None, None))[0])
            if migration is None or migration == 0:
                item = ctx.kpi_data.get("KPI_ReachM", (None, None))[1]
                results.append(
                    CheckResult(
                        rule_code="grbmp",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="warning",
                    )
                )

    if year and country_id:
        cyr = CountryYearReference.query.filter_by(country_id=country_id, year=year).first()
        awsd = cyr.awsd_deaths_on_duty if cyr else None
        if awsd is not None and awsd > 0:
            vol_deaths = numeric_value(ctx.kpi_data.get("KPI_noVolDeathsDuty_Tot", (None, None))[0])
            staff_deaths = numeric_value(ctx.kpi_data.get("KPI_PStaffDeathsDuty_Tot", (None, None))[0])
            reported = (vol_deaths or 0) + (staff_deaths or 0)
            if reported != awsd:
                item = ctx.kpi_data.get("KPI_noVolDeathsDuty_Tot", (None, None))[1]
                results.append(
                    CheckResult(
                        rule_code="awsd_check",
                        form_item_id=item.id if item else None,
                        fired=True,
                        severity="warning",
                        context={"awsd_deaths": awsd, "reported_deaths": reported},
                    )
                )

    fiscal_entry, fiscal_item = ctx.kpi_data.get("KPI_FiscalYearEnd", (None, None))
    fiscal_days = numeric_value(fiscal_entry)
    if fiscal_days is not None and fiscal_days > 365:
        results.append(
            CheckResult(
                rule_code="fiscal_year",
                form_item_id=fiscal_item.id if fiscal_item else None,
                fired=True,
                severity="warning",
                context={"fiscal_days": fiscal_days},
            )
        )

    from app.models import FormItem, SubmittedDocument

    for doc_rule, doc_label in (("missing_ar", "Annual Report"), ("missing_sp", "Audited Financial Statement")):
        doc_item = (
            FormItem.query.filter(
                FormItem.template_id == ctx.template_id,
                FormItem.item_type == "document_field",
                FormItem.archived == False,
                FormItem.label.ilike(f"%{doc_label}%"),
            )
            .first()
        )
        if doc_item:
            has_doc = (
                SubmittedDocument.query.filter_by(
                    assignment_entity_status_id=ctx.aes.id,
                    form_item_id=doc_item.id,
                ).count()
                > 0
            )
            if not has_doc:
                results.append(
                    CheckResult(
                        rule_code=doc_rule,
                        form_item_id=doc_item.id,
                        fired=True,
                        severity="warning",
                        context={"document_type": doc_label},
                    )
                )

    if year and country_id:
        ind_values: list[float] = []
        for code in cat.REACH_KPI_CODES:
            entry, _ = ctx.kpi_data.get(code, (None, None))
            if entry and entry.disagg_data:
                values = entry.disagg_data.get("values", {}) or {}
                direct = values.get("direct", values) if isinstance(values, dict) else {}
                if isinstance(direct, dict):
                    ind_val = direct.get("_I") or direct.get("indigenous")
                    try:
                        if ind_val is not None and float(ind_val) > 0:
                            ind_values.append(float(ind_val))
                    except (TypeError, ValueError):
                        pass
        if len(ind_values) >= 2:
            spread = max(ind_values) - min(ind_values)
            avg = sum(ind_values) / len(ind_values)
            if avg > 0 and spread / avg >= 0.5:
                results.append(
                    CheckResult(
                        rule_code="similar_ind_reach",
                        form_item_id=None,
                        fired=True,
                        severity="info",
                        context={"spread_ratio": spread / avg, "programme_count": len(ind_values)},
                    )
                )

    return results
