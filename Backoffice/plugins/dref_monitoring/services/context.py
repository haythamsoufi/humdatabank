"""Background a draft needs besides the monitoring tables.

A report chapter such as "What happened" or "Needs" cannot come from figures. The
model therefore also receives, in order of trust:

1. the written application GO approved for this operation (stored at sync time),
2. the latest public GO field reports about the same emergency,
3. Databank documents about the country that the person generating the draft may read,
4. the previous draft for this operation, so an update continues rather than restarts.

Everything here is best effort. A missing page, a GO timeout, or an unavailable vector
store leaves that source out and the draft is still produced from the rest.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable

from app.extensions import db
from plugins.dref_monitoring.constants import GO_API_ROOT, SECTION_KEYS
from plugins.dref_monitoring.services.parsing import as_date, plain_text

logger = logging.getLogger(__name__)

FIELD_REPORT_TEXT_LIMIT = 2500
DOCUMENT_EXCERPT_LIMIT = 900
DOCUMENT_COUNT = 6
_ORGANIZATIONS = {
    "NTLS": "National Society",
    "PNS": "Partner National Societies",
    "FDRN": "IFRC",
}
_FIGURES = (
    ("num_dead", "dead"),
    ("num_injured", "injured"),
    ("num_missing", "missing"),
    ("num_affected", "affected"),
    ("num_displaced", "displaced"),
    ("num_assisted", "assisted by the Red Cross Red Crescent"),
    ("num_potentially_affected", "potentially affected"),
    ("num_highest_risk", "at highest risk"),
    ("gov_num_dead", "dead (government)"),
    ("gov_num_affected", "affected (government)"),
    ("gov_num_displaced", "displaced (government)"),
    ("other_num_dead", "dead (other source)"),
    ("other_num_affected", "affected (other source)"),
    ("other_num_displaced", "displaced (other source)"),
)


def _say(progress: Callable | None, stage: str, message: str, percent: float) -> None:
    if progress is not None:
        progress({"stage": stage, "message": message, "percent": percent})


def _fast_get(url: str, params=None):
    import requests

    response = requests.get(
        url,
        params=params,
        timeout=(3, 10),
        headers={"Accept": "application/json", "User-Agent": "IFRC-Network-Databank/dref-monitoring"},
    )
    response.raise_for_status()
    return response.json()


def field_report_summary(report: dict) -> dict:
    """What a National Society or the IFRC wrote in one field report. No contacts, no author."""
    figures = {}
    for key, label in _FIGURES:
        value = report.get(key)
        if value not in (None, "", 0):
            figures[label] = value
    actions = []
    for item in report.get("actions_taken") or []:
        if not isinstance(item, dict):
            continue
        names = [
            str(detail.get("name") or "").strip()
            for detail in item.get("actions_details") or []
            if isinstance(detail, dict) and detail.get("name")
        ]
        summary = plain_text(item.get("summary"), 600)
        if not names and not summary:
            continue
        organization = str(item.get("organization") or "").strip()
        actions.append(
            {
                "by": _ORGANIZATIONS.get(organization, organization),
                "actions": names,
                "summary": summary,
            }
        )
    summary = {
        "number": report.get("fr_num"),
        "report_date": str(report.get("report_date") or "")[:10],
        "event_start": str(report.get("start_date") or "")[:10],
        "title": str(report.get("title") or "").strip()[:200],
        "description": plain_text(report.get("description"), FIELD_REPORT_TEXT_LIMIT),
        "figures": figures,
        "actions_taken": actions,
        "actions_by_others": plain_text(report.get("actions_others"), 1200),
        "other_sources": plain_text(report.get("other_sources"), 300),
        "notes_ns": plain_text(report.get("notes_ns"), 800),
        "notes_health": plain_text(report.get("notes_health"), 800),
        "notes_socioeconomic": plain_text(report.get("notes_socioeco"), 800),
        "national_society_requested_assistance": report.get("ns_request_assistance"),
        "international_assistance_requested": report.get("request_assistance"),
    }
    return {key: value for key, value in summary.items() if value not in ("", None, [], {})}


def field_reports(report_ids: list[int], http_get: Callable | None = None) -> list[dict]:
    getter = http_get or _fast_get
    root = GO_API_ROOT.rstrip("/")

    def read(report_id: int) -> dict | None:
        try:
            payload = getter(f"{root}/field-report/{int(report_id)}/", None)
        except Exception as exc:
            logger.info("DREF field report %s could not be read: %s", report_id, exc)
            return None
        return field_report_summary(payload) if isinstance(payload, dict) else None

    if not report_ids:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(report_ids))) as pool:
        found = [item for item in pool.map(read, report_ids) if item]
    found.sort(key=lambda item: (item.get("report_date") or "", item.get("number") or 0))
    return found


def _search_queries(operation) -> list[str]:
    place = " ".join(part for part in (operation.country_name, operation.hazard) if part).strip()
    name = (operation.disaster_name or "").strip()
    return [
        f"{name or place} situation overview people affected damage humanitarian needs".strip(),
        f"{place} humanitarian response government ICRC UN OCHA Red Cross Red Crescent actions coordination".strip(),
    ]


def _default_search(query: str, filters: dict, user_id: int | None, top_k: int) -> list[dict]:
    from app.services.ai.documents.vector_store import AIVectorStore

    return AIVectorStore().hybrid_search(
        query_text=query,
        top_k=top_k,
        filters=filters,
        user_id=user_id,
        user_role=None,
    )


def _not_before(operation) -> date | None:
    start = operation.date_of_disaster or operation.start_date
    return None if start is None else start - timedelta(days=30)


def databank_documents(operation, user_id: int | None, search: Callable | None = None) -> list[dict]:
    """Excerpts the reader may open. Someone without a user (a scheduled job) sees public documents only."""
    if not (operation.country_id or operation.country_name):
        return []
    filters: dict[str, Any] = {}
    if operation.country_id:
        filters["country_id"] = int(operation.country_id)
    else:
        filters["country_name"] = operation.country_name
    run = search or _default_search
    floor = _not_before(operation)
    seen: set[Any] = set()
    ranked: list[dict] = []
    for query in _search_queries(operation):
        try:
            results = run(query, filters, user_id, 5) or []
        except Exception as exc:
            logger.info("DREF document search failed for %s: %s", operation.appeal_code, exc)
            # A failed query leaves the session unusable until it is rolled back.
            db.session.rollback()
            continue
        for row in results:
            chunk_id = row.get("chunk_id") or (row.get("document_id"), row.get("chunk_index"))
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            published = as_date(row.get("document_date"))
            if floor is not None and published is not None and published < floor:
                continue
            ranked.append(row)
    ranked.sort(key=lambda row: float(row.get("combined_score") or 0.0), reverse=True)
    documents = []
    for row in ranked[:DOCUMENT_COUNT]:
        excerpt = plain_text(row.get("content"), DOCUMENT_EXCERPT_LIMIT)
        if not excerpt:
            continue
        item = {
            "title": str(row.get("document_title") or "").strip()[:200],
            "organization": str(row.get("source_organization") or "").strip()[:120],
            "date": str(row.get("document_date") or "")[:10],
            "page": row.get("page_number"),
            "excerpt": excerpt,
        }
        documents.append({key: value for key, value in item.items() if value not in ("", None)})
    return documents


def previous_report(operation) -> dict | None:
    """The newest earlier draft's chapters, so the new one carries forward what is still true."""
    from plugins.dref_monitoring.models import DrefDraft
    from plugins.dref_monitoring.services.drafts import narrative_map

    rows = (
        DrefDraft.query.filter_by(operation_id=operation.id)
        .order_by(DrefDraft.id.desc())
        .limit(6)
        .all()
    )
    for row in rows:
        status = row.status or "draft"
        if status == "draft" and not row.edited_body:
            continue
        chapters = {
            key: text
            for key, text in narrative_map(row).items()
            if key in SECTION_KEYS and str(text or "").strip()
        }
        if not chapters:
            continue
        return {
            "kind": row.report_kind,
            "status": status,
            "written_on": row.created_at.date().isoformat() if row.created_at else "",
            "chapters": {key: plain_text(text, 1800) for key, text in chapters.items()},
        }
    return None


def latest_application(operation) -> tuple[dict | None, dict | None]:
    """The written application of the latest approved stage, and of the first one."""
    from plugins.dref_monitoring.models import DrefBaseline

    rows = DrefBaseline.query.filter_by(operation_id=operation.id).order_by(DrefBaseline.id).all()
    stored = [row for row in rows if isinstance(row.application, dict) and row.application.get("narrative")]
    if not stored:
        return None, None
    latest = next((row for row in reversed(stored) if row.is_latest), stored[-1])
    first = stored[0]
    return latest.application, (None if first.id == latest.id else first.application)


def _clip_application(narrative: dict, budget: int) -> dict:
    """Keep the prompt bounded. Long fields are cut on a sentence."""
    clipped: dict[str, Any] = {}
    for key, value in narrative.items():
        if isinstance(value, str):
            clipped[key] = plain_text(value, budget)
        elif isinstance(value, list):
            rows = []
            for item in value:
                if isinstance(item, dict):
                    rows.append(
                        {
                            name: plain_text(text, budget) if isinstance(text, str) else text
                            for name, text in item.items()
                        }
                    )
                else:
                    rows.append(item)
            clipped[key] = rows
        else:
            clipped[key] = value
    return clipped


def load_context(
    operation,
    actor=None,
    *,
    http_get: Callable | None = None,
    search: Callable | None = None,
    progress: Callable | None = None,
) -> dict:
    """Everything outside the monitoring tables that the model may use.

    A source that fails is left out. ``progress`` is called between sources, outside
    the guarded blocks, so a listener that raises to cancel stops the load.
    """
    context: dict[str, Any] = {}
    latest, first = None, None
    _say(progress, "background", "Reading the approved application and the previous draft.", 12)
    try:
        latest, first = latest_application(operation)
    except Exception:
        logger.warning("DREF application text unavailable for %s", operation.appeal_code, exc_info=True)
    emergency: dict = {}
    if latest:
        emergency = dict(latest.get("context") or {})
        context["approved_application"] = _clip_application(latest.get("narrative") or {}, 3500)
        if first and first.get("narrative"):
            original = first["narrative"]
            context["original_application"] = _clip_application(
                {
                    key: original[key]
                    for key in ("event_description", "event_scope", "who_targeted")
                    if original.get(key)
                },
                1800,
            )
    report_ids = [int(item) for item in emergency.pop("field_report_ids", []) or [] if str(item).isdigit()]
    if emergency:
        context["emergency"] = emergency
    _say(progress, "field_reports", "Reading recent GO field reports.", 20)
    try:
        reports = field_reports(report_ids, http_get)
    except Exception:
        logger.warning("DREF field reports unavailable for %s", operation.appeal_code, exc_info=True)
        reports = []
    if reports:
        context["field_reports"] = reports
    user_id = getattr(actor, "user_id", None)
    _say(progress, "documents", "Searching Databank documents.", 32)
    try:
        documents = databank_documents(operation, user_id, search)
    except Exception:
        logger.warning("DREF Databank documents unavailable for %s", operation.appeal_code, exc_info=True)
        documents = []
    if documents:
        context["databank_documents"] = documents
    try:
        earlier = previous_report(operation)
    except Exception:
        logger.warning("DREF previous report unavailable for %s", operation.appeal_code, exc_info=True)
        earlier = None
    if earlier:
        context["previous_report"] = earlier
    return context
