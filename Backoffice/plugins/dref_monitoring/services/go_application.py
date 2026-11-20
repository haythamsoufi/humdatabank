"""Read the approved DREF application from the public GO emergency page.

``dref3`` only has sector totals. The emergency payload's ``dref`` object carries
the planned interventions (sectors), their indicators, and the activity text.
An imminent application puts structured activities on ``proposed_action``.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any

from plugins.dref_monitoring.constants import GO_API_ROOT, SECTOR_LABELS

logger = logging.getLogger(__name__)

# GO planned-intervention title -> the sector key used on dref3 and in this plugin.
INTERVENTION_TO_SECTOR = {
    "shelter_housing_and_settlements": "shelter_and_basic_household_items",
    "livelihoods_and_basic_needs": "livelihoods",
    "multi_purpose_cash": "multi_purpose_cash_grants",
    "health": "health",
    "water_sanitation_and_hygiene": "water_sanitation_and_hygiene",
    "protection_gender_and_inclusion": "protection_gender_and_inclusion",
    "education": "education",
    "migration_and_displacement": "migration_and_displacement",
    "risk_reduction_climate_adaptation_and_recovery": "risk_reduction_climate_adaptation_and_recovery",
    "community_engagement_and_accountability": "community_engagement_and_accountability",
    "environmental_sustainability": "environmental_sustainability",
    "coordination_and_partnerships": "coordination_and_partnerships",
    "secretariat_services": "secretariat_services",
    "national_society_strengthening": "national_society_strengthening",
}

# GO deployments.Sector primary keys used to tag an imminent activity.
# Same map the dref3 serializer uses to roll those activities up to a sector.
DEPLOYMENT_SECTOR_TO_KEY = {
    0: "water_sanitation_and_hygiene",
    1: "protection_gender_and_inclusion",
    2: "community_engagement_and_accountability",
    3: "migration_and_displacement",
    4: "health",
    5: "risk_reduction_climate_adaptation_and_recovery",
    6: "shelter_and_basic_household_items",
    7: "national_society_strengthening",
    8: "education",
    9: "livelihoods",
}

_EVENT_ID = re.compile(r"/emergencies/(\d+)(?:/|$)")
_LINE_MARKER = re.compile(r"^(?:\d+[\).\]]\s*|[-•*]\s+)")


def event_id_from_link(link: str) -> int | None:
    match = _EVENT_ID.search(str(link or ""))
    if not match:
        return None
    return int(match.group(1))


def sector_key_for_title(title: str) -> str:
    raw = str(title or "").strip()
    if raw in SECTOR_LABELS:
        return raw
    return INTERVENTION_TO_SECTOR.get(raw, "")


def activities_from_description(text: str) -> list[str]:
    """One activity per numbered or bulleted line. A single paragraph stays one activity."""
    lines = []
    for raw in str(text or "").splitlines():
        line = _LINE_MARKER.sub("", raw.strip()).strip()
        if line:
            lines.append(line[:255])
    if lines:
        return lines
    paragraph = " ".join(str(text or "").split())
    if paragraph:
        return [paragraph[:255]]
    return []


def _indicators(raw) -> list[dict]:
    found = []
    if not isinstance(raw, list):
        return found
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        target = item.get("target")
        try:
            target = None if target is None or target == "" else int(target)
        except (TypeError, ValueError):
            target = None
        found.append({"title": title[:255], "target": target})
    return found


def _intervention(item: dict) -> dict | None:
    title = str(item.get("title") or "").strip()
    key = sector_key_for_title(title)
    label = SECTOR_LABELS.get(key) or str(item.get("title_display") or title or "Sector")
    budget = item.get("budget")
    people = item.get("person_targeted")
    try:
        budget = None if budget is None or budget == "" else int(budget)
    except (TypeError, ValueError):
        budget = None
    try:
        people = None if people is None or people == "" else int(people)
    except (TypeError, ValueError):
        people = None
    return {
        "key": key,
        "label": label[:180],
        "budget": budget,
        "people_targeted": people,
        "indicators": _indicators(item.get("indicators")),
        "activities": activities_from_description(item.get("description") or ""),
    }


def _sector_id(raw) -> int | None:
    if isinstance(raw, dict):
        raw = raw.get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _merge_proposed_actions(interventions: list[dict], actions) -> None:
    """Attach imminent activities to the sector they were tagged with."""
    if not isinstance(actions, list):
        return
    by_key = {item["key"]: item for item in interventions if item.get("key")}
    for action in actions:
        if not isinstance(action, dict):
            continue
        phase = "Early actions" if action.get("proposed_type") == 1 else ""
        if action.get("proposed_type") == 2:
            phase = "Early response"
        for activity in action.get("activities") or []:
            if not isinstance(activity, dict):
                continue
            text = str(activity.get("activity") or "").strip()
            if not text:
                continue
            key = DEPLOYMENT_SECTOR_TO_KEY.get(_sector_id(activity.get("sector")) or -1, "")
            title = f"{phase}: {text}" if phase else text
            title = title[:255]
            host = by_key.get(key)
            if host is None:
                host = {
                    "key": key,
                    "label": (SECTOR_LABELS.get(key) or "Proposed actions")[:180],
                    "budget": action.get("total_budget"),
                    "people_targeted": None,
                    "indicators": [],
                    "activities": [],
                }
                interventions.append(host)
                if key:
                    by_key[key] = host
            if title not in host["activities"]:
                host["activities"].append(title)


def _stage_source(dref: dict, stage: str) -> tuple[dict, str]:
    """The latest approved stage's plan, falling back to the application itself."""
    lowered = (stage or "").lower()
    final = dref.get("final_report_details")
    update = dref.get("operational_update_details")
    if "final" in lowered and isinstance(final, dict) and final.get("planned_interventions"):
        return final, "final_report"
    if ("update" in lowered or "operational" in lowered) and isinstance(update, dict) and update.get("planned_interventions"):
        return update, "operational_update"
    return dref, "application"


def application_from_emergency(payload: Any, stage: str = "") -> dict | None:
    """Sectors, indicators, and activities from one public emergency payload."""
    if not isinstance(payload, dict):
        return None
    dref = payload.get("dref")
    if not isinstance(dref, dict):
        return None
    source, source_name = _stage_source(dref, stage)
    interventions = []
    for item in source.get("planned_interventions") or []:
        if isinstance(item, dict):
            built = _intervention(item)
            if built is not None:
                interventions.append(built)
    _merge_proposed_actions(interventions, dref.get("proposed_action"))
    if not interventions:
        return None
    return {"source": source_name, "interventions": interventions}


def _fast_get(url, params):
    """Emergency pages are large. A short timeout keeps one missing page from stalling the sync."""
    import requests

    response = requests.get(
        url,
        params=params,
        timeout=(3, 8),
        headers={"Accept": "application/json", "User-Agent": "IFRC-Network-Databank/dref-monitoring"},
    )
    response.raise_for_status()
    return response.json()


def _read_emergency(http_get, url: str):
    try:
        return http_get(url, None), None
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404 or "404" in str(exc):
            return None, "missing"
        logger.info("DREF application lookup failed for %s: %s", url, exc)
        return None, "error"


def attach_applications(rows: list[dict], http_get=None, *, progress=None, should_stop=None) -> dict:
    """Fill ``application`` on each dref3 row from its public emergency page.

    A missing page (GO returns 404 for some linked emergencies) leaves that row
    without an application. The sync still stores the sector totals, and the plan
    falls back to one activity per sector. Lookups run together so one slow page
    does not hold the rest.
    """
    getter = http_get or _fast_get
    root = GO_API_ROOT.rstrip("/")
    event_ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or isinstance(row.get("application"), dict):
            continue
        event_id = event_id_from_link(row.get("link_to_emergency_page") or "")
        if event_id is None or event_id in seen:
            continue
        seen.add(event_id)
        event_ids.append(event_id)

    cache: dict[int, Any] = {}
    missing = 0
    errors = 0
    cancelled = False
    if event_ids and should_stop and should_stop():
        cancelled = True
    elif event_ids:
        workers = min(16, len(event_ids))
        pool = ThreadPoolExecutor(max_workers=workers)
        raised = None
        try:
            futures = [
                pool.submit(_read_emergency, getter, f"{root}/emergency/{event_id}/")
                for event_id in event_ids
            ]
            pending = set(futures)
            future_ids = dict(zip(futures, event_ids))
            done_count = 0
            while pending and not cancelled:
                if should_stop and should_stop():
                    cancelled = True
                    break
                finished, pending = wait(pending, timeout=0.4, return_when=FIRST_COMPLETED)
                for future in finished:
                    payload, problem = future.result()
                    cache[future_ids[future]] = payload
                    if problem == "missing":
                        missing += 1
                    elif problem == "error":
                        errors += 1
                    done_count += 1
                    if progress:
                        progress(
                            {
                                "stage": "applications",
                                "message": "Reading emergency pages (%(current)s of %(total)s).",
                                "message_vars": {"current": done_count, "total": len(event_ids)},
                                "current": done_count,
                                "total": len(event_ids),
                                "percent": round(20 + 55 * done_count / len(event_ids), 1),
                            }
                        )
        except Exception as exc:
            raised = exc
        finally:
            pool.shutdown(wait=raised is None and not cancelled, cancel_futures=True)
        if raised is not None:
            raise raised

    with_plan: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or isinstance(row.get("application"), dict):
            continue
        event_id = event_id_from_link(row.get("link_to_emergency_page") or "")
        if event_id is None:
            continue
        parsed = application_from_emergency(cache.get(event_id), str(row.get("stage") or ""))
        if parsed:
            row["application"] = parsed
            with_plan.add(event_id)
    if event_ids:
        logger.info(
            "DREF applications: %s emergency page(s), %s with a plan, %s not published, %s failed.",
            len(event_ids),
            len(with_plan),
            missing,
            errors,
        )
    return {
        "emergencies": len(event_ids),
        "with_plan": len(with_plan),
        "missing": missing,
        "errors": errors,
        "cancelled": cancelled,
    }
