"""Compare FDRS service income with the last two closed collection rounds.

FDRS imputes total income when a National Society has not reported, and does
not impute income sources. The open year's stored service-income total is
therefore only the Societies that filled the Service income row.

- Each year sums reported total income, or the imputed total when no reported
  total exists. Service income is the reported "Service income" matrix cell
  (legacy ``si_CHF`` if the matrix cell is absent). A blank source counts as
  zero. Other income is total income minus service income.
- The latest year is the open round. The average of service income in the two
  preceding years is a reference for those closed rounds, not an estimate of
  the open round. The difference shown beside it is the open round's total
  income minus that reference.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.services.data_quality.helpers import parse_period_year
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.fdrs.data_quality.fdrs_v1_catalog import (
    FINANCE_TOTAL_EXPENDITURE,
    FINANCE_TOTAL_INCOME,
)

SERVICE_INCOME_KPI = "si_CHF"
SERVICE_INCOME_ROW = "Service income"
SERVICE_INCOME_COLUMN = "Funding"
# Published FDRS income-sources matrix on template 21. Same id as
# fdrs_sync_constants.FDRS_INCOME_SOURCES_MATRIX_ITEM_ID.
INCOME_SOURCES_MATRIX_ITEM_ID = 943
BASELINE_YEAR_COUNT = 2

_KIND_INCOME = "income"
_KIND_EXPENDITURE = "expenditure"
_KIND_SERVICE_MATRIX = "service_matrix"
_KIND_SERVICE_LEGACY = "service_legacy"


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _number_from_text(value: Any) -> float | None:
    if _blank(value):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _amount(text: Any, numeric: Any) -> float | None:
    if not _blank(text):
        if numeric is not None:
            try:
                return float(numeric)
            except (TypeError, ValueError):
                return _number_from_text(text)
        return _number_from_text(text)
    if numeric is not None:
        try:
            return float(numeric)
        except (TypeError, ValueError):
            return None
    return None


def reported_or_imputed(
    value: Any,
    numeric_value: Any,
    imputed_value: Any,
    imputed_numeric_value: Any,
) -> tuple[float | None, str | None]:
    """Prefer a reported figure. Use the imputed figure only when reported is blank."""
    if not _blank(value):
        amount = _amount(value, numeric_value)
        if amount is not None:
            return amount, "reported"
    if _blank(value) and (not _blank(imputed_value) or imputed_numeric_value is not None):
        amount = _amount(imputed_value, imputed_numeric_value)
        if amount is not None:
            return amount, "imputed"
    if numeric_value is not None and _blank(value) and _blank(imputed_value) and imputed_numeric_value is None:
        try:
            return float(numeric_value), "reported"
        except (TypeError, ValueError):
            return None, None
    return None, None


def _payload_mapping(disagg: Any) -> Mapping[str, Any] | None:
    if isinstance(disagg, str):
        try:
            disagg = json.loads(disagg)
        except json.JSONDecodeError:
            return None
    if not isinstance(disagg, dict):
        return None
    values = disagg.get("values")
    if isinstance(values, dict):
        return values
    return disagg


def service_income_from_disagg(disagg: Any) -> float | None:
    """Reported Service income cell, or None when that row was not stored."""
    payload = _payload_mapping(disagg)
    if not payload:
        return None
    prefix = f"{SERVICE_INCOME_ROW}_".lower()
    exact = f"{SERVICE_INCOME_ROW}_{SERVICE_INCOME_COLUMN}".lower()
    found: float | None = None
    for key, raw in payload.items():
        label = str(key).strip().lower()
        if label in ("mode", "values", "direct", "indirect"):
            continue
        if label != exact and not label.startswith(prefix):
            continue
        amount = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else _number_from_text(raw)
        if amount is None:
            continue
        found = float(amount)
        if label == exact:
            return found
    return found


def _prefer_income(
    current: tuple[float, str] | None,
    amount: float,
    source: str,
) -> tuple[float, str]:
    if current is None or (current[1] == "imputed" and source == "reported"):
        return amount, source
    return current


def collapse_observations(
    observations: list[dict[str, Any]],
    *,
    published_only: bool = False,
) -> list[dict[str, Any]]:
    """One row per country-year. Countries without a total-income figure are dropped."""
    buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for obs in observations:
        year = obs.get("year")
        country_id = obs.get("country_id")
        if year is None or country_id is None:
            continue
        key = (int(country_id), int(year))
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "country_id": int(country_id),
                "country_name": obs.get("country_name") or "",
                "year": int(year),
                "income": None,
                "expenditure": None,
                "service_matrix": None,
                "service_legacy": None,
            }
            buckets[key] = bucket
        elif obs.get("country_name") and not bucket["country_name"]:
            bucket["country_name"] = obs["country_name"]

        kind = obs.get("kind")
        if kind in (_KIND_INCOME, _KIND_EXPENDITURE):
            amount, source = reported_or_imputed(
                obs.get("value"),
                obs.get("numeric_value"),
                obs.get("imputed_value"),
                obs.get("imputed_numeric_value"),
            )
            if amount is None or source is None:
                continue
            field = "income" if kind == _KIND_INCOME else "expenditure"
            bucket[field] = _prefer_income(bucket[field], amount, source)
        elif kind == _KIND_SERVICE_MATRIX:
            disagg = obs.get("published_disagg_data") if published_only else obs.get("disagg_data")
            cell = service_income_from_disagg(disagg)
            if cell is not None and bucket["service_matrix"] is None:
                bucket["service_matrix"] = cell
        elif kind == _KIND_SERVICE_LEGACY:
            if published_only:
                amount = _amount(obs.get("published_value"), obs.get("published_numeric_value"))
                if amount is not None and bucket["service_legacy"] is None:
                    bucket["service_legacy"] = amount
            else:
                amount, source = reported_or_imputed(
                    obs.get("value"),
                    obs.get("numeric_value"),
                    obs.get("imputed_value"),
                    obs.get("imputed_numeric_value"),
                )
                if amount is not None and source == "reported" and bucket["service_legacy"] is None:
                    bucket["service_legacy"] = amount

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        income = bucket["income"]
        if income is None:
            continue
        if bucket["service_matrix"] is not None:
            service = float(bucket["service_matrix"])
            service_reported = True
        elif bucket["service_legacy"] is not None:
            service = float(bucket["service_legacy"])
            service_reported = True
        else:
            service = 0.0
            service_reported = False
        expenditure = bucket["expenditure"]
        rows.append(
            {
                "country_id": bucket["country_id"],
                "country_name": bucket["country_name"],
                "year": bucket["year"],
                "total_income": float(income[0]),
                "income_source": income[1],
                "expenditure": None if expenditure is None else float(expenditure[0]),
                "service_income": service,
                "service_reported": service_reported,
            }
        )
    rows.sort(key=lambda row: (row["year"], row["country_name"], row["country_id"]))
    return rows


def _year_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        year = int(row["year"])
        slot = grouped.get(year)
        if slot is None:
            slot = {
                "year": year,
                "total_income": 0.0,
                "total_expenditure": 0.0,
                "expenditure_present": False,
                "service_income": 0.0,
                "count_reported": 0,
                "count_imputed": 0,
                "societies_with_service": 0,
            }
            grouped[year] = slot
        slot["total_income"] += float(row["total_income"])
        if row.get("expenditure") is not None:
            slot["total_expenditure"] += float(row["expenditure"])
            slot["expenditure_present"] = True
        slot["service_income"] += float(row["service_income"])
        if row.get("income_source") == "imputed":
            slot["count_imputed"] += 1
        else:
            slot["count_reported"] += 1
        if row.get("service_reported"):
            slot["societies_with_service"] += 1

    years = [grouped[year] for year in sorted(grouped)]
    previous: dict[str, Any] | None = None
    for slot in years:
        total = slot["total_income"]
        service = slot["service_income"]
        slot["other_income"] = total - service
        slot["service_share"] = (service / total) if total else None
        slot["total_expenditure"] = slot["total_expenditure"] if slot["expenditure_present"] else None
        if previous is None:
            slot["income_change"] = None
            slot["service_change"] = None
        else:
            slot["income_change"] = total - previous["total_income"]
            slot["service_change"] = service - previous["service_income"]
        previous = slot
        del slot["expenditure_present"]
    return years


def summarize_service_income(
    rows: list[dict[str, Any]],
    *,
    baseline_years: int = BASELINE_YEAR_COUNT,
) -> dict[str, Any]:
    """Build the yearly comparison and the closed-round service reference."""
    years = _year_totals(rows)
    reference = None
    if years:
        open_slot = years[-1]
        open_year = open_slot["year"]
        for slot in years:
            slot["is_open_round"] = slot["year"] == open_year
        prior = [slot for slot in years if slot["year"] < open_year]
        baseline = prior[-baseline_years:] if baseline_years > 0 else []
        if baseline:
            reference_service = sum(slot["service_income"] for slot in baseline) / len(baseline)
            reported_service = open_slot["service_income"]
            total_income = open_slot["total_income"]
            reference = {
                "open_year": open_year,
                "baseline_years": [slot["year"] for slot in baseline],
                "total_income": total_income,
                "reported_service_income": reported_service,
                "reference_service_income": reference_service,
                "income_minus_reference": total_income - reference_service,
                "service_difference": reported_service - reference_service,
                "count_reported": open_slot["count_reported"],
                "count_imputed": open_slot["count_imputed"],
                "societies_with_service": open_slot["societies_with_service"],
            }
        else:
            open_slot["is_open_round"] = True
    return {
        "currency": "CHF",
        "years": years,
        "reference": reference,
        "country_count": len({int(row["country_id"]) for row in rows}),
    }


def _item_ids_for_codes(template_id: int, codes: set[str]) -> dict[str, set[int]]:
    from app.models import FormItem, IndicatorBank

    found: dict[str, set[int]] = {code: set() for code in codes}
    items = (
        FormItem.query.join(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
        .filter(
            FormItem.template_id == template_id,
            FormItem.archived.is_(False),
            IndicatorBank.fdrs_kpi_code.in_(codes),
        )
        .all()
    )
    for item in items:
        code = (item.indicator_bank.fdrs_kpi_code or "").strip()
        if code in found:
            found[code].add(int(item.id))
    return found


def _matrix_item_ids(template_id: int) -> set[int]:
    from app.models import FormItem

    ids: set[int] = set()
    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.item_type == "matrix",
            FormItem.archived.is_(False),
        )
        .all()
    )
    for item in items:
        label = (item.label or "").lower()
        if "income" in label and "source" in label:
            ids.add(int(item.id))
    pinned = FormItem.query.filter_by(id=INCOME_SOURCES_MATRIX_ITEM_ID).first()
    if pinned is not None and pinned.template_id == template_id and not pinned.archived:
        ids.add(int(pinned.id))
    return ids


def load_service_income_analysis(
    template_id: int = FDRS_TEMPLATE_ID,
    *,
    published_only: bool = False,
) -> dict[str, Any]:
    """Read FDRS template totals and the income-sources matrix, then summarize."""
    from app.models import AssignedForm, AssignmentEntityStatus, Country, FormData
    from app.utils.country_utils import exclude_sandbox_countries

    by_code = _item_ids_for_codes(
        template_id,
        {FINANCE_TOTAL_INCOME, FINANCE_TOTAL_EXPENDITURE, SERVICE_INCOME_KPI},
    )
    income_ids = by_code[FINANCE_TOTAL_INCOME]
    expenditure_ids = by_code[FINANCE_TOTAL_EXPENDITURE]
    legacy_ids = by_code[SERVICE_INCOME_KPI]
    matrix_ids = _matrix_item_ids(template_id)
    all_ids = income_ids | expenditure_ids | legacy_ids | matrix_ids
    if not income_ids:
        summary = summarize_service_income([])
        summary["warning"] = "Total income was not found on the FDRS template."
        summary["published_only"] = published_only
        return summary

    query_rows = (
        FormData.query.join(
            AssignmentEntityStatus,
            FormData.assignment_entity_status_id == AssignmentEntityStatus.id,
        )
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            FormData.form_item_id.in_(all_ids),
        )
    )
    query_rows = (
        exclude_sandbox_countries(query_rows)
        .with_entities(
            AssignmentEntityStatus.entity_id,
            Country.name,
            AssignedForm.period_name,
            FormData.form_item_id,
            FormData.value,
            FormData.numeric_value,
            FormData.imputed_value,
            FormData.imputed_numeric_value,
            FormData.disagg_data,
            FormData.published_value,
            FormData.published_numeric_value,
            FormData.published_disagg_data,
        )
        .all()
    )

    observations: list[dict[str, Any]] = []
    for row in query_rows:
        year = parse_period_year(row.period_name)
        if year is None:
            continue
        item_id = int(row.form_item_id)
        if item_id in matrix_ids:
            kind = _KIND_SERVICE_MATRIX
        elif item_id in income_ids:
            kind = _KIND_INCOME
        elif item_id in expenditure_ids:
            kind = _KIND_EXPENDITURE
        elif item_id in legacy_ids:
            kind = _KIND_SERVICE_LEGACY
        else:
            continue
        observations.append(
            {
                "country_id": int(row.entity_id),
                "country_name": row.name,
                "year": year,
                "kind": kind,
                "value": row.value,
                "numeric_value": row.numeric_value,
                "imputed_value": row.imputed_value,
                "imputed_numeric_value": row.imputed_numeric_value,
                "disagg_data": row.disagg_data,
                "published_value": row.published_value,
                "published_numeric_value": row.published_numeric_value,
                "published_disagg_data": row.published_disagg_data,
            }
        )

    summary = summarize_service_income(
        collapse_observations(observations, published_only=published_only)
    )
    summary["template_id"] = template_id
    summary["published_only"] = published_only
    return summary
