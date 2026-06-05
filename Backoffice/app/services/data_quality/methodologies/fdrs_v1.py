"""
FDRS v1 Quality of Data methodology (IFRC PDF).

Overall = 0.2*docs + 0.3*reporting + 0.3*disagg + 0.1*timeliness + 0.1*validation
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app import db
from app.models import FormData, FormItem, FormSection, SubmittedDocument
from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.helpers import (
    compute_income_sources_ratio,
    fdrs_compliance_doc_label_matches,
    get_assignment_aes,
    is_reported_value,
    load_form_data_by_kpi,
    numeric_value,
    parse_disagg_sex_age_totals,
    parse_period_year,
    section_name_matches,
    validation_question_counts,
)
from app.services.data_quality.types import DataQualityResult
from app.utils.data_quality_constants import METHODOLOGY_FDRS_V1


class FdrsV1Methodology:
    code = METHODOLOGY_FDRS_V1

    def compute(
        self,
        *,
        template_id: int,
        entity_type: str,
        entity_id: int,
        period_name: str,
        assignment_entity_status_id: int | None = None,
        include_trend: bool = True,
    ) -> DataQualityResult:
        warnings: list[str] = []
        aes = None
        if assignment_entity_status_id:
            from app.models.assignments import AssignmentEntityStatus

            aes = AssignmentEntityStatus.query.get(assignment_entity_status_id)
        if aes is None:
            aes = get_assignment_aes(template_id, entity_type, entity_id, period_name)

        if aes is None:
            return DataQualityResult(
                overall_pct=0.0,
                methodology=self.code,
                template_id=template_id,
                entity_type=entity_type,
                entity_id=entity_id,
                period_name=period_name,
                warnings=["No assignment found for this entity and period."],
            )

        assigned_form = aes.assigned_form
        template = assigned_form.template if assigned_form else None
        version_id = template.published_version_id if template else None

        kpi_data = load_form_data_by_kpi(aes.id, template_id, version_id)

        docs_score, docs_detail = self._documents_score(aes.id, template_id)
        reporting_score, reporting_detail, reporting_components = self._reporting_score(
            kpi_data,
            aes_id=aes.id,
            template_id=template_id,
            version_id=version_id,
        )
        disagg_score, disagg_detail, disagg_components = self._disaggregation_score(
            kpi_data, warnings
        )
        timeliness_score, timeliness_detail = self._timeliness_score(
            aes, template_id, version_id, period_name
        )
        val_summary = validation_question_counts(template_id, entity_type, entity_id, period_name)
        if val_summary["asked"] == 0:
            validation_score = 1.0
        else:
            validation_score = val_summary["answered"] / val_summary["asked"]

        overall = (
            cat.WEIGHT_DOCUMENTS * docs_score
            + cat.WEIGHT_REPORTING * reporting_score
            + cat.WEIGHT_DISAGGREGATION * disagg_score
            + cat.WEIGHT_TIMELINESS * timeliness_score
            + cat.WEIGHT_VALIDATION * validation_score
        ) * 100.0

        trend = (
            self._trend(template_id, entity_type, entity_id, period_name, aes.id)
            if include_trend
            else []
        )
        return DataQualityResult(
            overall_pct=overall,
            methodology=self.code,
            template_id=template_id,
            entity_type=entity_type,
            entity_id=entity_id,
            period_name=period_name,
            pillars={
                "documents": round(docs_score * 100, 1),
                "reporting": round(reporting_score * 100, 1),
                "disaggregation": round(disagg_score * 100, 1),
                "timeliness": round(timeliness_score * 100, 1),
                "validation_questions": round(validation_score * 100, 1),
            },
            sub_pillars={
                "documents": docs_detail,
                "reporting": reporting_detail,
                "disaggregation": disagg_detail,
                "timeliness": timeliness_detail,
            },
            component_details={
                "reporting": reporting_components,
                "disaggregation": disagg_components,
            },
            trend=trend,
            warnings=warnings,
            validation_summary=val_summary,
        )

    def catalog_warnings(self, template_id: int) -> list[str]:
        return []

    def _documents_score(self, aes_id: int, template_id: int) -> tuple[float, dict]:
        doc_items = (
            FormItem.query.filter(
                FormItem.template_id == template_id,
                FormItem.item_type == "document_field",
                FormItem.archived == False,
            ).all()
        )
        found_types: set[str] = set()
        for item in doc_items:
            label = (item.label or "").lower()
            for doc_type in cat.COMPLIANCE_DOC_TYPES:
                if fdrs_compliance_doc_label_matches(item.label, doc_type):
                    has_doc = (
                        SubmittedDocument.query.filter(
                            SubmittedDocument.assignment_entity_status_id == aes_id,
                            SubmittedDocument.form_item_id == item.id,
                        ).count()
                        > 0
                    )
                    if has_doc:
                        found_types.add(doc_type)
                    break

        ar = 1.0 if "Annual Report" in found_types else 0.0
        afs = 1.0 if "Audited Financial Statement" in found_types else 0.0
        score = (ar + afs) / 2.0
        return score, {"annual_report": ar, "audited_financial_statement": afs}

    def _reporting_score(
        self,
        kpi_data: dict,
        *,
        aes_id: int,
        template_id: int,
        version_id: int | None,
    ) -> tuple[float, dict, dict]:
        gov_reported = sum(
            1 for code in cat.GOVERNANCE_KPI_CODES if is_reported_value(kpi_data.get(code, (None, None))[0])
        )
        gov_score = gov_reported / len(cat.GOVERNANCE_KPI_CODES) if cat.GOVERNANCE_KPI_CODES else 0.0

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

        finance_score = income_reported * 0.35 + expend_reported * 0.35 + income_sources_ratio * 0.30

        reported_reach = sum(
            1 for code in cat.REACH_KPI_CODES if is_reported_value(kpi_data.get(code, (None, None))[0])
        )
        reach_score = reported_reach / len(cat.REACH_KPI_CODES) if cat.REACH_KPI_CODES else 0.0

        reporting_score = gov_score * 0.33 + finance_score * 0.33 + reach_score * 0.33
        return reporting_score, {
            "governance_structure": round(gov_score, 3),
            "finance_partnership": round(finance_score, 3),
            "people_reached": round(reach_score, 3),
        }, {
            "finance_partnership": {
                "reported_income": income_reported,
                "reported_expenditure": expend_reported,
                "income_sources": round(income_sources_ratio, 3),
            }
        }

    def _disaggregation_score(
        self, kpi_data: dict, warnings: list[str]
    ) -> tuple[float, dict, dict]:
        total_people = 0.0
        sex_disagg = 0.0
        age_disagg = 0.0
        ddd_answered = 0
        ddd_disagg = 0
        wgq_answered = 0
        wgq_followed = 0

        for code in cat.DISAGG_INDICATOR_KPI_CODES:
            entry, _ = kpi_data.get(code, (None, None))
            nv = numeric_value(entry)
            if nv is None or nv <= 0:
                continue
            total_people += nv
            if entry and entry.disagg_data:
                sex_part, age_part = parse_disagg_sex_age_totals(entry.disagg_data)
                sex_disagg += sex_part
                age_disagg += age_part

            disability_handled = False
            if entry and isinstance(getattr(entry, "disagg_data", None), dict):
                disagg_values = entry.disagg_data.get("values") or {}
                if isinstance(disagg_values, dict):
                    disability_meta = disagg_values.get("disability")
                    if isinstance(disability_meta, dict) and "disaggregated_by_disability" in disability_meta:
                        ddd_answered += 1
                        if disability_meta.get("disaggregated_by_disability"):
                            ddd_disagg += 1
                            wgq_answered += 1
                            if disability_meta.get("washington_group_compliant"):
                                wgq_followed += 1
                        disability_handled = True

            if not disability_handled:
                ddd_code = f"{code}_ddd" if not code.endswith("_ddd") else code
                wgq_code = f"{code}_wgq" if not code.endswith("_wgq") else code
                for suffix, answered_attr, disagg_attr in (
                    ("_ddd", "ddd", "ddd_disagg"),
                    ("_wgq", "wgq", "wgq_followed"),
                ):
                    alt_code = code + suffix if not code.endswith(suffix) else code
                    d_entry, _ = kpi_data.get(alt_code, (None, None))
                    if d_entry is not None:
                        if suffix == "_ddd":
                            ddd_answered += 1
                            if is_reported_value(d_entry):
                                ddd_disagg += 1
                        else:
                            wgq_answered += 1
                            if is_reported_value(d_entry):
                                wgq_followed += 1

        if total_people <= 0:
            warnings.append("No people-count indicators with values for disaggregation scoring.")
            return 0.0, {"sex": 0, "age": 0, "disability": 0}, {
                "disability": {
                    "disaggregated_disability": 0.0,
                    "washington_group_questions": 0.0,
                }
            }

        sex_score = min(1.0, sex_disagg / total_people)
        age_score = min(1.0, age_disagg / total_people)
        ddd_ratio = ddd_disagg / ddd_answered if ddd_answered else 0.0
        wgq_ratio = wgq_followed / wgq_answered if wgq_answered else 0.0
        disability_score = ddd_ratio * 0.8 + wgq_ratio * 0.2
        if ddd_answered == 0:
            warnings.append("disability_data_gap: no _ddd/_wgq KPI data in form_data.")

        disagg_score = sex_score * 0.33 + age_score * 0.33 + disability_score * 0.33
        return disagg_score, {
            "sex": round(sex_score, 3),
            "age": round(age_score, 3),
            "disability": round(disability_score, 3),
        }, {
            "disability": {
                "disaggregated_disability": round(ddd_ratio, 3),
                "washington_group_questions": round(wgq_ratio, 3),
            }
        }

    def _timeliness_score(
        self,
        aes,
        template_id: int,
        version_id: int | None,
        period_name: str,
    ) -> tuple[float, dict]:
        year = parse_period_year(period_name)
        if year is None:
            return 0.0, {"error": "Could not parse reporting year from period."}

        cutoff = datetime(year + 1, cat.TIMELINESS_CUTOFF_MONTH, cat.TIMELINESS_CUTOFF_DAY)
        sections = (
            FormSection.query.filter(
                FormSection.template_id == template_id,
            ).all()
        )
        if version_id:
            sections = [s for s in sections if s.version_id == version_id or s.version_id is None]

        section_ids_by_group: dict[str, list[int]] = {g[0]: [] for g in cat.TIMELINESS_SECTION_GROUPS}
        for section in sections:
            for group_key, keywords in cat.TIMELINESS_SECTION_GROUPS:
                if section_name_matches(section, keywords):
                    section_ids_by_group[group_key].append(section.id)

        groups_with_sections = [k for k, ids in section_ids_by_group.items() if ids]
        group_submitted: dict[str, datetime | None] = {gk: None for gk, _ in cat.TIMELINESS_SECTION_GROUPS}

        if aes.submitted_at and groups_with_sections:
            # Use the assignment submission timestamp — FormData.submitted_at is updated on
            # every edit/import and is not a reliable measure of original timeliness.
            for group_key in groups_with_sections:
                group_submitted[group_key] = aes.submitted_at
        else:
            for group_key, section_ids in section_ids_by_group.items():
                if not section_ids:
                    continue
                item_ids = [
                    i.id
                    for i in FormItem.query.filter(
                        FormItem.section_id.in_(section_ids),
                        FormItem.archived == False,
                    ).all()
                ]
                if not item_ids:
                    continue
                latest = (
                    db.session.query(db.func.max(FormData.submitted_at))
                    .filter(
                        FormData.assignment_entity_status_id == aes.id,
                        FormData.form_item_id.in_(item_ids),
                    )
                    .scalar()
                )
                group_submitted[group_key] = latest

            if aes.submitted_at:
                for key in groups_with_sections:
                    if group_submitted.get(key) is None:
                        group_submitted[key] = aes.submitted_at

        if not groups_with_sections and aes.submitted_at:
            all_on_time = aes.submitted_at <= cutoff
        else:
            all_on_time = bool(groups_with_sections) and all(
                group_submitted.get(k) is not None and group_submitted[k] <= cutoff
                for k in groups_with_sections
            )
        score = 1.0 if all_on_time else 0.0
        return score, {
            "cutoff": cutoff.isoformat(),
            "sections": {k: (v.isoformat() if v else None) for k, v in group_submitted.items()},
        }

    def _trend(
        self,
        template_id: int,
        entity_type: str,
        entity_id: int,
        current_period: str,
        current_aes_id: int,
    ) -> list[dict[str, Any]]:
        from app.models.assignments import AssignmentEntityStatus

        from app.models import AssignedForm

        rows = (
            AssignmentEntityStatus.query.join(
                AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id
            )
            .filter(
                AssignmentEntityStatus.entity_type == entity_type,
                AssignmentEntityStatus.entity_id == entity_id,
                AssignedForm.template_id == template_id,
            )
            .order_by(AssignedForm.period_name)
            .all()
        )
        periods = []
        seen = set()
        for aes in rows:
            pn = aes.assigned_form.period_name if aes.assigned_form else None
            if pn and pn not in seen:
                seen.add(pn)
                periods.append(pn)

        trend = []
        for pn in periods[-5:]:
            result = self.compute(
                template_id=template_id,
                entity_type=entity_type,
                entity_id=entity_id,
                period_name=pn,
                include_trend=False,
            )
            trend.append({
                "period": pn,
                "overall_pct": result.overall_pct,
                "pillars": result.pillars,
            })
        return trend
