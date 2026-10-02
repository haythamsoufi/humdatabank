"""Validation dashboard — country summaries and dry-run indicator previews."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func

from app import db
from app.models import Country, FormTemplate
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.validation import ValidationQuestion
from app.services.data_quality.helpers import numeric_value, parse_period_year
from app.services.data_quality.service import get_rule_pack_for_template
from app.services.forms.reporting_period_service import sort_period_names
from app.services.validation.pack_registry import get_pack
from app.utils.data_quality_constants import RULE_PACK_CORE
from app.services.validation.rule_labels import format_rule_labels
from app.services.validation.types import CheckResult, ValidationEvaluationResult
from .check_service import evaluate_validation_checks, validation_checks_disabled_message

HISTORY_YEARS_LOOKBACK = 3

_QUESTION_STATUS_PRIORITY = {"open": 0, "answered": 1, "waived": 2, "resolved": 3}


def _history_year_columns(current_year: int | None) -> list[int]:
    """Reporting years shown when historical toggle is on (current year and two prior)."""
    if current_year is None:
        return []
    return [current_year - offset for offset in range(HISTORY_YEARS_LOOKBACK)]


def _format_display_number(value: int | float | str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    if num.is_integer():
        return f"{int(num):,}"
    text = f"{num:,}".rstrip("0").rstrip(".")
    return text or "0"


def _historical_values_for_years(
    hist: dict[int, float],
    years: list[int],
    *,
    current_year: int | None = None,
    current_entry=None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for year in years:
        if current_year is not None and year == current_year:
            formatted = _format_value(current_entry)
        elif year in hist:
            formatted = _format_display_number(hist[year])
        else:
            formatted = None
        if formatted is not None:
            result[str(year)] = formatted
    return result


def _templates_with_validation() -> list[FormTemplate]:
    from app.models.forms import FormTemplateVersion

    return (
        FormTemplate.query.join(
            FormTemplateVersion,
            FormTemplate.published_version_id == FormTemplateVersion.id,
        )
        .filter(FormTemplateVersion.enable_data_quality == True)  # noqa: E712
        .order_by(FormTemplate.id)
        .all()
    )


def _upr_dashboard():
    """Load UPR tab helpers after this module is initialized.

    Importing ``plugins.upr`` at module scope pulls admin routes, which import
    this module again before its functions exist.
    """
    from plugins.upr.catalog import (
        UPR_LEGACY_REPORTING_TEMPLATE_ID,
        UPR_REPORTING_TEMPLATE_ID,
        UPR_VALIDATION_TEMPLATE_IDS,
    )
    from plugins.upr.validation_dashboard import upr_display_name, upr_product_tab

    return {
        "legacy_id": UPR_LEGACY_REPORTING_TEMPLATE_ID,
        "reporting_id": UPR_REPORTING_TEMPLATE_ID,
        "validation_ids": UPR_VALIDATION_TEMPLATE_IDS,
        "display_name": upr_display_name,
        "product_tab": upr_product_tab,
    }


_PERIOD_YEAR_RE = re.compile(r"20\d{2}")


def _registered_pack_code(template: FormTemplate):
    """Plugin pack for this template, or the general checks pack when data quality is on.

    Test doubles without a real published-version flag are kept so callers that
    already selected templates are not filtered out. An empty string means the
    template is left off the dashboard.
    """
    version = getattr(template, "published_version", None)
    enabled = getattr(version, "enable_data_quality", None)
    if not isinstance(enabled, bool):
        return None
    if not enabled:
        return ""
    pack = get_rule_pack_for_template(template)
    if isinstance(pack, str) and pack != RULE_PACK_CORE and get_pack(pack):
        return pack
    return RULE_PACK_CORE


def _validation_templates_by_id() -> dict[int, FormTemplate]:
    """DQ-enabled templates. Legacy UPR 25 drops when 33 is present."""
    by_id = {}
    for template in _templates_with_validation():
        pack_code = _registered_pack_code(template)
        if pack_code == "":
            continue
        by_id[template.id] = template
    upr = _upr_dashboard()
    if upr["reporting_id"] in by_id:
        by_id.pop(upr["legacy_id"], None)
    return by_id


def indicator_codes_for_template_ids(template_ids: list[int]) -> dict[int, list[str]]:
    """Indicator codes on each template's published items, for the rules screen."""
    from sqlalchemy.orm import joinedload

    from app.models import FormItem
    from app.services.data_quality.helpers import indicator_storage_key

    ids = [template_id for template_id in template_ids if isinstance(template_id, int)]
    if not ids:
        return {}
    templates = FormTemplate.query.filter(FormTemplate.id.in_(ids)).all()
    version_by_template = {template.id: template.published_version_id for template in templates}
    items = (
        FormItem.query.filter(
            FormItem.template_id.in_(ids),
            FormItem.archived == False,  # noqa: E712
            FormItem.indicator_bank_id.isnot(None),
        )
        .options(joinedload(FormItem.indicator_bank))
        .all()
    )
    found: dict[int, list[str]] = {template_id: [] for template_id in ids}
    seen: dict[int, set[str]] = {template_id: set() for template_id in ids}
    for item in items:
        version_id = version_by_template.get(item.template_id)
        if version_id and item.version_id not in (version_id, None):
            continue
        key = indicator_storage_key(getattr(item, "indicator_bank", None))
        bucket = seen.setdefault(item.template_id, set())
        if not key or key in bucket:
            continue
        bucket.add(key)
        found.setdefault(item.template_id, []).append(key)
    for codes in found.values():
        codes.sort()
    return found


def template_options() -> list[dict[str, Any]]:
    """Flat template list for selects (questions/rules) and API consumers."""
    by_id = _validation_templates_by_id()
    upr = _upr_dashboard()
    options: list[dict[str, Any]] = []
    for tid in sorted(by_id):
        tmpl = by_id[tid]
        options.append({
            "id": tmpl.id,
            "name": upr["display_name"](tmpl.id, tmpl.name),
            "rule_pack": _registered_pack_code(tmpl) or None,
        })
    return options


def template_tab_options() -> list[dict[str, Any]]:
    """Product tabs for the validation dashboard (UPR grouped as one tab)."""
    by_id = _validation_templates_by_id()
    upr = _upr_dashboard()
    tabs: list[dict[str, Any]] = []
    for tid in sorted(by_id):
        if tid in upr["validation_ids"]:
            continue
        tmpl = by_id[tid]
        tabs.append({"id": tmpl.id, "name": tmpl.name, "children": None})

    upr_tab = upr["product_tab"](by_id)
    if upr_tab:
        tabs.append(upr_tab)
    return tabs


def global_periods_for_template(template_id: int) -> list[str]:
    rows = (
        db.session.query(AssignedForm.period_name)
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.period_name.isnot(None),
        )
        .distinct()
        .all()
    )
    periods = [r[0] for r in rows if r[0]]
    return sort_period_names(periods)


def _period_matches_year(period_name: str | None, requested: str) -> bool:
    target = parse_period_year(requested)
    if target is None or not period_name:
        return False
    return any(int(year) == target for year in _PERIOD_YEAR_RE.findall(str(period_name)))


def _pick_assignment_row(rows: list[tuple], requested: str):
    """Choose (aes, period_name) for one country. Exact period wins, then year, then highest assignment id."""
    exact = [row for row in rows if row[1] == requested]
    pool = exact or [row for row in rows if _period_matches_year(row[1], requested)]
    if not pool:
        return None
    aes, period, assignment_id = max(pool, key=lambda row: row[2] or 0)
    return aes, period


def list_countries_for_period(template_id: int, period_name: str) -> list[dict[str, Any]]:
    """Countries with an assignment for template+period, plus persisted question counts."""
    assignment_rows = (
        db.session.query(
            Country.id,
            Country.name,
            AssignmentEntityStatus,
            AssignedForm.period_name,
            AssignedForm.id,
        )
        .join(AssignmentEntityStatus, AssignmentEntityStatus.entity_id == Country.id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
        )
        .all()
    )

    grouped: dict[int, dict[str, Any]] = {}
    for country_id, country_name, aes, period, assignment_id in assignment_rows:
        bucket = grouped.setdefault(country_id, {"name": country_name, "rows": []})
        bucket["rows"].append((aes, period, assignment_id))

    resolved: dict[int, tuple[str, str]] = {}
    for country_id, info in grouped.items():
        picked = _pick_assignment_row(info["rows"], period_name)
        if picked:
            _aes, resolved_period = picked
            resolved[country_id] = (info["name"], resolved_period)

    if not resolved:
        return []

    counts = (
        db.session.query(
            ValidationQuestion.entity_id,
            ValidationQuestion.period_name,
            ValidationQuestion.status,
            func.count(ValidationQuestion.id),
        )
        .filter(
            ValidationQuestion.template_id == template_id,
            ValidationQuestion.entity_type == "country",
            ValidationQuestion.entity_id.in_(resolved.keys()),
        )
        .group_by(
            ValidationQuestion.entity_id,
            ValidationQuestion.period_name,
            ValidationQuestion.status,
        )
        .all()
    )
    count_map: dict[tuple[int, str], dict[str, int]] = {}
    for entity_id, pn, status, cnt in counts:
        count_map.setdefault((entity_id, pn), {})[status] = cnt

    rows = []
    for country_id, (country_name, resolved_period) in resolved.items():
        status_counts = count_map.get((country_id, resolved_period), {})
        rows.append(
            {
                "country_id": country_id,
                "country_name": country_name,
                "period_name": resolved_period,
                "has_assignment": True,
                "open_questions": status_counts.get("open", 0),
                "answered_questions": status_counts.get("answered", 0),
                "waived_questions": status_counts.get("waived", 0),
                "resolved_questions": status_counts.get("resolved", 0),
                "total_questions": sum(status_counts.values()),
            }
        )
    return sorted(rows, key=lambda r: r["country_name"])


def _format_value(entry) -> str | None:
    if entry is None:
        return None
    nv = numeric_value(entry)
    if nv is not None:
        return _format_display_number(nv)
    tv = getattr(entry, "total_value", None)
    if tv not in (None, ""):
        return _format_display_number(tv)
    return None


def _persisted_questions_map(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
) -> dict[tuple[str, int | None], ValidationQuestion]:
    """Best question per (rule_code, form_item_id) for dashboard indicator rows."""
    rows = ValidationQuestion.query.filter_by(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=period_name,
    ).all()
    chosen: dict[tuple[str, int | None], ValidationQuestion] = {}
    for question in rows:
        key = (question.rule_code, question.form_item_id)
        existing = chosen.get(key)
        if existing is None or _question_preferred_over(existing, question):
            chosen[key] = question
    return chosen


def _question_preferred_over(current: ValidationQuestion, candidate: ValidationQuestion) -> bool:
    cur_rank = _QUESTION_STATUS_PRIORITY.get(current.status, 99)
    cand_rank = _QUESTION_STATUS_PRIORITY.get(candidate.status, 99)
    if cand_rank != cur_rank:
        return cand_rank < cur_rank
    cur_ts = current.asked_at.timestamp() if current.asked_at else 0
    cand_ts = candidate.asked_at.timestamp() if candidate.asked_at else 0
    return cand_ts > cur_ts


def _pick_question_for_flags(
    flags: list[CheckResult],
    form_item_id: int | None,
    questions_by_key: dict[tuple[str, int | None], ValidationQuestion],
) -> ValidationQuestion | None:
    for flag in flags:
        question = questions_by_key.get((flag.rule_code, form_item_id))
        if question is not None:
            return question
    if flags:
        return questions_by_key.get((flags[0].rule_code, form_item_id))
    return None


def _question_row_fields(question: ValidationQuestion | None) -> dict[str, Any]:
    if question is None:
        return {
            "question_id": None,
            "question_status": None,
            "question_sent": False,
            "sent_at": None,
            "answered_at": None,
            "has_answer": False,
            "answer_preview": None,
        }
    answer = question.answer_text
    preview = None
    if answer:
        preview = answer if len(answer) <= 120 else answer[:117] + "…"
    return {
        "question_id": question.id,
        "question_status": question.status,
        "question_sent": question.sent_at is not None,
        "sent_at": question.sent_at.isoformat() if question.sent_at else None,
        "answered_at": question.answered_at.isoformat() if question.answered_at else None,
        "has_answer": bool(answer),
        "answer_preview": preview,
    }


def build_indicator_preview_rows(
    evaluation: ValidationEvaluationResult,
    questions_by_key: dict[tuple[str, int | None], ValidationQuestion] | None = None,
) -> list[dict[str, Any]]:
    fired_by_item: dict[int | None, list[CheckResult]] = {}
    country_flags: list[CheckResult] = []
    for result in evaluation.check_results:
        if not result.fired:
            continue
        if result.form_item_id is None:
            country_flags.append(result)
        else:
            fired_by_item.setdefault(result.form_item_id, []).append(result)

    draft_by_key = {(d.rule_code, d.form_item_id): d for d in evaluation.drafts}
    current_year = parse_period_year(evaluation.resolved_period)
    questions_by_key = questions_by_key or {}

    rows: list[dict[str, Any]] = []
    for kpi_code, (entry, item) in sorted(evaluation.kpi_data.items()):
        form_item_id = item.id if item else None
        flags = fired_by_item.get(form_item_id, [])
        primary = flags[0] if flags else None
        draft = draft_by_key.get((primary.rule_code, form_item_id)) if primary else None
        hist = evaluation.history_by_kpi.get(kpi_code, {})
        history_years = _history_year_columns(current_year)
        historical_values = _historical_values_for_years(
            hist,
            history_years,
            current_year=current_year,
            current_entry=entry,
        )
        prior_value = hist.get(current_year - 1) if current_year is not None else None
        question = _pick_question_for_flags(flags, form_item_id, questions_by_key)
        rows.append(
            {
                "row_type": "indicator",
                "kpi_code": kpi_code,
                "form_item_id": form_item_id,
                "indicator_label": (item.label if item else None) or kpi_code,
                "current_value": _format_value(entry),
                "prior_value": _format_display_number(prior_value),
                "historical_values": historical_values,
                "flagged": bool(flags),
                "rule_code": primary.rule_code if primary else None,
                "severity": primary.severity if primary else None,
                "triggered_rules": [r.rule_code for r in flags],
                "triggered_rule_labels": format_rule_labels([r.rule_code for r in flags]),
                "context": primary.context if primary else None,
                "question_preview": draft.question_text if draft else None,
                **_question_row_fields(question),
            }
        )

    for result in country_flags:
        draft = draft_by_key.get((result.rule_code, None))
        question = questions_by_key.get((result.rule_code, None))
        rows.append(
            {
                "row_type": "country",
                "kpi_code": None,
                "form_item_id": None,
                "indicator_label": result.rule_code.replace("_", " ").title(),
                "current_value": None,
                "flagged": True,
                "rule_code": result.rule_code,
                "severity": result.severity,
                "triggered_rules": [result.rule_code],
                "triggered_rule_labels": format_rule_labels([result.rule_code]),
                "context": result.context,
                "question_preview": draft.question_text if draft else None,
                **_question_row_fields(question),
            }
        )

    rows.sort(key=lambda r: (0 if r["flagged"] else 1, r.get("indicator_label") or ""))
    return rows


def preview_country_validation(
    template_id: int,
    period_name: str,
    country_id: int,
    *,
    language: str = "en",
) -> dict[str, Any]:
    evaluation = evaluate_validation_checks(
        template_id,
        "country",
        country_id,
        period_name,
        language=language,
        require_rule_pack=False,
    )
    questions_by_key = _persisted_questions_map(
        template_id,
        "country",
        country_id,
        evaluation.resolved_period,
    )
    indicator_rows = build_indicator_preview_rows(evaluation, questions_by_key)
    flag_count = sum(1 for r in indicator_rows if r["flagged"])
    severity_counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for row in indicator_rows:
        if row["flagged"] and row.get("severity"):
            sev = row["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

    current_year = parse_period_year(evaluation.resolved_period)
    history_years = _history_year_columns(current_year)
    validation_enabled = bool(evaluation.rule_pack)

    return {
        "country_id": country_id,
        "period_name": evaluation.resolved_period,
        "rule_pack": evaluation.rule_pack or None,
        "validation_enabled": validation_enabled,
        "message": None if validation_enabled else validation_checks_disabled_message(template_id),
        "current_year": current_year,
        "flag_count": flag_count,
        "clean_count": len(indicator_rows) - flag_count,
        "indicator_count": len(indicator_rows),
        "severity_counts": severity_counts,
        "history_years": history_years,
        "draft_count": len(evaluation.drafts),
        "indicators": indicator_rows,
    }


def summarize_period(template_id: int, period_name: str) -> dict[str, Any]:
    """Aggregate question counts across countries for dashboard KPIs and charts."""
    countries = list_countries_for_period(template_id, period_name)
    totals = {
        "country_count": len(countries),
        "open_questions": sum(c["open_questions"] for c in countries),
        "answered_questions": sum(c["answered_questions"] for c in countries),
        "waived_questions": sum(c["waived_questions"] for c in countries),
        "resolved_questions": sum(c["resolved_questions"] for c in countries),
        "total_questions": sum(c["total_questions"] for c in countries),
        "countries_with_open": sum(1 for c in countries if c["open_questions"] > 0),
    }
    return {"countries": countries, "totals": totals}
