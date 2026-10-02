"""
FDRS matrix v1 validation rules (see IFRC Docs/fdrs-automatic-validation-checks-spec.md).
"""

from __future__ import annotations

from app.models.validation import CountryAttribute, CountryYearReference, ValidationKpiCheckType, ValidationThreshold
from plugins.fdrs.data_quality import fdrs_v1_catalog as cat
from plugins.fdrs.data_quality.fdrs_v1_catalog import fdrs_compliance_doc_label_matches
from app.services.data_quality.helpers import is_reported_value, numeric_value, parse_period_year
from plugins.fdrs.validation.fdrs_matrix.history import DEATH_KPI_CODES
from app.services.validation.types import CheckResult

# Core checks own thresholds, check types, and the blank-value helper.
# These names stay on this module so existing rule tests can patch them.
_PATCHABLE = (ValidationKpiCheckType, ValidationThreshold, is_reported_value)

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


def _query_rows(query) -> list:
    """Return query rows. Stubs that only set ``.first()`` still work."""
    rows = query.all()
    if isinstance(rows, list):
        return rows
    one = query.first()
    return [one] if one is not None else []


def _configured_document_type(item) -> str:
    cfg = getattr(item, "config", None)
    if not isinstance(cfg, dict):
        return ""
    raw = cfg.get("document_type")
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def _document_item_for_label(items: list, doc_label: str):
    """Prefer the field's configured document type, then its label."""
    for item in items:
        configured = _configured_document_type(item)
        if configured and (
            configured.lower() == doc_label.lower()
            or fdrs_compliance_doc_label_matches(configured, doc_label)
        ):
            return item
    for item in items:
        label = getattr(item, "label", None)
        if not isinstance(label, str):
            continue
        if label.strip() == doc_label or fdrs_compliance_doc_label_matches(label, doc_label):
            return item
    return None


def run_fdrs_matrix_rules(ctx) -> list[CheckResult]:
    """Run all FDRS matrix rules against a ValidationContext."""
    results: list[CheckResult] = []
    year = parse_period_year(ctx.period_name)
    country_id = ctx.country_id

    country_year = None
    if year and country_id:
        country_year = CountryYearReference.query.filter_by(country_id=country_id, year=year).first()

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

    if year and country_id and country_year and country_year.world_bank_population:
        population = country_year.world_bank_population
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

    if year and country_id and country_year and country_year.awsd_deaths_on_duty:
        awsd = country_year.awsd_deaths_on_duty
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

    document_items = _query_rows(
        FormItem.query.filter(
            FormItem.template_id == ctx.template_id,
            FormItem.item_type == "document_field",
            FormItem.archived == False,
        )
    )
    for doc_rule, doc_label in (("missing_ar", "Annual Report"), ("missing_sp", "Audited Financial Statement")):
        doc_item = _document_item_for_label(document_items, doc_label)
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
                        context={"document_type": _configured_document_type(doc_item) or doc_label},
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
