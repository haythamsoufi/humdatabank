"""Turn a public GO ``appeal`` record into the row shape the DREF sync reads.

The ``dref3`` feed is a DREF dataset. Its ``EA`` rows are DREFs allocated as a loan
against an appeal, so they carry sector budgets for the loan and not for the appeal.
The appeal itself (code, country, hazard, amount requested, people targeted, dates,
status) is on ``/api/v2/appeal/`` with ``atype`` 1. GO publishes no sector budget,
indicator, or activity list for an Emergency Appeal. Those sit in the Emergency Plan
of Action document. The plan therefore starts as one group for the whole appeal, and
the National Society adds sectors and activities, or imports them from Excel.

Each appeal becomes a dref3-shaped row, so it goes through the same parser, baseline,
plan, and project code as a DREF stage. ``appeal_feed`` marks it, and it outranks the
dref3 stages of the same appeal code.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from plugins.dref_monitoring.constants import APPEAL_STAGE, APPEAL_STAGE_PREFIX, GO_APPEAL_TYPE_EA
from plugins.dref_monitoring.services.parsing import as_date, as_int

# GO appeal status: 0 active, 1 closed, 2 frozen, 3 archived. Only an active appeal is still operating.
# A frozen appeal is past its end date and waiting for the books to close, so it is treated as closed.
_ACTIVE = 0


def emergency_page_link(event_id: Any) -> str:
    """Public GO page of the event. The application reader takes the event id from this address."""
    number = as_int(event_id)
    return f"https://go.ifrc.org/emergencies/{number}" if number else ""


def _months(start: date | None, end: date | None) -> int | None:
    if start is None or end is None or end < start:
        return None
    return max(1, round((end - start).days / 30.4375))


def _name(value: Any, key: str) -> str:
    return str(value.get(key) or "").strip() if isinstance(value, dict) else ""


def appeal_row(item: Any) -> dict | None:
    """One Emergency Appeal as a dref3-shaped row. None for anything else, or when it has no code."""
    if not isinstance(item, dict) or as_int(item.get("atype")) != GO_APPEAL_TYPE_EA:
        return None
    code = str(item.get("code") or "").strip().upper()
    appeal_id = as_int(item.get("id"))
    if not code or appeal_id is None:
        return None
    country = item.get("country") if isinstance(item.get("country"), dict) else {}
    event = item.get("event_details") if isinstance(item.get("event_details"), dict) else {}
    start = as_date(item.get("start_date"))
    end = as_date(item.get("end_date"))
    active = as_int(item.get("status")) == _ACTIVE
    requested = item.get("amount_requested")
    return {
        "id": f"{APPEAL_STAGE_PREFIX}{appeal_id}",
        "appeal_id": appeal_id,
        "appeal_code": code,
        "stage": APPEAL_STAGE,
        "allocation": "",
        "pillar": "Response",
        "appeal_type": "EA",
        "allocation_type": "Appeal",
        "country": _name(country, "name"),
        "country_iso3": _name(country, "iso3"),
        "region": _name(item.get("region"), "region_name") or _name(item.get("region"), "label"),
        "disaster_definition": _name(item.get("dtype"), "name"),
        "disaster_name": str(item.get("name") or "").strip() or _name(event, "name") or code,
        "crisis_categorization": _name(event, "ifrc_severity_level_display"),
        # The amount requested is the appeal budget. GO has no separate "approved" figure for an appeal.
        "amount_approved": requested,
        "total_approved": requested,
        "people_targeted": item.get("num_beneficiaries"),
        "date_of_approval": start,
        "start_date_of_operation": start,
        "end_date_of_operation": end,
        "operation_timeframe": _months(start, end),
        "operation_status": "active" if active else "closed",
        "is_latest_stage": True,
        "link_to_emergency_page": emergency_page_link(item.get("event")),
        "appeal_feed": True,
    }


def enrich_from_emergency(row: dict, payload: Any) -> None:
    """Fill what the appeal list lacks from the public emergency page: areas, event date, people affected.

    Only blanks are filled, and only from a payload GO actually returned.
    """
    if not isinstance(payload, dict):
        return
    districts = payload.get("districts")
    if not row.get("districts") and isinstance(districts, list):
        names = [str(item.get("name") or "").strip() for item in districts if isinstance(item, dict)]
        row["districts"] = ", ".join(name for name in names if name)
    if not row.get("date_of_disaster") and as_date(payload.get("disaster_start_date")):
        row["date_of_disaster"] = as_date(payload.get("disaster_start_date"))
    if row.get("people_affected") in (None, "") and as_int(payload.get("num_affected")) is not None:
        row["people_affected"] = as_int(payload.get("num_affected"))


def appeal_queries(closed_since_year: int) -> list[dict]:
    """Two reads: every active appeal, and every appeal that started since the cutoff year, whatever its status."""
    return [
        {"atype": GO_APPEAL_TYPE_EA, "status": _ACTIVE},
        {"atype": GO_APPEAL_TYPE_EA, "start_date__gte": f"{int(closed_since_year)}-01-01"},
    ]
