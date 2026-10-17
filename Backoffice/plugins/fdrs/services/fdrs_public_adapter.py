"""Published FDRS snapshot, reshaped for the legacy data.ifrc.org client.

The Angular client talks to ``data-api.ifrc.org`` and parses nested ``data`` trees
keyed by legacy KPI strings. Backoffice stores one cell per indicator-bank item, with
sex/age inside ``published_disagg_data``. This module translates between the two.
See ``docs/FDRS-PUBLIC-FRONTEND-ADAPTER.md`` for the contract.

Reads only the published snapshot (``FormData.published_*``) of template 21 items
marked ``privacy = public``.

Legacy semantics this module reproduces:

- ``X_IP`` is reported **plus** imputed values; plain ``X`` is reported only.
- ``KpiImputedValue`` returns every society with a value and flags imputed rows
  with ``source = "I"``.
- Sex and age series (``X_M``, ``X_F``, ``X_M_age_6_12`` ...) come from the
  disaggregation of the base indicator.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import func

from app.extensions import db
from app.models import AssignedForm, FdrsSociety, FormData, FormItem, IndicatorBank
from app.models.assignments import AssignmentEntityStatus
from app.models.fdrs_society import FDRS_ZONES
from app.models.organization import NationalSociety
from app.services.data_quality.helpers import parse_period_year
from app.services.data_retrieval.shared import form_item_privacy_is_public_expr
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.fdrs.published_facts import published_numeric, published_snapshot_clause

# Same ids as ``plugins/fdrs/scripts/fdrs_sync_constants.py`` (kept here so the web
# process does not import the sync scripts). ``test_fdrs_public_compat`` asserts they
# match.
INCOME_MATRIX_ITEM_ID = 943
INCOME_MATRIX_COLUMN = "Funding"
INCOME_KPI_TO_ROW = {
    "h_gov_CHF": "Home Government",
    "f_gov_CHF": "Foreign Government",
    "ind_CHF": "Individuals",
    "corp_CHF": "Corporations",
    "found_CHF": "Foundations",
    "un_CHF": "UN Agencies & other Multilateral Agencies",
    "pooled_f_CHF": "Pooled funds",
    "ngo_CHF": "Non-governmental organizations",
    "si_CHF": "Service income",
    "iga_CHF": "Income generating activity",
    "KPI_incomeFromNSsLC_CHF": "Other National Society",
    "ifrc_CHF": "IFRC",
    "icrc_CHF": "ICRC",
    "other_CHF": "Other",
}
QUESTION_KPI_TO_ITEM = {"KPI_pr_sex": 924, "KPI_sg_sex": 934}
NETWORK_ITEMS = {
    "supported": (919, "Funding provided"),
    "received_support": (929, "Funding Received"),
}

AGE_BANDS = ("6_12", "13_17", "18_29", "30_39", "40_49", "50_59", "60_69", "70_79", "80")
HEADLINE_SUFFIXES = ("_Tot", "_CPD")
IMPUTED_SUFFIX = "_IP"
DIGITAL_MATURITY_CODES = ("KPIDigitalPeople", "KPIDigitalProcess", "KPIDigitalTechnology")
VOLUNTEER_BANK_CODE = "KPI_PeopleVol"
MAX_INDICATORS_PER_REQUEST = 200

KIND_TOTAL = "total"
KIND_SEX = "sex"
KIND_AGE = "age"
KIND_INCOME = "income"
KIND_QUESTION = "question"
KIND_NETWORK = "network"

_SEX_AGE_RE = re.compile(r"^(?P<base>.+?)_(?P<sex>[MF])(?:_age_(?P<age>[0-9]+(?:_[0-9]+)?))?$")
_NETWORK_RE = re.compile(r"^(?P<prefix>supported|received_support)(?P<slot>\d+)(?P<amount>_amount)?$")
_STRUCTURE_KEYS = frozenset({"mode", "values", "direct", "indirect", "disability", "total", "total_direct", "total_indirect"})
_AGE_ALIASES = {"80_plus": "80", "age_80": "80"}


@dataclass(frozen=True)
class SeriesSpec:
    """One response series, identified by the legacy code the client expects back."""

    code: str
    kind: str
    candidates: tuple[str, ...] = ()
    reported_only: bool = True
    sex: Optional[str] = None
    age: Optional[str] = None
    income_row: Optional[str] = None
    item_id: Optional[int] = None
    network_prefix: Optional[str] = None
    network_slot: int = 1
    network_amount: bool = False


@dataclass(frozen=True)
class Observation:
    value: Any
    imputed: bool = False


# ---------------------------------------------------------------------------
# Legacy code parsing (no database)
# ---------------------------------------------------------------------------


def _bank_candidates(code: str) -> tuple[str, ...]:
    out = [code]
    for suffix in HEADLINE_SUFFIXES:
        if code.endswith(suffix) and len(code) > len(suffix):
            out.append(code[: -len(suffix)])
    return tuple(out)


def parse_code(token: str) -> Optional[SeriesSpec]:
    """Translate one legacy KPI string. ``None`` when it cannot be a series."""
    token = (token or "").strip()
    if not token:
        return None
    imputed_read = token.endswith(IMPUTED_SUFFIX) and len(token) > len(IMPUTED_SUFFIX)
    core = token[: -len(IMPUTED_SUFFIX)] if imputed_read else token
    reported_only = not imputed_read

    if core in INCOME_KPI_TO_ROW:
        return SeriesSpec(
            token,
            KIND_INCOME,
            reported_only=reported_only,
            item_id=INCOME_MATRIX_ITEM_ID,
            income_row=INCOME_KPI_TO_ROW[core],
        )
    if core in QUESTION_KPI_TO_ITEM:
        return SeriesSpec(token, KIND_QUESTION, reported_only=reported_only, item_id=QUESTION_KPI_TO_ITEM[core])
    network = _NETWORK_RE.match(core)
    if network:
        return SeriesSpec(
            token,
            KIND_NETWORK,
            reported_only=reported_only,
            item_id=NETWORK_ITEMS[network.group("prefix")][0],
            network_prefix=network.group("prefix"),
            network_slot=int(network.group("slot")),
            network_amount=bool(network.group("amount")),
        )

    sex_age = _SEX_AGE_RE.match(core)
    if sex_age:
        age = sex_age.group("age")
        if age is not None and age not in AGE_BANDS:
            return None
        return SeriesSpec(
            token,
            KIND_AGE if age else KIND_SEX,
            candidates=_bank_candidates(sex_age.group("base")),
            reported_only=reported_only,
            sex="male" if sex_age.group("sex") == "M" else "female",
            age=age,
        )

    return SeriesSpec(token, KIND_TOTAL, candidates=_bank_candidates(core), reported_only=reported_only)


def _breakdown_specs(spec: SeriesSpec) -> list[SeriesSpec]:
    """Sex (and, for a bare base code, age) series the profile charts ask for implicitly.

    The sex chart requests ``KPI_PeopleVol_Tot`` and reads ``..._M`` / ``..._F`` out of the
    reply; the age chart strips the suffix and requests ``KPI_PeopleVol``.
    """
    if spec.kind != KIND_TOTAL or not spec.reported_only:
        return []
    out = [
        SeriesSpec(f"{spec.code}_{letter}", KIND_SEX, candidates=spec.candidates, sex=sex)
        for letter, sex in (("M", "male"), ("F", "female"))
    ]
    if not spec.code.endswith(HEADLINE_SUFFIXES):
        for letter, sex in (("M", "male"), ("F", "female")):
            for band in AGE_BANDS:
                out.append(
                    SeriesSpec(
                        f"{spec.code}_{letter}_age_{band}",
                        KIND_AGE,
                        candidates=spec.candidates,
                        sex=sex,
                        age=band,
                    )
                )
    return out


def split_codes(raw: Optional[str]) -> list[str]:
    seen: dict[str, None] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            seen.setdefault(part, None)
    return list(seen)


def resolve_requested(raw_indicators: Optional[str], *, society_scoped: bool) -> list[SeriesSpec]:
    """Series to return for a comma-separated ``indicator`` parameter.

    Sex and age series are added only when the request is scoped to a society
    (``KPI_Don_Code``). Adding them to the world-wide map call would triple its size.
    """
    specs: dict[str, SeriesSpec] = {}
    for token in split_codes(raw_indicators)[:MAX_INDICATORS_PER_REQUEST]:
        spec = parse_code(token)
        if spec is None:
            continue
        specs.setdefault(spec.code, spec)
        if society_scoped:
            for extra in _breakdown_specs(spec):
                specs.setdefault(extra.code, extra)
    return list(specs.values())


# ---------------------------------------------------------------------------
# Value extraction from a published cell
# ---------------------------------------------------------------------------


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def json_number(value: Optional[float]) -> Any:
    if value is None:
        return None
    if float(value).is_integer():
        return int(value)
    return value


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _payload(disagg: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(disagg, str):
        try:
            disagg = json.loads(disagg)
        except json.JSONDecodeError:
            return None
    if not isinstance(disagg, dict):
        return None
    values = disagg.get("values") if "values" in disagg else disagg
    if not isinstance(values, dict):
        return None
    direct = values.get("direct")
    return direct if isinstance(direct, dict) else values


def _leaves(disagg: Any) -> Iterable[tuple[str, float]]:
    payload = _payload(disagg)
    if not payload:
        return
    for key, raw in payload.items():
        name = str(key).strip()
        if name.lower() in _STRUCTURE_KEYS:
            continue
        if isinstance(raw, dict):
            for sub_key, sub_raw in raw.items():
                number = _number(sub_raw)
                if number is not None:
                    yield f"{name}_{sub_key}", number
            continue
        number = _number(raw)
        if number is not None:
            yield name, number


def _sex_and_age(slug: str) -> tuple[Optional[str], str]:
    for sex in ("female", "male"):
        if slug == sex:
            return sex, ""
        if slug.startswith(sex + "_"):
            return sex, slug[len(sex) + 1 :]
    return None, slug


def breakdown_cells(disagg: Any) -> dict[tuple[str, str], float]:
    """``{(sex, age_band): value}``; the age part is ``""`` for a sex-only cell."""
    out: dict[tuple[str, str], float] = {}
    for key, number in _leaves(disagg):
        sex, rest = _sex_and_age(_slug(key))
        if sex is None:
            continue
        band = _AGE_ALIASES.get(rest, rest)
        slot = (sex, band if band in AGE_BANDS else "")
        out[slot] = out.get(slot, 0.0) + number
    return out


def sex_total(disagg: Any, sex: str) -> Optional[float]:
    cells = breakdown_cells(disagg)
    matching = [value for (cell_sex, _band), value in cells.items() if cell_sex == sex]
    return sum(matching) if matching else None


def age_value(disagg: Any, sex: str, band: str) -> Optional[float]:
    return breakdown_cells(disagg).get((sex, band))


def disagg_total(disagg: Any) -> Optional[float]:
    values = [number for _key, number in _leaves(disagg)]
    return sum(values) if values else None


def matrix_cells(disagg: Any) -> dict[str, float]:
    """Matrix cells keyed ``{row label}_{column}`` (lower-cased)."""
    out: dict[str, float] = {}
    payload = _payload(disagg)
    if not payload:
        return out
    for key, raw in payload.items():
        number = _number(raw)
        if number is not None:
            out[str(key).strip().lower()] = number
    return out


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _total_value(row: Any) -> Optional[float]:
    number = published_numeric(row.published_numeric_value, row.published_value)
    if number is not None:
        return number
    return disagg_total(row.published_disagg_data)


def observation_for(spec: SeriesSpec, row: Any, *, name_to_don: Mapping[str, str]) -> Optional[Observation]:
    """The value ``row`` contributes to ``spec``, or ``None`` when it has none."""
    imputed = (row.published_source or "").strip().lower() == "imputed"
    if spec.reported_only and imputed:
        return None
    if spec.kind == KIND_TOTAL:
        value = json_number(_total_value(row))
    elif spec.kind == KIND_SEX:
        value = json_number(sex_total(row.published_disagg_data, spec.sex))
    elif spec.kind == KIND_AGE:
        value = json_number(age_value(row.published_disagg_data, spec.sex, spec.age))
    elif spec.kind == KIND_INCOME:
        key = f"{spec.income_row}_{INCOME_MATRIX_COLUMN}".lower()
        value = json_number(matrix_cells(row.published_disagg_data).get(key))
    elif spec.kind == KIND_QUESTION:
        value = _clean_text(row.published_value)
    elif spec.kind == KIND_NETWORK:
        if spec.network_slot != 1:
            return None
        value = _network_value(spec, row, name_to_don)
    else:
        return None
    if value is None:
        return None
    return Observation(value=value, imputed=imputed)


def _network_value(spec: SeriesSpec, row: Any, name_to_don: Mapping[str, str]) -> Optional[str]:
    """Counterpart DON codes (or their amounts), comma-separated, as the client splits them.

    Backoffice keeps one matrix cell per counterpart, so the legacy slot numbers are gone;
    slot 1 carries every counterpart.
    """
    column = NETWORK_ITEMS[spec.network_prefix][1].lower()
    codes: list[str] = []
    amounts: list[str] = []
    suffix = f"_{column}"
    for key, amount in matrix_cells(row.published_disagg_data).items():
        if not key.endswith(suffix):
            continue
        don = name_to_don.get(_norm(key[: -len(suffix)]))
        if not don:
            continue
        codes.append(don)
        amounts.append(str(json_number(amount)))
    if not codes:
        return None
    return ",".join(amounts if spec.network_amount else codes)


def _norm(text: str) -> str:
    return " ".join(str(text).casefold().split())


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def society_name_index() -> dict[str, str]:
    """Normalised society name, ISO3 or DON code -> DON code.

    Network-support matrix rows are labelled with the National Society name, so the
    reply needs the reverse lookup the importer used to build them.
    """
    index: dict[str, str] = {}
    by_country: dict[int, str] = {}
    for society in FdrsSociety.query.filter(FdrsSociety.is_active.is_(True)).all():
        index.setdefault(_norm(society.name), society.don_code)
        index.setdefault(_norm(society.don_code), society.don_code)
        iso3 = society.iso3 or (society.country.iso3 if society.country else None)
        if iso3:
            index.setdefault(_norm(iso3), society.don_code)
        if society.country_id:
            by_country.setdefault(society.country_id, society.don_code)
    if by_country:
        for ns in NationalSociety.query.filter(NationalSociety.country_id.in_(list(by_country))).all():
            if (ns.name or "").strip():
                index.setdefault(_norm(ns.name), by_country[ns.country_id])
    return index


def _resolve_item_ids(specs: list[SeriesSpec]) -> dict[str, list[int]]:
    """Public template-21 form items behind each spec."""
    wanted = {c.lower() for s in specs if s.kind in (KIND_TOTAL, KIND_SEX, KIND_AGE) for c in s.candidates}
    code_to_banks: dict[str, list[int]] = {}
    if wanted:
        for bank_id, code in (
            IndicatorBank.query.filter(func.lower(IndicatorBank.fdrs_kpi_code).in_(wanted))
            .with_entities(IndicatorBank.id, IndicatorBank.fdrs_kpi_code)
            .all()
        ):
            code_to_banks.setdefault(code.lower(), []).append(bank_id)
    special_ids = {s.item_id for s in specs if s.item_id is not None}
    bank_ids = [b for ids in code_to_banks.values() for b in ids]

    conditions = []
    if bank_ids:
        conditions.append(FormItem.indicator_bank_id.in_(bank_ids))
    if special_ids:
        conditions.append(FormItem.id.in_(list(special_ids)))
    if not conditions:
        return {}
    bank_to_items: dict[int, list[int]] = {}
    public_special: set[int] = set()
    for item_id, bank_id in (
        FormItem.query.filter(FormItem.template_id == FDRS_TEMPLATE_ID)
        .filter(form_item_privacy_is_public_expr())
        .filter(db.or_(*conditions))
        .with_entities(FormItem.id, FormItem.indicator_bank_id)
        .all()
    ):
        public_special.add(item_id)
        if bank_id is not None:
            bank_to_items.setdefault(bank_id, []).append(item_id)

    resolved: dict[str, list[int]] = {}
    for spec in specs:
        if spec.item_id is not None:
            if spec.item_id in public_special:
                resolved[spec.code] = [spec.item_id]
            continue
        for candidate in spec.candidates:
            items = [i for b in code_to_banks.get(candidate.lower(), []) for i in bank_to_items.get(b, [])]
            if items:
                resolved[spec.code] = items
                break
    return resolved


def _fetch_cells(
    item_ids: Iterable[int],
    *,
    year: Optional[int],
    don_codes: Optional[list[str]],
    zone_code: Optional[str],
):
    item_ids = list(item_ids)
    if not item_ids:
        return []
    query = (
        db.session.query(
            FormData.form_item_id,
            FormData.published_value,
            FormData.published_numeric_value,
            FormData.published_disagg_data,
            FormData.published_source,
            AssignedForm.period_name,
            FdrsSociety.don_code,
            FdrsSociety.zone_code,
        )
        .select_from(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(FdrsSociety, FdrsSociety.country_id == AssignmentEntityStatus.entity_id)
        .filter(AssignedForm.template_id == FDRS_TEMPLATE_ID)
        .filter(AssignmentEntityStatus.entity_type == "country")
        .filter(FdrsSociety.is_active.is_(True))
        .filter(FormData.form_item_id.in_(item_ids))
        .filter(published_snapshot_clause())
    )
    if year is not None:
        query = query.filter(AssignedForm.period_name.like(f"%{int(year)}%"))
    if don_codes:
        query = query.filter(FdrsSociety.don_code.in_(don_codes))
    if zone_code:
        query = query.filter(FdrsSociety.zone_code == zone_code)
    return query.order_by(FormData.published_at.asc().nullsfirst(), FormData.id.asc()).all()


def compute_series(
    specs: list[SeriesSpec],
    *,
    year: Optional[int] = None,
    don_codes: Optional[list[str]] = None,
    zone_code: Optional[str] = None,
) -> dict[str, dict[str, dict[int, Observation]]]:
    """``{series code: {don code: {year: Observation}}}`` for the specs that have data."""
    if not specs:
        return {}
    don_codes = [d.upper() for d in don_codes] if don_codes else None
    items_by_spec = _resolve_item_ids(specs)
    all_items = {i for ids in items_by_spec.values() for i in ids}
    rows_by_item: dict[int, list[Any]] = {}
    for row in _fetch_cells(all_items, year=year, don_codes=don_codes, zone_code=zone_code):
        rows_by_item.setdefault(row.form_item_id, []).append(row)

    name_to_don = society_name_index() if any(s.kind == KIND_NETWORK for s in specs) else {}
    result: dict[str, dict[str, dict[int, Observation]]] = {}
    for spec in specs:
        by_don: dict[str, dict[int, Observation]] = {}
        for item_id in items_by_spec.get(spec.code, []):
            for row in rows_by_item.get(item_id, []):
                row_year = parse_period_year(row.period_name)
                if row_year is None or (year is not None and row_year != year):
                    continue
                observation = observation_for(spec, row, name_to_don=name_to_don)
                if observation is not None:
                    by_don.setdefault(row.don_code, {})[row_year] = observation
        if by_don:
            result[spec.code] = by_don
    return result


def build_data_tree(
    specs: list[SeriesSpec],
    *,
    year: Optional[int] = None,
    don_codes: Optional[list[str]] = None,
    zone_code: Optional[str] = None,
) -> dict[str, Any]:
    """The ``/api/data`` response: indicator -> society -> ``{year, value}``."""
    computed = compute_series(specs, year=year, don_codes=don_codes, zone_code=zone_code)
    series = []
    for spec in specs:
        by_don = computed.get(spec.code)
        if not by_don:
            continue
        series.append(
            {
                "id": spec.code,
                "data": [
                    {
                        "id": don,
                        "data": [{"year": y, "value": obs.value} for y, obs in sorted(years.items())],
                    }
                    for don, years in sorted(by_don.items())
                ],
            }
        )
    return {"data": series}


def build_imputed_values(
    kpi_code: str,
    *,
    year: int,
    zone_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    """The ``/api/KpiImputedValue`` list. ``source`` is ``"I"`` for imputed, ``"R"`` for reported."""
    spec = parse_code(kpi_code)
    if spec is None or spec.kind != KIND_TOTAL:
        return []
    spec = SeriesSpec(spec.code, KIND_TOTAL, candidates=spec.candidates, reported_only=False)
    by_don = compute_series([spec], year=year, zone_code=zone_code).get(spec.code, {})
    return [
        {"doncode": don, "value": years[year].value, "source": "I" if years[year].imputed else "R"}
        for don, years in sorted(by_don.items())
        if year in years
    ]


def build_kpi_values(kpi_codes: list[str], *, year: int) -> list[dict[str, Any]]:
    """The ``/api/kpivalue`` list, one row per society and KPI. Text answers stay text."""
    specs = []
    for code in kpi_codes:
        spec = parse_code(code)
        if spec is not None and spec.kind == KIND_TOTAL:
            specs.append(SeriesSpec(spec.code, KIND_TOTAL, candidates=spec.candidates, reported_only=False))
    if not specs:
        return []
    items_by_spec = _resolve_item_ids(specs)
    all_items = {i for ids in items_by_spec.values() for i in ids}
    rows_by_item: dict[int, list[Any]] = {}
    for row in _fetch_cells(all_items, year=year, don_codes=None, zone_code=None):
        rows_by_item.setdefault(row.form_item_id, []).append(row)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for spec in specs:
        for item_id in items_by_spec.get(spec.code, []):
            for row in rows_by_item.get(item_id, []):
                if parse_period_year(row.period_name) != year:
                    continue
                number = _total_value(row)
                value = json_number(number) if number is not None else _clean_text(row.published_value)
                if value is None:
                    continue
                out[(row.don_code, spec.code)] = {
                    "doncode": row.don_code,
                    "DONCode": row.don_code,
                    "kpicode": spec.code,
                    "year": year,
                    "value": value,
                }
    return [out[key] for key in sorted(out)]


def build_global_validation(year: int) -> list[dict[str, Any]]:
    """The ``/api/globalvalidationdata`` list: volunteers per zone plus a world row."""
    spec = SeriesSpec(VOLUNTEER_BANK_CODE, KIND_TOTAL, candidates=(VOLUNTEER_BANK_CODE,), reported_only=False)
    by_don = compute_series([spec], year=year).get(spec.code, {})
    zone_by_don = {
        don: zone
        for don, zone in db.session.query(FdrsSociety.don_code, FdrsSociety.zone_code)
        .filter(FdrsSociety.don_code.in_(list(by_don)))
        .all()
    } if by_don else {}
    totals = {zone: 0.0 for zone in FDRS_ZONES}
    world = 0.0
    for don, years in by_don.items():
        observation = years.get(year)
        if observation is None:
            continue
        value = float(observation.value)
        world += value
        zone = zone_by_don.get(don)
        if zone in totals:
            totals[zone] += value
    rows = [{"ZoneCode": zone, "IntValue": int(round(total))} for zone, total in totals.items()]
    rows.append({"ZoneCode": "", "IntValue": int(round(world))})
    return rows


def last_published_year() -> int:
    """Greatest year with any published public FDRS value (previous calendar year if none)."""
    periods = (
        db.session.query(AssignedForm.period_name)
        .select_from(FormData)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(FormItem, FormData.form_item_id == FormItem.id)
        .filter(AssignedForm.template_id == FDRS_TEMPLATE_ID)
        .filter(AssignmentEntityStatus.entity_type == "country")
        .filter(form_item_privacy_is_public_expr())
        .filter(published_snapshot_clause())
        .distinct()
        .all()
    )
    years = [y for y in (parse_period_year(p[0]) for p in periods) if y is not None]
    return max(years) if years else date.today().year - 1


# ---------------------------------------------------------------------------
# Society reference
# ---------------------------------------------------------------------------


def _legacy_date(value: Optional[date]) -> Optional[str]:
    return value.strftime("%d.%m.%Y") if value else None


def society_to_legacy(society: FdrsSociety) -> dict[str, Any]:
    country = society.country
    zone_name = society.zone_name or FDRS_ZONES.get(society.zone_code or "")
    return {
        "KPI_DON_code": society.don_code,
        "NSO_DON_name": society.name,
        "NSO_ZON_name": zone_name,
        "ZON_Code": society.zone_code,
        "iso_3": (country.iso3 if country else None) or society.iso3,
        "iso_2": (country.iso2 if country else None) or society.iso2,
        "country": society.country_name or (country.name if country else None),
        "lat": society.latitude,
        "long": society.longitude,
        "admission_date": _legacy_date(society.admission_date),
        "admission_date_note": society.admission_date_note,
        "cur_code": society.currency_code,
        "SearchString": society.search_string,
        "Url": society.website,
        "url": society.website,
        "facebook": society.facebook,
        "twitter": society.twitter,
        "othersocial": society.other_social,
    }


def list_societies() -> list[dict[str, Any]]:
    rows = FdrsSociety.query.filter(FdrsSociety.is_active.is_(True)).order_by(FdrsSociety.name.asc()).all()
    return [society_to_legacy(s) for s in rows]


def get_society(don_code: str) -> Optional[dict[str, Any]]:
    society = FdrsSociety.query.filter(
        func.upper(FdrsSociety.don_code) == (don_code or "").strip().upper(),
        FdrsSociety.is_active.is_(True),
    ).first()
    return society_to_legacy(society) if society else None
