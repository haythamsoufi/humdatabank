"""Turn one public ``dref3`` row into the fields the monitoring tables store."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from plugins.emergency_operations_monitoring.constants import SECTORS
from plugins.emergency_operations_monitoring.services.parsing import as_bool, as_date, as_int, as_money


def appeal_kind(appeal_type: str) -> str:
    return (appeal_type or "").strip().lower().replace("_", "-").replace(" ", "-")


def is_dref_appeal(appeal_type: str) -> bool:
    """Response DREF and Imminent DREF."""
    return appeal_kind(appeal_type) in {"dref", "i-dref", "idref"}


def is_emergency_appeal(appeal_type: str) -> bool:
    """An Emergency Appeal (``EA`` on the dref3 feed, ``Emergency Appeal`` on the appeal API)."""
    return appeal_kind(appeal_type) in {"ea", "emergency-appeal"}


def is_monitored_appeal(appeal_type: str) -> bool:
    """The appeal types this plugin monitors: DREF, Imminent DREF, and Emergency Appeal."""
    return is_dref_appeal(appeal_type) or is_emergency_appeal(appeal_type)


def appeal_type_label(appeal_type: str) -> str:
    """English name for an appeal type. Other values are shown as GO sent them."""
    if is_emergency_appeal(appeal_type):
        return "Emergency Appeal"
    if is_imminent(appeal_type, ""):
        return "Imminent DREF"
    if is_dref_appeal(appeal_type):
        return "DREF"
    return (appeal_type or "").strip()


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
        # Set on a row built from the GO appeal API. It outranks the dref3 stages of the same appeal code.
        "from_appeal_feed": as_bool(row.get("appeal_feed")),
        "sectors": sectors_from_row(row),
        "application": row.get("application") if isinstance(row.get("application"), dict) else None,
    }


def application_signature(application) -> tuple:
    """Titles and targets of the planned interventions. Empty when GO sent none."""
    if not isinstance(application, dict):
        return ()
    items = []
    for item in application.get("interventions") or []:
        if not isinstance(item, dict):
            continue
        indicators = tuple(
            (str(indicator.get("title") or ""), indicator.get("target"))
            for indicator in item.get("indicators") or []
            if isinstance(indicator, dict)
        )
        activities = tuple(str(title) for title in item.get("activities") or [])
        items.append(
            (item.get("key"), str(item.get("budget")), item.get("people_targeted"), indicators, activities)
        )
    return tuple(items)


def narrative_signature(application) -> str:
    """Digest of the written application. It is not part of ``stage_signature``.

    New wording must be saved, but it must not open a new plan version.
    """
    if not isinstance(application, dict):
        return ""
    material = {
        "version": application.get("narrative_version"),
        "narrative": application.get("narrative"),
        "context": application.get("context"),
        "contacts": application.get("contacts"),
    }
    strategy = application.get("operational_strategy")
    if isinstance(strategy, dict) and strategy.get("id") not in (None, ""):
        try:
            strategy_id = int(strategy.get("id"))
        except (TypeError, ValueError):
            strategy_id = str(strategy.get("id"))
        # A new or replaced operational strategy must be saved. It is not a plan rebase by itself.
        material["operational_strategy"] = {
            "id": strategy_id,
            "created_at": str(strategy.get("created_at") or "")[:40],
        }
    if (
        not material["narrative"]
        and not material["context"]
        and not material["contacts"]
        and "operational_strategy" not in material
    ):
        return ""
    raw = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stage_signature(parsed: dict[str, Any]) -> tuple:
    sectors = tuple(
        (item["key"], str(item["budget_chf"]), item["people_targeted"])
        for item in parsed.get("sectors") or []
    )
    return (
        str(parsed.get("total_approved")),
        parsed.get("end_date"),
        sectors,
        application_signature(parsed.get("application")),
    )
