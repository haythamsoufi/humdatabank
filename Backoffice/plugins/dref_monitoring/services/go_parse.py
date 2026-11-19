"""Turn one public ``dref3`` row into the fields the monitoring tables store."""

from __future__ import annotations

from typing import Any

from plugins.dref_monitoring.constants import SECTORS
from plugins.dref_monitoring.services.parsing import as_bool, as_date, as_int, as_money


def appeal_kind(appeal_type: str) -> str:
    return (appeal_type or "").strip().lower().replace("_", "-")


def is_dref_appeal(appeal_type: str) -> bool:
    """Response DREF and Imminent DREF. Emergency Appeals (EA) are not included."""
    return appeal_kind(appeal_type) in {"dref", "i-dref", "idref"}


def is_imminent(appeal_type: str, pillar: str) -> bool:
    if appeal_kind(appeal_type) in {"i-dref", "idref"}:
        return True
    return (pillar or "").strip().lower().startswith("anticip")


def sectors_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for key, label in SECTORS:
        active = as_bool(row.get(f"sector_{key}"))
        budget = as_money(row.get(f"sector_{key}_budget"))
        targeted = as_int(row.get(f"sector_{key}_people_targeted"))
        assisted = as_int(row.get(f"sector_{key}_people_assisted"))
        if not active and budget is None and targeted is None and assisted is None:
            continue
        found.append(
            {
                "key": key,
                "label": label,
                "budget_chf": budget,
                "people_targeted": targeted,
                "people_assisted": assisted,
            }
        )
    return found


def parse_stage(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    appeal = str(row.get("appeal_code") or "").strip().upper()
    stage_id = str(row.get("id") or "").strip()
    if not appeal or not stage_id:
        return None
    return {
        "appeal_code": appeal,
        "go_stage_id": stage_id,
        "go_appeal_id": as_int(row.get("appeal_id")),
        "stage": str(row.get("stage") or ""),
        "allocation": str(row.get("allocation") or ""),
        "pillar": str(row.get("pillar") or ""),
        "appeal_type": str(row.get("appeal_type") or ""),
        "allocation_type": str(row.get("allocation_type") or ""),
        "country_name": str(row.get("country") or ""),
        "country_iso3": str(row.get("country_iso3") or "").strip().upper(),
        "hazard": str(row.get("disaster_definition") or ""),
        "disaster_name": str(row.get("disaster_name") or appeal),
        "districts": str(row.get("districts") or ""),
        "region": str(row.get("region") or ""),
        "onset": str(row.get("type_of_onset") or ""),
        "crisis_category": str(row.get("crisis_categorization") or ""),
        "amount_approved": as_money(row.get("amount_approved")),
        "total_approved": as_money(row.get("total_approved")),
        "people_affected": as_int(row.get("people_affected")),
        "people_targeted": as_int(row.get("people_targeted")),
        "people_assisted": as_int(row.get("people_assisted")),
        "date_of_disaster": as_date(row.get("date_of_disaster")),
        "date_of_approval": as_date(row.get("date_of_approval")),
        "start_date": as_date(row.get("start_date_of_operation")),
        "end_date": as_date(row.get("end_date_of_operation")),
        "operation_timeframe_months": as_int(row.get("operation_timeframe")),
        "operation_status": str(row.get("operation_status") or "").strip().lower(),
        "is_latest_stage": as_bool(row.get("is_latest_stage")),
        "sectors": sectors_from_row(row),
    }


def stage_signature(parsed: dict[str, Any]) -> tuple:
    sectors = tuple(
        (item["key"], str(item["budget_chf"]), item["people_targeted"])
        for item in parsed.get("sectors") or []
    )
    return (
        str(parsed.get("total_approved")),
        parsed.get("end_date"),
        sectors,
    )
