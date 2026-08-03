"""Generalized form-data aggregation for reports and analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AssignedForm, Country, FormData, FormItem, IndicatorBank
from app.models.assignments import AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue


@dataclass
class AggregationFilters:
    template_ids: list[int] = field(default_factory=list)
    period_names: list[str] = field(default_factory=list)
    country_ids: list[int] = field(default_factory=list)
    assignment_statuses: list[str] = field(default_factory=lambda: ["submitted", "approved"])
    indicator_bank_ids: list[int] = field(default_factory=list)
    include_public_submissions: bool = False


def _period_filter(column, period_names: list[str]):
    if not period_names:
        return True
    clauses = [column == name for name in period_names]
    clauses.extend(column.ilike(f"%{name}%") for name in period_names)
    return or_(*clauses)


def _status_values(statuses: list[str]) -> list[str]:
    allowed = {s.value for s in AssignmentEntityStatusValue}
    return [s for s in statuses if s in allowed] or ["submitted", "approved"]


def _base_form_data_query(filters: AggregationFilters):
    statuses = _status_values(filters.assignment_statuses)
    q = (
        db.session.query(FormData)
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status.in_(statuses),
            FormData.not_applicable.isnot(True),
        )
    )
    if filters.template_ids:
        q = q.filter(
            AssignedForm.template_id.in_(filters.template_ids),
            FormItem.template_id.in_(filters.template_ids),
        )
    if filters.period_names:
        q = q.filter(_period_filter(AssignedForm.period_name, filters.period_names))
    if filters.country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(filters.country_ids))
    if filters.indicator_bank_ids:
        q = q.filter(FormItem.indicator_bank_id.in_(filters.indicator_bank_ids))
    return q


def aggregate_indicator(
    *,
    template_id: int,
    indicator_bank_id: int,
    period_name: str,
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Per-indicator period aggregation (value, implementing, reported counts)."""
    filters = AggregationFilters(
        template_ids=[template_id],
        period_names=[period_name] if period_name else [],
        country_ids=country_ids or [],
        indicator_bank_ids=[indicator_bank_id],
        assignment_statuses=assignment_statuses or ["submitted", "approved"],
    )
    base = (
        db.session.query(
            func.sum(FormData.numeric_value).label("total_value"),
            func.count(FormData.id)
            .filter(
                or_(
                    FormData.numeric_value.isnot(None),
                    FormData.data_not_available.is_(True),
                )
            )
            .label("implementing"),
            func.count(FormData.id)
            .filter(and_(FormData.numeric_value.isnot(None), FormData.numeric_value > 0))
            .label("reported_count"),
        )
        .select_from(FormData)
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.template_id == template_id,
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            FormData.not_applicable.isnot(True),
        )
    )
    statuses = _status_values(assignment_statuses or ["submitted", "approved"])
    base = base.filter(AssignmentEntityStatus.status.in_(statuses))
    if period_name:
        base = base.filter(_period_filter(AssignedForm.period_name, [period_name]))
    if country_ids:
        base = base.filter(AssignmentEntityStatus.entity_id.in_(country_ids))
    row = base.one()
    total_value = row.total_value
    return {
        "value": float(total_value) if total_value is not None else None,
        "implementing": int(row.implementing or 0),
        "reported_count": int(row.reported_count or 0),
    }


def count_reporting_entities(
    *,
    template_id: int,
    period_name: str,
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
) -> int:
    """Distinct countries with submitted/approved assignments for a template/period."""
    statuses = _status_values(assignment_statuses or ["submitted", "approved"])
    q = (
        db.session.query(func.count(func.distinct(AssignmentEntityStatus.entity_id)))
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status.in_(statuses),
        )
    )
    if period_name:
        q = q.filter(_period_filter(AssignedForm.period_name, [period_name]))
    if country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(country_ids))
    return int(q.scalar() or 0)


def aggregate_indicator_by_country(
    *,
    template_id: int,
    indicator_bank_id: int,
    period_names: list[str],
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
    metric: str = "sum",
) -> list[dict[str, Any]]:
    statuses = _status_values(assignment_statuses or ["submitted", "approved"])
    value_expr = func.sum(FormData.numeric_value)
    if metric == "count":
        value_expr = func.count(FormData.id)
    elif metric == "implementing_count":
        value_expr = func.count(
            FormData.id.filter(
                or_(
                    FormData.numeric_value.isnot(None),
                    FormData.data_not_available.is_(True),
                )
            )
        )
    elif metric == "reported_count":
        value_expr = func.count(
            FormData.id.filter(and_(FormData.numeric_value.isnot(None), FormData.numeric_value > 0))
        )

    q = (
        db.session.query(
            AssignmentEntityStatus.entity_id.label("country_id"),
            value_expr.label("value"),
        )
        .select_from(FormData)
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.template_id == template_id,
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status.in_(statuses),
            FormData.not_applicable.isnot(True),
        )
        .group_by(AssignmentEntityStatus.entity_id)
    )
    if period_names:
        q = q.filter(_period_filter(AssignedForm.period_name, period_names))
    if country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(country_ids))

    country_map = {c.id: c.name for c in Country.query.filter(Country.id.in_([r.country_id for r in q.all()])).all()}
    results = []
    for row in q.all():
        val = row.value
        if val is None:
            continue
        results.append(
            {
                "country_id": row.country_id,
                "country": country_map.get(row.country_id, str(row.country_id)),
                "value": float(val),
            }
        )
    results.sort(key=lambda r: r["value"], reverse=True)
    return results


def aggregate_indicator_timeseries(
    *,
    template_id: int,
    indicator_bank_id: int,
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
    limit_periods: int = 20,
) -> list[dict[str, Any]]:
    statuses = _status_values(assignment_statuses or ["submitted", "approved"])
    q = (
        db.session.query(
            AssignedForm.period_name.label("period_name"),
            func.sum(FormData.numeric_value).label("value"),
        )
        .select_from(FormData)
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.template_id == template_id,
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status.in_(statuses),
            FormData.not_applicable.isnot(True),
        )
        .group_by(AssignedForm.period_name)
        .order_by(AssignedForm.period_name.asc())
    )
    if country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(country_ids))

    series: list[dict[str, Any]] = []
    for row in q.limit(limit_periods).all():
        period = str(row.period_name or "").strip()
        if not period:
            continue
        year_digits = "".join(ch for ch in period if ch.isdigit())[:4]
        x = int(year_digits) if year_digits else None
        if x is None:
            continue
        val = row.value
        if val is None:
            continue
        series.append(
            {
                "x": x,
                "y": float(val),
                "period_name": period,
            }
        )
    return series


def list_indicator_period_years(
    *,
    template_id: int,
    indicator_bank_id: int,
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
    period_names: list[str] | None = None,
    limit_periods: int = 20,
) -> list[tuple[int, str]]:
    """Distinct calendar years for an indicator, with a representative period_name."""
    statuses = _status_values(assignment_statuses or ["submitted", "approved"])
    q = (
        db.session.query(AssignedForm.period_name.label("period_name"))
        .select_from(FormData)
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.template_id == template_id,
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status.in_(statuses),
            FormData.not_applicable.isnot(True),
        )
        .distinct()
        .order_by(AssignedForm.period_name.asc())
    )
    if country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(country_ids))
    if period_names:
        q = q.filter(_period_filter(AssignedForm.period_name, period_names))

    year_map: dict[int, str] = {}
    for (period_name,) in q.limit(limit_periods).all():
        period = str(period_name or "").strip()
        if not period:
            continue
        year_digits = "".join(ch for ch in period if ch.isdigit())[:4]
        if not year_digits:
            continue
        year_int = int(year_digits)
        year_map.setdefault(year_int, period)
    return sorted(year_map.items())


def aggregate_indicator_dashboard(
    *,
    template_id: int,
    indicator_bank_id: int,
    country_ids: list[int] | None = None,
    assignment_statuses: list[str] | None = None,
    period_names: list[str] | None = None,
    limit_periods: int = 20,
) -> dict[str, Any]:
    """Per-year value plus NS reporting/implementing counts (P&B dashboard parity)."""
    years: list[str] = []
    values: list[float | None] = []
    reporting: list[int] = []
    implementing: list[int] = []
    series: list[dict[str, Any]] = []

    for year_int, period_name in list_indicator_period_years(
        template_id=template_id,
        indicator_bank_id=indicator_bank_id,
        country_ids=country_ids,
        assignment_statuses=assignment_statuses,
        period_names=period_names,
        limit_periods=limit_periods,
    ):
        agg = aggregate_indicator(
            template_id=template_id,
            indicator_bank_id=indicator_bank_id,
            period_name=period_name,
            country_ids=country_ids,
            assignment_statuses=assignment_statuses,
        )
        year_str = str(year_int)
        val = agg.get("value")
        years.append(year_str)
        values.append(val)
        reporting.append(int(agg.get("reported_count") or 0))
        implementing.append(int(agg.get("implementing") or 0))
        if val is not None:
            series.append({"x": year_int, "y": float(val), "period_name": period_name})

    return {
        "years": years,
        "values": values,
        "reporting": reporting,
        "implementing": implementing,
        "series": series,
    }


def assignment_status_counts(filters: AggregationFilters) -> list[dict[str, Any]]:
    statuses = _status_values(filters.assignment_statuses)
    q = (
        db.session.query(
            AssignmentEntityStatus.status.label("status"),
            func.count(AssignmentEntityStatus.id).label("count"),
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(AssignmentEntityStatus.entity_type == "country")
    )
    if filters.template_ids:
        q = q.filter(AssignedForm.template_id.in_(filters.template_ids))
    if filters.period_names:
        q = q.filter(_period_filter(AssignedForm.period_name, filters.period_names))
    if filters.country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(filters.country_ids))
    if statuses:
        q = q.filter(AssignmentEntityStatus.status.in_(statuses))
    q = q.group_by(AssignmentEntityStatus.status)
    return [{"status": str(r.status), "count": int(r.count)} for r in q.all()]


def assignment_list_rows(filters: AggregationFilters, *, limit: int = 500) -> list[dict[str, Any]]:
    q = (
        db.session.query(AssignmentEntityStatus)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(AssignmentEntityStatus.entity_type == "country")
    )
    if filters.template_ids:
        q = q.filter(AssignedForm.template_id.in_(filters.template_ids))
    if filters.period_names:
        q = q.filter(_period_filter(AssignedForm.period_name, filters.period_names))
    if filters.country_ids:
        q = q.filter(AssignmentEntityStatus.entity_id.in_(filters.country_ids))
    statuses = _status_values(filters.assignment_statuses)
    if statuses:
        q = q.filter(AssignmentEntityStatus.status.in_(statuses))

    rows = q.limit(limit).all()
    country_ids = {r.entity_id for r in rows if r.entity_id}
    country_map = {c.id: c.name for c in Country.query.filter(Country.id.in_(country_ids)).all()} if country_ids else {}

    return [
        {
            "id": r.id,
            "country_id": r.entity_id,
            "country": country_map.get(r.entity_id, str(r.entity_id)),
            "status": str(r.status),
            "completion_rate": r.completion_rate,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "assignment_id": r.assigned_form_id,
        }
        for r in rows
    ]


def indicator_value_rows(filters: AggregationFilters, *, limit: int = 1000) -> list[dict[str, Any]]:
    q = (
        _base_form_data_query(filters)
        .options(
            joinedload(FormData.form_item),
            joinedload(FormData.assignment_entity_status).joinedload(AssignmentEntityStatus.assigned_form),
        )
    )
    rows = q.limit(limit).all()
    indicator_ids = {r.form_item.indicator_bank_id for r in rows if r.form_item and r.form_item.indicator_bank_id}
    indicators = {
        ib.id: ib.name
        for ib in IndicatorBank.query.filter(IndicatorBank.id.in_(indicator_ids)).all()
    } if indicator_ids else {}

    result = []
    for fd in rows:
        ib_id = fd.form_item.indicator_bank_id if fd.form_item else None
        result.append(
            {
                "form_data_id": fd.id,
                "indicator_bank_id": ib_id,
                "indicator": indicators.get(ib_id, ""),
                "country_id": fd.assignment_entity_status.entity_id if fd.assignment_entity_status else None,
                "value": fd.value,
                "num_value": float(fd.numeric_value) if fd.numeric_value is not None else None,
                "period_name": (
                    fd.assignment_entity_status.assigned_form.period_name
                    if fd.assignment_entity_status and fd.assignment_entity_status.assigned_form
                    else None
                ),
            }
        )
    return result
