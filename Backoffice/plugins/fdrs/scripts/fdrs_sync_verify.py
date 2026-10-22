"""
Compare FDRS data-api values to template-21 form_data after sync.

One row per (BaseKPI, year, country): FDRS value, databank value, and a status
of matched / skipped_intentionally / missing / mismatch.

Usage (from Backoffice/):
    python scripts/dev/verify_fdrs_sync.py --years 2024
    python scripts/dev/verify_fdrs_sync.py --years 2023,2024 --problems-only
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fdrs_sync_constants import (
    FDRS_INCOME_KPI_TO_MATRIX_ROW,
    FDRS_INCOME_SOURCES_MATRIX_COLUMN,
    FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
    FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX,
    FDRS_NETWORK_SUPPORT_GIVEN_COLUMN,
    FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
    FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX,
    FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN,
    FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
    FDRS_QUESTION_KPI_TO_ITEM,
    FDRS_SECTION_WORKFLOW_SPECS,
    fdrs_kpi_has_data_availability_suffix,
)

STATUS_MATCHED = "matched"
STATUS_SKIPPED = "skipped_intentionally"
STATUS_MISSING = "missing"
STATUS_MISMATCH = "mismatch"

KIND_INDICATOR = "indicator"
KIND_QUESTION = "question"
KIND_INCOME = "income_matrix"
KIND_NETWORK = "network_support"
KIND_WORKFLOW = "workflow"
KIND_OTHER = "other"

_NETWORK_SLOT_RE = re.compile(
    rf"^({re.escape(FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX)}|{re.escape(FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX)})\d+(_amount)?$",
    re.IGNORECASE,
)
_WORKFLOW_PREFIXES = tuple(f"{spec['prefix']}_" for spec in FDRS_SECTION_WORKFLOW_SPECS)
_WORKFLOW_BASES = tuple(spec["prefix"] for spec in FDRS_SECTION_WORKFLOW_SPECS)

DATA_POINT_COLUMNS = (
    "year",
    "ISO3",
    "country_name",
    "DonCode",
    "KPI",
    "kpi_name",
    "kpi_code_used",
    "kind",
    "fdrs_value",
    "fdrs_imputed_value",
    "fdrs_state",
    "fdrs_value_status",
    "databank_value",
    "databank_imputed_value",
    "databank_data_not_available",
    "databank_not_applicable",
    "item_id",
    "assignment_entity_status_id",
    "status",
    "detail",
)

SUMMARY_COLUMNS = ("status", "detail", "count")
KPI_COVERAGE_COLUMNS = (
    "KPI",
    "kpi_name",
    "kind",
    "item_id",
    "matched",
    "skipped_intentionally",
    "missing",
    "mismatch",
    "total",
)


@dataclass
class DatabankValue:
    value: Any = None
    numeric_value: Any = None
    imputed_value: Any = None
    imputed_numeric_value: Any = None
    data_not_available: bool = False
    not_applicable: bool = False
    disagg_data: Any = None
    disagg_type: Optional[str] = None


@dataclass
class FdrsDataPoint:
    year: str
    iso3: str
    don_code: str
    base_kpi: str
    kpi_code_used: str = ""
    kind: str = KIND_OTHER
    fdrs_value: Any = None
    fdrs_imputed_value: Any = None
    fdrs_state: Any = None
    fdrs_value_status: str = ""
    data_not_available: bool = False
    not_applicable: bool = False
    skip_reason: Optional[str] = None
    item_id: Optional[int] = None
    aes_id: Optional[int] = None
    matrix_cell: Optional[str] = None
    network_db_value: Any = None
    network_status: str = ""
    network_detail: str = ""
    kpi_name: str = ""
    country_name: str = ""
    databank: Optional[DatabankValue] = None
    status: str = ""
    detail: str = ""


def _blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _as_whole_number(val: Any) -> Optional[int]:
    """Match importer rounding (ROUND_HALF_UP to int). None when not numeric."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(",", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite():
        return None
    return int(d.to_integral_value(rounding=ROUND_HALF_UP))


def values_equal(left: Any, right: Any) -> bool:
    """True when FDRS and databank scalars represent the same stored value."""
    if _blank(left) and _blank(right):
        return True
    if _blank(left) or _blank(right):
        return False
    ln = _as_whole_number(left)
    rn = _as_whole_number(right)
    if ln is not None and rn is not None:
        return ln == rn
    return str(left).strip().lower() == str(right).strip().lower()


def kpi_kind(base_kpi: str) -> str:
    k = (base_kpi or "").strip()
    if not k:
        return KIND_OTHER
    if k in FDRS_QUESTION_KPI_TO_ITEM:
        return KIND_QUESTION
    if k in FDRS_INCOME_KPI_TO_MATRIX_ROW or f"{k}_CHF" in FDRS_INCOME_KPI_TO_MATRIX_ROW:
        return KIND_INCOME
    if _NETWORK_SLOT_RE.match(k):
        return KIND_NETWORK
    if k in _WORKFLOW_BASES or k.startswith(_WORKFLOW_PREFIXES):
        return KIND_WORKFLOW
    if k.startswith("KPI_"):
        return KIND_INDICATOR
    return KIND_OTHER


def _majority_reason(rows: Sequence[Dict[str, Any]], key: str) -> str:
    counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        reason = (r.get(key) or "").strip()
        if reason:
            counts[reason] += 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _imputed_parent_from_ip_rows(
    rows: Sequence[Dict[str, Any]],
    base_kpi: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Pick the ``*_IP`` row whose value was stored as the parent indicator's imputed value.

    Preference matches the importer: the base code, then ``_Tot``, then ``_CPD``.
    """
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    for row in rows:
        if (row.get("fdrs_data_filter_reason") or "").strip() != "ends_with_IP":
            continue
        code = (row.get("KPI_code") or "").strip()
        if not code.endswith("_IP"):
            continue
        candidates.append((code[: -len("_IP")], row))
    if not candidates:
        return None, None
    for target in (base_kpi, f"{base_kpi}_Tot", f"{base_kpi}_CPD"):
        for parent, row in candidates:
            if parent == target and not _blank(row.get("Value")):
                return parent, row
    for parent, row in candidates:
        if not _blank(row.get("Value")):
            return parent, row
    parent, row = candidates[0]
    return parent, row


def _row_included(row: Dict[str, Any]) -> bool:
    flag = row.get("in_fdrs_data_stage")
    if flag is None:
        return True
    return str(flag).strip().lower() in ("yes", "true", "1")


def _is_variant_kpi(kpi_code: str, base_kpi: str) -> bool:
    kpi = (kpi_code or "").strip()
    base = (base_kpi or "").strip()
    if not kpi or not base or kpi == base:
        return False
    if fdrs_kpi_has_data_availability_suffix(kpi):
        return True
    if kpi in (base + "_Tot", base + "_CPD", base + "_I"):
        return False
    return True


def _network_matrix_target(base_kpi: str) -> Optional[Tuple[int, str, str]]:
    """Return (item_id, amount column, code prefix) for a network-support slot KPI."""
    k = (base_kpi or "").strip()
    if not _NETWORK_SLOT_RE.match(k):
        return None
    lower = k.lower()
    if lower.startswith(FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX):
        return (
            FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
            FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN,
            FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX,
        )
    if lower.startswith(FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX):
        return (
            FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
            FDRS_NETWORK_SUPPORT_GIVEN_COLUMN,
            FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX,
        )
    return None


def _network_slot_index(base_kpi: str, prefix: str) -> Optional[int]:
    rest = (base_kpi or "")[len(prefix) :]
    if rest.lower().endswith("_amount"):
        rest = rest[: -len("_amount")]
    return int(rest) if rest.isdigit() else None


def _disagg_payload(point: FdrsDataPoint) -> Optional[Dict[str, Any]]:
    db = point.databank
    if db is None:
        return None
    payload = db.disagg_data
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
    return payload if isinstance(payload, dict) else {}


def apply_network_matrix_checks(
    points: Sequence[FdrsDataPoint],
    don_to_label: Optional[Dict[str, str]] = None,
) -> None:
    """Compare received/given support slots to matrix items 929 and 919.

    ``received_supportN`` is the partner NS codes and ``received_supportN_amount``
    is the matching amounts. Both are stored on item 929 as ``{NS name}_Funding Received``.
    Support given uses item 919 the same way. A cell may be the sum of several slots.
    """
    from import_fdrs_form_data import _parse_don_code_amount_pairs

    labels = don_to_label or {}
    grouped: Dict[Tuple[str, str, str], Dict[int, Dict[str, FdrsDataPoint]]] = defaultdict(dict)
    for point in points:
        if point.kind != KIND_NETWORK or point.skip_reason:
            continue
        target = _network_matrix_target(point.base_kpi)
        if target is None or not point.iso3:
            continue
        _item_id, _column, prefix = target
        slot = _network_slot_index(point.base_kpi, prefix)
        if slot is None:
            continue
        role = "amount" if point.base_kpi.lower().endswith("_amount") else "code"
        grouped[(point.iso3, point.year, prefix)].setdefault(slot, {})[role] = point

    for (iso3, year, prefix), slots in grouped.items():
        sample = next(iter(next(iter(slots.values())).values()))
        target = _network_matrix_target(sample.base_kpi)
        if target is None:
            continue
        _item_id, column, _prefix = target
        sums: Dict[str, int] = defaultdict(int)
        amount_reported: set = set()
        parsed_slots: Dict[int, List[Tuple[str, Optional[int]]]] = {}
        for slot, roles in slots.items():
            code_point = roles.get("code")
            amount_point = roles.get("amount")
            pairs = _parse_don_code_amount_pairs(
                code_point.fdrs_value if code_point is not None else "",
                amount_point.fdrs_value if amount_point is not None else "",
            )
            parsed_slots[slot] = pairs
            for don, amount in pairs:
                if amount is None:
                    continue
                sums[don] += amount
                amount_reported.add(don)

        payload = None
        for roles in slots.values():
            for point in roles.values():
                payload = _disagg_payload(point)
                if payload is not None:
                    break
            if payload is not None:
                break

        for slot, roles in slots.items():
            pairs = parsed_slots.get(slot) or []
            names: List[str] = []
            found_amounts: List[str] = []
            missing: List[str] = []
            differed: List[str] = []
            for don, _amount in pairs:
                label = labels.get(don, don)
                key = f"{label}_{column}"
                names.append(label)
                present = payload is not None and key in payload
                cell = payload.get(key) if present else None
                if not present:
                    missing.append(don)
                    found_amounts.append("")
                    continue
                found_amounts.append("" if _blank(cell) else str(cell).strip())
                if don in amount_reported:
                    if not values_equal(cell, sums[don]):
                        differed.append(don)
                elif not _blank(cell):
                    differed.append(don)
            code_point = roles.get("code")
            amount_point = roles.get("amount")
            if code_point is not None and not _blank(code_point.fdrs_value):
                code_point.network_db_value = ", ".join(names) if names else None
                if payload is None:
                    code_point.network_status = STATUS_MISSING
                    code_point.network_detail = "value_not_in_databank"
                elif missing:
                    code_point.network_status = STATUS_MISSING
                    code_point.network_detail = "matrix_row_missing"
                else:
                    code_point.network_status = STATUS_MATCHED
                    code_point.network_detail = "matrix_row"
            if amount_point is not None and not _blank(amount_point.fdrs_value):
                amount_point.network_db_value = ",".join(found_amounts) if found_amounts else None
                if payload is None:
                    amount_point.network_status = STATUS_MISSING
                    amount_point.network_detail = "value_not_in_databank"
                elif missing:
                    amount_point.network_status = STATUS_MISSING
                    amount_point.network_detail = "matrix_amount_missing"
                elif differed:
                    amount_point.network_status = STATUS_MISMATCH
                    amount_point.network_detail = "matrix_amount_differs"
                else:
                    amount_point.network_status = STATUS_MATCHED
                    amount_point.network_detail = "matrix_amount"


def build_point_from_group(rows: Sequence[Dict[str, Any]]) -> FdrsDataPoint:
    """Collapse raw FDRS snapshot rows that share (country, year, BaseKPI)."""
    from import_fdrs_form_data import (
        _data_availability_from_group_rows,
        _main_value_empty_or_zero,
        _normalize_question_value,
        _pick_imputed_value_for_base,
        _pick_total_row_for_base,
    )

    first = rows[0]
    iso3 = (first.get("ISO3") or "").strip()
    year = str(first.get("year") or "").strip()
    don = (first.get("DonCode") or "").strip()
    base_kpi = (first.get("BaseKPI") or "").strip()
    for r in rows:
        if (r.get("ISO3") or "").strip():
            iso3 = (r.get("ISO3") or "").strip()
            break
    kind = kpi_kind(base_kpi)
    point = FdrsDataPoint(
        year=year,
        iso3=iso3,
        don_code=don,
        base_kpi=base_kpi,
        kind=kind,
    )

    if kind == KIND_WORKFLOW:
        point.skip_reason = "assignment_workflow"
        point.kpi_code_used = base_kpi
        point.fdrs_value = first.get("Value")
        point.fdrs_state = first.get("State")
        point.fdrs_value_status = (first.get("ValueStatus") or "")
        return point
    if kind == KIND_NETWORK:
        target = _network_matrix_target(base_kpi)
        if target is not None:
            point.item_id = target[0]

    if not iso3:
        point.skip_reason = "no_iso3_mapping"
        point.kpi_code_used = (first.get("KPI_code") or base_kpi).strip()
        point.fdrs_value = first.get("Value")
        point.fdrs_imputed_value = first.get("ImputedValue")
        point.fdrs_state = first.get("State")
        point.fdrs_value_status = (first.get("ValueStatus") or "")
        return point

    included = [r for r in rows if _row_included(r)]
    if not included:
        reason = _majority_reason(rows, "fdrs_data_filter_reason") or "filtered_in_fdrs_data_stage"
        statuses = {(r.get("ValueStatus") or "").strip() for r in rows}
        if "Unpublished Reported" in statuses and reason in ("", "null_or_empty_value"):
            reason = "unpublished_or_not_filled"
        parent_code, ip_row = _imputed_parent_from_ip_rows(rows, base_kpi) if reason == "ends_with_IP" else (None, None)
        if ip_row is not None and not _blank(ip_row.get("Value")):
            # ``*_IP`` is the imputed figure for the parent indicator, not a dropped KPI.
            point.kpi_code_used = parent_code or base_kpi
            point.fdrs_value = None
            point.fdrs_imputed_value = ip_row.get("Value")
            point.fdrs_state = ip_row.get("State")
            point.fdrs_value_status = (ip_row.get("ValueStatus") or "")
            return point
        point.skip_reason = reason
        sample = rows[0]
        point.kpi_code_used = (sample.get("KPI_code") or base_kpi).strip()
        point.fdrs_value = sample.get("Value")
        point.fdrs_imputed_value = sample.get("ImputedValue")
        point.fdrs_state = sample.get("State")
        point.fdrs_value_status = (sample.get("ValueStatus") or "")
        return point

    dna, na = _data_availability_from_group_rows(included)
    point.data_not_available = dna
    point.not_applicable = na

    if kind == KIND_QUESTION:
        picked = next(
            (r for r in included if (r.get("KPI_code") or "").strip() == base_kpi),
            included[0],
        )
        point.kpi_code_used = (picked.get("KPI_code") or base_kpi).strip()
        point.fdrs_value = _normalize_question_value(base_kpi, picked.get("Value"))
        point.fdrs_imputed_value = picked.get("ImputedValue")
        point.fdrs_state = picked.get("State")
        point.fdrs_value_status = (picked.get("ValueStatus") or "")
        if _blank(point.fdrs_value):
            point.skip_reason = "main_value_empty_or_zero"
        return point

    picked = _pick_total_row_for_base(list(included), base_kpi)
    point.kpi_code_used = (picked.get("KPI_code") or base_kpi).strip()
    point.fdrs_value = picked.get("Value")
    point.fdrs_imputed_value = _pick_imputed_value_for_base(list(included), base_kpi)
    point.fdrs_state = picked.get("State")
    point.fdrs_value_status = (picked.get("ValueStatus") or "")
    if kind == KIND_INCOME:
        row_label = FDRS_INCOME_KPI_TO_MATRIX_ROW.get(base_kpi) or FDRS_INCOME_KPI_TO_MATRIX_ROW.get(
            f"{base_kpi}_CHF"
        )
        if row_label:
            point.matrix_cell = f"{row_label}_{FDRS_INCOME_SOURCES_MATRIX_COLUMN}"
            point.item_id = FDRS_INCOME_SOURCES_MATRIX_ITEM_ID

    has_scalar = not _main_value_empty_or_zero(point.fdrs_value) or not _main_value_empty_or_zero(
        point.fdrs_imputed_value
    )
    if not (dna or na or has_scalar):
        if point.kpi_code_used and _is_variant_kpi(point.kpi_code_used, base_kpi):
            point.skip_reason = "variant_or_disagg_only"
        else:
            point.skip_reason = "main_value_empty_or_zero"
    return point


def group_snapshot_to_points(snapshot_rows: Iterable[Dict[str, Any]]) -> List[FdrsDataPoint]:
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for raw in snapshot_rows or []:
        iso3 = (raw.get("ISO3") or "").strip()
        don = (raw.get("DonCode") or "").strip()
        year = str(raw.get("year") or "").strip()
        base = (raw.get("BaseKPI") or "").strip()
        if not year or not base:
            continue
        country_key = iso3 or don or "?"
        groups[(country_key, year, base)].append(raw)
    points = [build_point_from_group(rows) for rows in groups.values()]
    points.sort(key=lambda p: (p.year, p.iso3 or p.don_code, p.base_kpi))
    return points


def apply_mapping_skips(
    points: Sequence[FdrsDataPoint],
    *,
    assignment_by_key: Dict[Tuple[str, str], int],
    base_to_item_id: Dict[str, int],
    bank_kpi_codes: Optional[set] = None,
) -> None:
    """Fill item_id / aes_id and mapping skip reasons (in place)."""
    bank_codes = bank_kpi_codes or set()
    for point in points:
        if point.kind == KIND_QUESTION:
            point.item_id = FDRS_QUESTION_KPI_TO_ITEM.get(point.base_kpi)
        elif point.kind == KIND_INCOME:
            point.item_id = FDRS_INCOME_SOURCES_MATRIX_ITEM_ID
        elif point.kind == KIND_NETWORK and point.item_id is None:
            target = _network_matrix_target(point.base_kpi)
            if target is not None:
                point.item_id = target[0]
        elif point.item_id is None:
            item_id = base_to_item_id.get(point.base_kpi)
            if item_id is not None:
                point.item_id = item_id

        if point.iso3:
            point.aes_id = assignment_by_key.get((point.year, point.iso3))

        if point.skip_reason:
            continue
        if point.kind == KIND_WORKFLOW:
            continue
        if point.item_id is None:
            if point.base_kpi in bank_codes:
                point.skip_reason = "no_form_item_for_template"
            else:
                point.skip_reason = "no_indicator_bank_match"
            continue
        if point.aes_id is None:
            point.skip_reason = "no_assignment"


def _databank_comparable(point: FdrsDataPoint) -> Tuple[Any, Any]:
    """Return (main_value, imputed_value) from the databank row for this point."""
    db = point.databank
    if point.network_db_value is not None:
        return point.network_db_value, None
    if db is None:
        return None, None
    if point.matrix_cell:
        payload = db.disagg_data
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if point.base_kpi in FDRS_INCOME_KPI_TO_MATRIX_ROW:
            chf_value = payload.get(f"_chf|{point.matrix_cell}")
            if chf_value is not None and not _blank(chf_value):
                return chf_value, db.imputed_value
        return payload.get(point.matrix_cell), db.imputed_value
    if db.data_not_available or db.not_applicable:
        return None, None
    main = db.value if not _blank(db.value) else db.numeric_value
    imputed = db.imputed_value if not _blank(db.imputed_value) else db.imputed_numeric_value
    return main, imputed


def classify_point(point: FdrsDataPoint) -> Tuple[str, str]:
    """
    Return (status, detail) for one data point.

    skipped_intentionally: pipeline would not write this scalar (known filter).
    matched: databank value (or flags) agrees with FDRS.
    missing: we would import it, but databank has no comparable value.
    mismatch: both sides have a value and they differ.
    """
    if point.network_status:
        return point.network_status, point.network_detail or "matrix"
    if point.skip_reason:
        return STATUS_SKIPPED, point.skip_reason

    db = point.databank
    db_main, db_imputed = _databank_comparable(point)
    db_dna = bool(db.data_not_available) if db is not None else False
    db_na = bool(db.not_applicable) if db is not None else False

    if point.data_not_available or point.not_applicable:
        if db is None:
            return STATUS_MISSING, "availability_flag_not_in_databank"
        if bool(point.data_not_available) == db_dna and bool(point.not_applicable) == db_na:
            return STATUS_MATCHED, "availability_flags"
        return STATUS_MISMATCH, "availability_flags_differ"

    fdrs_has_main = not _blank(point.fdrs_value)
    fdrs_has_imputed = not _blank(point.fdrs_imputed_value)
    db_has_main = not _blank(db_main)
    db_has_imputed = not _blank(db_imputed)

    if not fdrs_has_main and fdrs_has_imputed:
        if db is None or not db_has_imputed:
            # Imputed may have been stored on value if a later edit copied it.
            if db_has_main and values_equal(point.fdrs_imputed_value, db_main):
                return STATUS_MATCHED, "imputed_stored_as_value"
            return STATUS_MISSING, "imputed_value_not_in_databank"
        if values_equal(point.fdrs_imputed_value, db_imputed):
            return STATUS_MATCHED, "imputed_value"
        return STATUS_MISMATCH, "imputed_value_differs"

    if not fdrs_has_main:
        return STATUS_SKIPPED, "null_or_empty_value"

    if db is None or not db_has_main:
        return STATUS_MISSING, "value_not_in_databank"

    if values_equal(point.fdrs_value, db_main):
        if fdrs_has_imputed and db_has_imputed and not values_equal(point.fdrs_imputed_value, db_imputed):
            return STATUS_MISMATCH, "imputed_value_differs"
        return STATUS_MATCHED, "value"

    return STATUS_MISMATCH, "value_differs"


def attach_databank_values(
    points: Sequence[FdrsDataPoint],
    *,
    by_iso_year_item: Dict[Tuple[str, str, int], DatabankValue],
    country_names: Optional[Dict[str, str]] = None,
    kpi_names: Optional[Dict[str, str]] = None,
) -> None:
    names = country_names or {}
    kpi_map = kpi_names or {}
    for point in points:
        if not point.country_name:
            point.country_name = names.get(point.iso3, "")
        if not point.kpi_name:
            point.kpi_name = kpi_map.get(point.base_kpi, "")
        if point.item_id is None or not point.iso3:
            continue
        point.databank = by_iso_year_item.get((point.iso3, point.year, int(point.item_id)))


def attach_classification(points: Sequence[FdrsDataPoint]) -> None:
    for point in points:
        status, detail = classify_point(point)
        point.status = status
        point.detail = detail


def point_to_row(point: FdrsDataPoint) -> Dict[str, Any]:
    db_main, db_imputed = _databank_comparable(point)
    db = point.databank
    return {
        "year": point.year,
        "ISO3": point.iso3,
        "country_name": point.country_name,
        "DonCode": point.don_code,
        "KPI": point.base_kpi,
        "kpi_name": point.kpi_name,
        "kpi_code_used": point.kpi_code_used,
        "kind": point.kind,
        "fdrs_value": point.fdrs_value,
        "fdrs_imputed_value": point.fdrs_imputed_value,
        "fdrs_state": point.fdrs_state,
        "fdrs_value_status": point.fdrs_value_status,
        "databank_value": db_main,
        "databank_imputed_value": db_imputed,
        "databank_data_not_available": bool(db.data_not_available) if db is not None else "",
        "databank_not_applicable": bool(db.not_applicable) if db is not None else "",
        "item_id": point.item_id if point.item_id is not None else "",
        "assignment_entity_status_id": point.aes_id if point.aes_id is not None else "",
        "status": point.status,
        "detail": point.detail,
    }


def summarize_points(points: Sequence[FdrsDataPoint]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    status_detail: Dict[Tuple[str, str], int] = defaultdict(int)
    by_kpi: Dict[str, Dict[str, Any]] = {}
    for point in points:
        status_detail[(point.status or "?", point.detail or "")] += 1
        bucket = by_kpi.setdefault(
            point.base_kpi,
            {
                "KPI": point.base_kpi,
                "kpi_name": point.kpi_name,
                "kind": point.kind,
                "item_id": point.item_id if point.item_id is not None else "",
                STATUS_MATCHED: 0,
                STATUS_SKIPPED: 0,
                STATUS_MISSING: 0,
                STATUS_MISMATCH: 0,
                "total": 0,
            },
        )
        if point.kpi_name and not bucket["kpi_name"]:
            bucket["kpi_name"] = point.kpi_name
        if point.item_id is not None and bucket["item_id"] == "":
            bucket["item_id"] = point.item_id
        bucket["total"] += 1
        if point.status in bucket:
            bucket[point.status] += 1

    summary_rows = [
        {"status": status, "detail": detail, "count": count}
        for (status, detail), count in sorted(status_detail.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    coverage_rows = [by_kpi[k] for k in sorted(by_kpi)]
    return summary_rows, coverage_rows


def counts_by_status(points: Sequence[FdrsDataPoint]) -> Dict[str, int]:
    out = {
        STATUS_MATCHED: 0,
        STATUS_SKIPPED: 0,
        STATUS_MISSING: 0,
        STATUS_MISMATCH: 0,
    }
    for point in points:
        if point.status in out:
            out[point.status] += 1
    return out
