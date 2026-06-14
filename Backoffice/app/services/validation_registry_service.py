"""Admin registry service — thresholds, KPI check types, and question templates."""

from __future__ import annotations

from typing import Any

from app import db
from app.models import Country
from app.models.validation import ValidationKpiCheckType, ValidationQuestionTemplate, ValidationThreshold
from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.validation.fdrs_matrix.history import CHECK_TYPE_3YEAR_AVG, CHECK_TYPE_PAST_YEAR
from app.services.validation.rule_registry import list_registered_rule_packs, list_rule_definitions
from app.utils.data_quality_constants import REGISTERED_RULE_PACKS


CHECK_TYPE_OPTIONS = (
    {"value": CHECK_TYPE_PAST_YEAR, "label": "Threshold over the past year"},
    {"value": CHECK_TYPE_3YEAR_AVG, "label": "Threshold over the average of the last 3 years"},
)

_THRESHOLD_KPI_CODES = sorted(
    set(cat.GOVERNANCE_KPI_CODES)
    | set(cat.REACH_KPI_CODES)
    | {cat.FINANCE_TOTAL_INCOME, cat.FINANCE_TOTAL_EXPENDITURE}
)


def registry_bootstrap() -> dict[str, Any]:
    return {
        "rule_packs": list_registered_rule_packs(),
        "check_type_options": list(CHECK_TYPE_OPTIONS),
        "kpi_codes": _THRESHOLD_KPI_CODES,
    }


def list_threshold_rows(*, template_id: int | None = None) -> list[dict[str, Any]]:
    query = ValidationThreshold.query
    if template_id is not None:
        query = query.filter_by(template_id=template_id)
    rows = query.order_by(ValidationThreshold.kpi_code, ValidationThreshold.country_id).all()
    country_names = {
        c.id: c.name
        for c in Country.query.filter(Country.id.in_({r.country_id for r in rows})).all()
    } if rows else {}
    return [
        {
            "id": row.id,
            "country_id": row.country_id,
            "country_name": country_names.get(row.country_id, f"Country {row.country_id}"),
            "kpi_code": row.kpi_code,
            "threshold_fraction": row.threshold_fraction,
            "threshold_percent": round(row.threshold_fraction * 100, 4),
            "template_id": row.template_id,
        }
        for row in rows
    ]


def upsert_threshold(
    *,
    country_id: int,
    kpi_code: str,
    threshold_fraction: float,
    template_id: int | None,
    row_id: int | None = None,
) -> dict[str, Any]:
    kpi_code = (kpi_code or "").strip()
    if not kpi_code:
        raise ValueError("kpi_code is required.")
    if country_id is None:
        raise ValueError("country_id is required.")
    if threshold_fraction < 0:
        raise ValueError("threshold_fraction must be zero or positive.")

    Country.query.get_or_404(country_id)

    row = ValidationThreshold.query.get(row_id) if row_id else None
    if row is None:
        row = ValidationThreshold.query.filter_by(
            country_id=country_id,
            kpi_code=kpi_code,
            template_id=template_id,
        ).first()
    if row is None:
        row = ValidationThreshold(
            country_id=country_id,
            kpi_code=kpi_code,
            threshold_fraction=threshold_fraction,
            template_id=template_id,
        )
        db.session.add(row)
    else:
        row.country_id = country_id
        row.kpi_code = kpi_code
        row.threshold_fraction = threshold_fraction
        row.template_id = template_id

    db.session.commit()
    return _serialize_threshold(row)


def _serialize_threshold(row: ValidationThreshold) -> dict[str, Any]:
    country = Country.query.get(row.country_id)
    return {
        "id": row.id,
        "country_id": row.country_id,
        "country_name": country.name if country else f"Country {row.country_id}",
        "kpi_code": row.kpi_code,
        "threshold_fraction": row.threshold_fraction,
        "threshold_percent": round(row.threshold_fraction * 100, 4),
        "template_id": row.template_id,
    }


def delete_threshold(row_id: int) -> None:
    row = ValidationThreshold.query.get_or_404(row_id)
    db.session.delete(row)
    db.session.commit()


def list_check_type_rows(*, template_id: int | None = None) -> list[dict[str, Any]]:
    query = ValidationKpiCheckType.query
    if template_id is not None:
        query = query.filter_by(template_id=template_id)
    rows = query.order_by(ValidationKpiCheckType.kpi_code).all()
    return [
        {
            "id": row.id,
            "kpi_code": row.kpi_code,
            "check_type": row.check_type,
            "template_id": row.template_id,
        }
        for row in rows
    ]


def upsert_check_type(
    *,
    kpi_code: str,
    check_type: str,
    template_id: int | None,
    row_id: int | None = None,
) -> dict[str, Any]:
    kpi_code = (kpi_code or "").strip()
    if not kpi_code:
        raise ValueError("kpi_code is required.")
    allowed = {opt["value"] for opt in CHECK_TYPE_OPTIONS}
    if check_type not in allowed:
        raise ValueError(f"check_type must be one of: {', '.join(sorted(allowed))}")

    row = ValidationKpiCheckType.query.get(row_id) if row_id else None
    if row is None:
        row = ValidationKpiCheckType.query.filter_by(kpi_code=kpi_code, template_id=template_id).first()
    if row is None:
        row = ValidationKpiCheckType(kpi_code=kpi_code, check_type=check_type, template_id=template_id)
        db.session.add(row)
    else:
        row.kpi_code = kpi_code
        row.check_type = check_type
        row.template_id = template_id

    db.session.commit()
    return {
        "id": row.id,
        "kpi_code": row.kpi_code,
        "check_type": row.check_type,
        "template_id": row.template_id,
    }


def delete_check_type(row_id: int) -> None:
    row = ValidationKpiCheckType.query.get_or_404(row_id)
    db.session.delete(row)
    db.session.commit()


def list_question_template_rows(*, rule_pack: str | None = None, language: str | None = None) -> list[dict[str, Any]]:
    query = ValidationQuestionTemplate.query
    if rule_pack:
        query = query.filter_by(rule_pack=rule_pack)
    if language:
        query = query.filter_by(language=language)
    rows = query.order_by(
        ValidationQuestionTemplate.rule_pack,
        ValidationQuestionTemplate.question_code,
        ValidationQuestionTemplate.language,
    ).all()
    return [
        {
            "id": row.id,
            "question_code": row.question_code,
            "language": row.language,
            "template_text": row.template_text,
            "needs_ending_value": row.needs_ending_value,
            "rule_pack": row.rule_pack,
        }
        for row in rows
    ]


def update_question_template(
    row_id: int,
    *,
    template_text: str,
    needs_ending_value: bool | None = None,
) -> dict[str, Any]:
    row = ValidationQuestionTemplate.query.get_or_404(row_id)
    text = (template_text or "").strip()
    if not text:
        raise ValueError("template_text is required.")
    row.template_text = text
    if needs_ending_value is not None:
        row.needs_ending_value = bool(needs_ending_value)
    db.session.commit()
    return {
        "id": row.id,
        "question_code": row.question_code,
        "language": row.language,
        "template_text": row.template_text,
        "needs_ending_value": row.needs_ending_value,
        "rule_pack": row.rule_pack,
    }


def list_countries_for_picker() -> list[dict[str, Any]]:
    rows = Country.query.order_by(Country.name).all()
    return [{"id": c.id, "name": c.name} for c in rows]


def list_rule_catalog(*, rule_pack: str | None = None) -> list[dict[str, Any]]:
    pack = rule_pack or (REGISTERED_RULE_PACKS[0] if REGISTERED_RULE_PACKS else None)
    return list_rule_definitions(rule_pack=pack)
