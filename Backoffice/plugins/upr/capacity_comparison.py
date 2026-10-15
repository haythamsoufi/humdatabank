"""Compare National Society capacity figures across planning and reporting.

Templates 24 (Unified Country Plan) and 33 (country reporting) both collect
volunteers, staff, branches, and local units for the same country and year.
This module lines those figures up and marks what a validator should look at.

A figure needs attention when:

* two sources for the same year differ by 25% or more
* the same source moves by 50% or more from the previous year
* a submitted form left the figure blank after the other reported a number

A blank on a form that is only in progress, an explicit not-available or
not-applicable mark, and smaller gaps (10% between sources, 20% year to year)
are variations to review. Pending or cancelled assignments are not treated as
missing data.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from plugins.upr.catalog import (
    KPI_BANK_IDS,
    KPI_SPECS,
    PLAN_KPI_LABELS,
    PLAN_TEMPLATE_ID,
    REPORT_TEMPLATE_ID,
)
from plugins.upr.formatters import to_number
from plugins.upr.validation_dashboard import round_for_assignment

MEASURE_ORDER: tuple[str, ...] = ("volunteers", "staff", "branches", "local_units")
MEASURE_LABELS = {key: PLAN_KPI_LABELS[key] for key in MEASURE_ORDER}
BANK_TO_MEASURE = {spec.bank_id: spec.key for spec in KPI_SPECS if spec.key in MEASURE_LABELS}

# Share of the larger number. 12,000 vs 9,000 is 25% and needs attention.
REVIEW_GAP = 0.10
ATTENTION_GAP = 0.25
REVIEW_YOY = 0.20
ATTENTION_YOY = 0.50

SOURCE_PLAN = "plan"
SOURCE_ANNUAL = "annual"
SOURCE_MIDYEAR = "midyear"
SOURCES = (SOURCE_PLAN, SOURCE_ANNUAL, SOURCE_MIDYEAR)

SOURCE_LABELS = {
    SOURCE_PLAN: "planning",
    SOURCE_ANNUAL: "the annual report",
    SOURCE_MIDYEAR: "mid-year reporting",
}

# A form that has been submitted is expected to contain the figure.
# In progress only means someone opened it, so a blank there is a review.
SUBMITTED_STATUSES = frozenset({
    "requires_revision",
    "sent_for_review",
    "submitted",
    "approved",
})

_SEVERITY_RANK = {"attention": 3, "review": 2, "aligned": 1, "single": 0}


def _status_name(status: Any) -> str:
    if status is None:
        return ""
    value = getattr(status, "value", None)
    if isinstance(value, str):
        return value
    return str(status)


def _count(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return int(round(number))


def _fmt(value: int | None) -> str:
    if value is None:
        return ""
    return f"{value:,}"


def _pct_label(gap: float) -> str:
    return f"{round(gap * 100):.0f}%"


def _gap(left: int | None, right: int | None) -> float | None:
    if left is None or right is None:
        return None
    scale = max(abs(left), abs(right))
    if scale == 0:
        return 0.0
    return abs(left - right) / scale


def _gap_severity(gap: float | None, *, review: float, attention: float) -> str | None:
    if gap is None:
        return None
    if gap >= attention:
        return "attention"
    if gap >= review:
        return "review"
    return None


def _year_from_round(code: str) -> int | None:
    if code.startswith("MYR") and code[3:].isdigit():
        return 2000 + int(code[3:])
    if code.startswith("AR") and code[2:].isdigit():
        return 2000 + int(code[2:])
    if code.startswith("P") and code[1:].isdigit():
        return 2000 + int(code[1:])
    return None


def _source_for(template_id: int, round_code: str) -> str | None:
    if template_id == PLAN_TEMPLATE_ID:
        return SOURCE_PLAN
    if template_id != REPORT_TEMPLATE_ID:
        return None
    if round_code.startswith("MYR"):
        return SOURCE_MIDYEAR
    if round_code.startswith("AR"):
        return SOURCE_ANNUAL
    return None


def _prefer_value(existing: Mapping[str, Any] | None, incoming: Mapping[str, Any]) -> Mapping[str, Any]:
    """Keep a reported number over a later blank, otherwise the later entry."""
    if existing is None:
        return incoming
    existing_has = existing.get("value") is not None
    incoming_has = incoming.get("value") is not None
    if incoming_has and not existing_has:
        return incoming
    if existing_has and not incoming_has:
        return existing
    if int(incoming.get("form_data_id") or 0) >= int(existing.get("form_data_id") or 0):
        return incoming
    return existing


def _prefer_observation(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return incoming
    existing_has = existing.get("value") is not None
    incoming_has = incoming.get("value") is not None
    if incoming_has and not existing_has:
        return incoming
    if existing_has and not incoming_has:
        return existing
    if int(incoming.get("aes_id") or 0) >= int(existing.get("aes_id") or 0):
        return incoming
    return existing


def _number_from_fields(row: Mapping[str, Any]) -> int | None:
    if row.get("not_available") or row.get("not_applicable"):
        return None
    number = _count(row.get("numeric_value"))
    if number is None:
        number = _count(row.get("value"))
    return number


def rows_to_observations(
    assignments: Iterable[Mapping[str, Any]],
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One observation per country, measure, year, and source.

    ``assignments`` are country assignments on templates 24 and 33.
    ``values`` are stored answers for the capacity indicator-bank ids.
    """
    by_cell: dict[tuple[int, int], Mapping[str, Any]] = {}
    for row in values:
        bank_id = row.get("bank_id")
        if bank_id not in BANK_TO_MEASURE:
            continue
        aes_id = int(row["aes_id"])
        stored = {
            "form_data_id": int(row.get("form_data_id") or 0),
            "value": _number_from_fields(row),
            "not_available": bool(row.get("not_available")),
            "not_applicable": bool(row.get("not_applicable")),
        }
        key = (aes_id, int(bank_id))
        by_cell[key] = _prefer_value(by_cell.get(key), stored)

    observations: list[dict[str, Any]] = []
    for assignment in assignments:
        status = _status_name(assignment.get("status"))
        if status == "cancelled":
            continue
        template_id = int(assignment["template_id"])
        period_name = str(assignment.get("period_name") or "")
        round_code = round_for_assignment(template_id, period_name)
        if not round_code:
            continue
        year = _year_from_round(round_code)
        source = _source_for(template_id, round_code)
        if year is None or source is None:
            continue
        aes_id = int(assignment["aes_id"])
        for measure in MEASURE_ORDER:
            bank_id = KPI_BANK_IDS[measure]
            stored = by_cell.get((aes_id, bank_id))
            observations.append({
                "country_id": int(assignment["country_id"]),
                "country_name": str(assignment.get("country_name") or ""),
                "iso3": str(assignment.get("iso3") or ""),
                "region": str(assignment.get("region") or ""),
                "measure": measure,
                "year": year,
                "source": source,
                "value": None if stored is None else stored.get("value"),
                "status": status,
                "not_available": bool(stored and stored.get("not_available")),
                "not_applicable": bool(stored and stored.get("not_applicable")),
                "period_name": period_name,
                "round_code": round_code,
                "aes_id": aes_id,
            })
    return observations


def _availability(obs: Mapping[str, Any] | None) -> str | None:
    if not obs:
        return None
    if obs.get("not_applicable"):
        return "not applicable"
    if obs.get("not_available"):
        return "not available"
    return None


def _blank_severity(obs: Mapping[str, Any] | None) -> str | None:
    """How seriously to treat a blank figure on this assignment."""
    if not obs or obs.get("value") is not None or _availability(obs):
        return None
    status = obs.get("status")
    if status in SUBMITTED_STATUSES:
        return "attention"
    if status == "in_progress":
        return "review"
    return None


def _missing_flag(measure: str, filled: str, empty: str, value: int, obs: Mapping[str, Any]) -> dict[str, Any] | None:
    label = MEASURE_LABELS[measure]
    availability = _availability(obs)
    if availability:
        return _flag(
            "missing",
            "review",
            (
                f"{label}: {SOURCE_LABELS[filled]} has {_fmt(value)}, and "
                f"{SOURCE_LABELS[empty]} marked this figure {availability}."
            ),
            (filled, empty),
        )
    severity = _blank_severity(obs)
    if not severity:
        return None
    return _flag(
        "missing",
        severity,
        (
            f"{label}: {SOURCE_LABELS[filled]} has {_fmt(value)}, and "
            f"{SOURCE_LABELS[empty]} left this figure blank."
        ),
        (filled, empty),
    )


def _flag(
    kind: str,
    severity: str,
    text: str,
    sources: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "text": text,
        "sources": list(sources),
    }


def _discrepancy_flag(measure: str, left_source: str, right_source: str, left: int, right: int) -> dict[str, Any] | None:
    severity = _gap_severity(_gap(left, right), review=REVIEW_GAP, attention=ATTENTION_GAP)
    if not severity:
        return None
    label = MEASURE_LABELS[measure]
    return _flag(
        "discrepancy",
        severity,
        (
            f"{label}: {SOURCE_LABELS[left_source]} and {SOURCE_LABELS[right_source]} "
            f"differ by {_pct_label(_gap(left, right) or 0)} "
            f"({_fmt(left)} on {SOURCE_LABELS[left_source]}, "
            f"{_fmt(right)} on {SOURCE_LABELS[right_source]})."
        ),
        (left_source, right_source),
    )


def _variation_flag(measure: str, source: str, year: int, current: int, prior: int) -> dict[str, Any] | None:
    gap = _gap(prior, current)
    severity = _gap_severity(gap, review=REVIEW_YOY, attention=ATTENTION_YOY)
    if not severity or gap is None:
        return None
    direction = "higher" if current > prior else "lower"
    label = MEASURE_LABELS[measure]
    return _flag(
        "variation",
        severity,
        (
            f"{label} on {SOURCE_LABELS[source]} changed from {_fmt(prior)} in {year - 1} "
            f"to {_fmt(current)} ({_pct_label(gap)} {direction})."
        ),
        (source,),
    )


def _reporting_counterpart(slots: Mapping[str, Mapping[str, Any] | None]) -> str | None:
    """Annual report when it has a number, otherwise mid-year reporting."""
    annual = slots.get(SOURCE_ANNUAL)
    if annual and annual.get("value") is not None:
        return SOURCE_ANNUAL
    midyear = slots.get(SOURCE_MIDYEAR)
    if midyear and midyear.get("value") is not None:
        return SOURCE_MIDYEAR
    return None


def _flags_for_year(
    measure: str,
    year: int,
    slots: Mapping[str, Mapping[str, Any] | None],
    history: Mapping[tuple[str, int], int],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    plan = slots.get(SOURCE_PLAN)
    annual = slots.get(SOURCE_ANNUAL)
    midyear = slots.get(SOURCE_MIDYEAR)
    plan_value = plan.get("value") if plan else None
    annual_value = annual.get("value") if annual else None
    midyear_value = midyear.get("value") if midyear else None

    counterpart = _reporting_counterpart(slots)
    if plan_value is not None and counterpart:
        other = annual_value if counterpart == SOURCE_ANNUAL else midyear_value
        if other is not None:
            found = _discrepancy_flag(measure, SOURCE_PLAN, counterpart, plan_value, other)
            if found:
                flags.append(found)
    elif counterpart and plan and (_blank_severity(plan) or _availability(plan)):
        other = annual_value if counterpart == SOURCE_ANNUAL else midyear_value
        if other is not None:
            found = _missing_flag(measure, counterpart, SOURCE_PLAN, other, plan)
            if found:
                flags.append(found)

    if plan_value is not None:
        for source, obs in ((SOURCE_ANNUAL, annual), (SOURCE_MIDYEAR, midyear)):
            if source == counterpart:
                continue
            if obs and (_blank_severity(obs) or _availability(obs)):
                found = _missing_flag(measure, SOURCE_PLAN, source, plan_value, obs)
                if found:
                    flags.append(found)

    if annual_value is not None and midyear_value is not None:
        found = _discrepancy_flag(measure, SOURCE_ANNUAL, SOURCE_MIDYEAR, annual_value, midyear_value)
        if found:
            flags.append(found)

    for source, value in (
        (SOURCE_PLAN, plan_value),
        (SOURCE_ANNUAL, annual_value),
        (SOURCE_MIDYEAR, midyear_value),
    ):
        if value is None:
            continue
        prior = history.get((source, year - 1))
        if prior is None:
            continue
        found = _variation_flag(measure, source, year, value, prior)
        if found:
            flags.append(found)
    return flags


def _row_severity(flags: list[dict[str, Any]], filled_sources: int) -> str:
    if flags:
        return max(flags, key=lambda flag: _SEVERITY_RANK.get(flag["severity"], 0))["severity"]
    if filled_sources >= 2:
        return "aligned"
    return "single"


def _has_any_signal(slots: Mapping[str, Mapping[str, Any] | None], flags: list[dict[str, Any]]) -> bool:
    if flags:
        return True
    return any(obs and obs.get("value") is not None for obs in slots.values())


def build_capacity_comparison(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Group observations into country/measure/year rows with attention flags."""
    chosen: dict[tuple[int, str, int, str], dict[str, Any]] = {}
    for raw in observations:
        obs = dict(raw)
        key = (int(obs["country_id"]), str(obs["measure"]), int(obs["year"]), str(obs["source"]))
        chosen[key] = _prefer_observation(chosen.get(key), obs)

    grouped: dict[tuple[int, str, int], dict[str, Any]] = {}
    history: dict[tuple[int, str, str, int], int] = {}
    for key, obs in chosen.items():
        country_id, measure, year, source = key
        bucket = grouped.setdefault((country_id, measure, year), {"sample": obs, "slots": {}})
        bucket["slots"][source] = obs
        if obs.get("value") is not None:
            history[(country_id, measure, source, year)] = int(obs["value"])

    rows: list[dict[str, Any]] = []
    for (country_id, measure, year), bucket in grouped.items():
        slots = bucket["slots"]
        sample = bucket["sample"]
        year_history = {
            (source, prior_year): value
            for (hist_country, hist_measure, source, prior_year), value in history.items()
            if hist_country == country_id and hist_measure == measure
        }
        flags = _flags_for_year(measure, year, slots, year_history)
        if not _has_any_signal(slots, flags):
            continue
        values = {
            source: (slots.get(source) or {}).get("value")
            for source in SOURCES
        }
        filled = sum(1 for value in values.values() if value is not None)
        hot: list[str] = []
        for flag in flags:
            for source in flag["sources"]:
                if source not in hot:
                    hot.append(source)
        rows.append({
            "country_id": country_id,
            "country_name": sample.get("country_name") or "",
            "iso3": sample.get("iso3") or "",
            "region": sample.get("region") or "",
            "measure": measure,
            "measure_label": MEASURE_LABELS[measure],
            "year": year,
            "plan": values[SOURCE_PLAN],
            "annual": values[SOURCE_ANNUAL],
            "midyear": values[SOURCE_MIDYEAR],
            "severity": _row_severity(flags, filled),
            "flags": flags,
            "hot": hot,
        })

    rows.sort(key=lambda row: (
        -_SEVERITY_RANK.get(row["severity"], 0),
        (row["country_name"] or "").lower(),
        -int(row["year"]),
        MEASURE_ORDER.index(row["measure"]) if row["measure"] in MEASURE_ORDER else 99,
    ))
    return {
        "measures": [{"key": key, "label": MEASURE_LABELS[key]} for key in MEASURE_ORDER],
        "years": sorted({int(row["year"]) for row in rows}, reverse=True),
        "summary": _summary(rows),
        "rows": rows,
        "thresholds": {
            "source_review_pct": int(REVIEW_GAP * 100),
            "source_attention_pct": int(ATTENTION_GAP * 100),
            "yoy_review_pct": int(REVIEW_YOY * 100),
            "yoy_attention_pct": int(ATTENTION_YOY * 100),
        },
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    countries = {row["country_id"] for row in rows}
    attention_rows = [row for row in rows if row["severity"] == "attention"]
    discrepancies = variations = missing = 0
    for row in rows:
        for flag in row["flags"]:
            if flag["kind"] == "discrepancy":
                discrepancies += 1
            elif flag["kind"] == "variation":
                variations += 1
            elif flag["kind"] == "missing":
                missing += 1
    return {
        "countries": len(countries),
        "attention_rows": len(attention_rows),
        "attention_countries": len({row["country_id"] for row in attention_rows}),
        "review_rows": sum(1 for row in rows if row["severity"] == "review"),
        "discrepancies": discrepancies,
        "variations": variations,
        "missing": missing,
    }


def _assignment_records() -> list[dict[str, Any]]:
    from app import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country

    rows = (
        db.session.query(
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.entity_id,
            AssignmentEntityStatus.status,
            AssignedForm.template_id,
            AssignedForm.period_name,
            Country.name,
            Country.iso3,
            Country.region,
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignedForm.template_id.in_((PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID)),
        )
        .all()
    )
    return [
        {
            "aes_id": aes_id,
            "country_id": country_id,
            "status": status,
            "template_id": template_id,
            "period_name": period_name,
            "country_name": name,
            "iso3": iso3,
            "region": region,
        }
        for aes_id, country_id, status, template_id, period_name, name, iso3, region in rows
    ]


def _value_records() -> list[dict[str, Any]]:
    from app import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.form_items import FormItem
    from app.models.forms import FormData

    rows = (
        db.session.query(
            FormData.assignment_entity_status_id,
            FormData.id,
            FormItem.indicator_bank_id,
            FormData.numeric_value,
            FormData.value,
            FormData.data_not_available,
            FormData.not_applicable,
        )
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(
            AssignmentEntityStatus,
            AssignmentEntityStatus.id == FormData.assignment_entity_status_id,
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignedForm.template_id.in_((PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID)),
            FormItem.indicator_bank_id.in_(tuple(BANK_TO_MEASURE)),
        )
        .all()
    )
    return [
        {
            "aes_id": aes_id,
            "form_data_id": form_data_id,
            "bank_id": bank_id,
            "numeric_value": numeric_value,
            "value": value,
            "not_available": not_available,
            "not_applicable": not_applicable,
        }
        for aes_id, form_data_id, bank_id, numeric_value, value, not_available, not_applicable in rows
    ]


def load_capacity_comparison() -> dict[str, Any]:
    """Read planning and reporting assignments and compare the four capacity figures."""
    return build_capacity_comparison(rows_to_observations(_assignment_records(), _value_records()))
