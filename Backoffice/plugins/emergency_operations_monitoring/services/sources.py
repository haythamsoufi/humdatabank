"""Sources the narrative model is allowed to name, and the list the page can show.

The model sees a catalog of ids, titles and dates. It does not see URLs. A reply
may only cite those ids. Titles, dates and links on the page come from the catalog
we built, never from text the model wrote.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from plugins.emergency_operations_monitoring.constants import SECTION_KEYS

KINDS = (
    "operation",
    "monitoring",
    "approved_application",
    "original_application",
    "emergency",
    "field_report",
    "document",
    "previous_report",
)

_APPROVED_REPORT = {"validated", "submitted"}
_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OPERATION = re.compile(r"^/emergency-operations/operations/\d+(?:/drafts/\d+)?(?:\?tab=reporting)?$")
_ASSIGNMENT = re.compile(r"^/assignment/\d+$")
_DOWNLOAD = re.compile(r"^/api/ai/documents/\d+/download$")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MAX_PER_CHAPTER = 24


def model_object(text: str | None) -> dict | None:
    """The JSON object in a model reply, or None when the reply is prose."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def source_claims(text: str | None) -> list[dict]:
    """The sources array from a reply. Anything that is not an object is dropped."""
    data = model_object(text)
    raw = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def safe_href(value) -> str:
    """A link we are willing to render: an http(s) URL, a document download, or an operation page."""
    text = str(value or "").strip()
    if not text or len(text) > 2000 or any(mark in text for mark in ' \t\r\n"\'<>\\'):
        return ""
    if _DOWNLOAD.match(text) or _OPERATION.match(text) or _ASSIGNMENT.match(text):
        return text
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.username and not parsed.password:
        return text
    return ""


def _int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _date(value) -> str:
    text = str(value or "").strip()[:10]
    return text if _DATE.match(text) else ""


def _pretty_date(value) -> str:
    text = _date(value)
    if not text:
        return ""
    year, month, day = (int(part) for part in text.split("-"))
    return f"{day} {_MONTHS[month - 1]} {year}"


def _operation_locator(payload: dict) -> str:
    """The headline figures that belong to the operation record, not to a monitoring period."""
    bits = []
    amount = payload.get("total_approved_chf")
    if amount not in (None, ""):
        bits.append(f"CHF {amount}")
    start, end = _pretty_date(payload.get("start_date")), _pretty_date(payload.get("end_date"))
    if start and end:
        bits.append(f"{start} to {end}")
    targeted = payload.get("people_targeted")
    if targeted not in (None, ""):
        bits.append(f"{targeted} people targeted")
    return " · ".join(bits)


def _add(items: list[dict], by_id: dict[str, dict], row: dict) -> None:
    ref = str(row.get("id") or "")
    if not _ID.match(ref) or ref in by_id:
        return
    record = {
        "id": ref,
        "kind": row.get("kind") if row.get("kind") in KINDS else "document",
        "title": _text(row.get("title"), 200) or ref,
        "date": _date(row.get("date")),
        "locator": _text(row.get("locator"), 160),
        "url": safe_href(row.get("url")),
    }
    items.append(record)
    by_id[ref] = record


def stamp_catalog(payload: dict, operation_id: int | None = None) -> list[dict]:
    """Attach ``source_catalog`` (no URLs) to the payload the model reads.

    Links stay on ``_source_links``, which the user message leaves out. Link-bearing
    fields are removed from the context so the model cannot copy a URL into the text.
    Calling this twice is safe: the second call keeps the links from the first.
    """
    current_draft = _int(payload.pop("draft_id", None))
    if isinstance(payload.get("_source_links"), dict) and isinstance(payload.get("source_catalog"), list):
        return _catalog_from_stamped(payload)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    items: list[dict] = []
    by_id: dict[str, dict] = {}
    operation = _int(operation_id)
    appeal = _text(payload.get("appeal_code"), 40)
    _add(
        items,
        by_id,
        {
            "id": "operation",
            "kind": "operation",
            "title": f"{appeal} operation record" if appeal else "Operation record",
            "locator": _operation_locator(payload),
            "url": f"/emergency-operations/operations/{operation}" if operation else "",
        },
    )
    cited_reports = []
    for report in payload.get("monitoring_reports") or []:
        if not isinstance(report, dict):
            continue
        _add(
            items,
            by_id,
            {
                "id": report.get("id"),
                "kind": "monitoring",
                "title": report.get("title"),
                "date": report.get("date"),
                "locator": report.get("locator"),
                "url": report.get("url"),
            },
        )
        cited_reports.append({key: report[key] for key in ("id", "title", "date", "locator", "status") if report.get(key)})
    if cited_reports:
        payload["monitoring_reports"] = cited_reports
    else:
        payload.pop("monitoring_reports", None)
    emergency = context.get("emergency") if isinstance(context.get("emergency"), dict) else {}
    event_id = _int(emergency.get("event_id"))
    event_url = f"https://go.ifrc.org/emergencies/{event_id}/details" if event_id else ""
    event_name = _text(emergency.get("event_name"), 200)
    if emergency:
        _add(
            items,
            by_id,
            {
                "id": "emergency",
                "kind": "emergency",
                "title": event_name or "Emergency",
                "date": emergency.get("event_start"),
                "locator": emergency.get("country") or "",
                "url": event_url,
            },
        )
    if isinstance(context.get("approved_application"), dict) and context.get("approved_application"):
        _add(
            items,
            by_id,
            {
                "id": "approved-application",
                "kind": "approved_application",
                "title": "Approved application",
                "locator": event_name,
                "url": event_url,
            },
        )
    if isinstance(context.get("original_application"), dict) and context.get("original_application"):
        _add(
            items,
            by_id,
            {
                "id": "original-application",
                "kind": "original_application",
                "title": "Original application",
                "url": event_url,
            },
        )
    for index, report in enumerate(context.get("field_reports") or [], start=1):
        if not isinstance(report, dict):
            continue
        report_id = _int(report.pop("id", None))
        ref = f"fr-{report_id}" if report_id else f"fr-n{index}"
        report["ref"] = ref
        number = report.get("number")
        title = _text(report.get("title"), 200)
        if not title:
            title = f"Field report {number}" if number else "Field report"
        locator = f"No. {number}" if number and report.get("title") else ""
        _add(
            items,
            by_id,
            {
                "id": ref,
                "kind": "field_report",
                "title": title,
                "date": report.get("report_date"),
                "locator": locator,
            },
        )
    _add_documents(items, by_id, context.get("databank_documents") or [])
    earlier = context.get("previous_report") if isinstance(context.get("previous_report"), dict) else None
    if earlier:
        draft_id = _int(earlier.pop("draft_id", None))
        status = str(earlier.get("status") or "")
        # An open draft, and the draft being written, are not a previous report.
        if draft_id and draft_id != current_draft and status in _APPROVED_REPORT:
            label = "Final report" if earlier.get("kind") == "final_report" else "Operational update"
            draft_url = f"/emergency-operations/operations/{operation}/drafts/{draft_id}" if operation else ""
            _add(
                items,
                by_id,
                {
                    "id": "previous-report",
                    "kind": "previous_report",
                    "title": f"{label}, {status}",
                    "date": earlier.get("written_on"),
                    "locator": "Approved report",
                    "url": draft_url,
                },
            )
        elif isinstance(context, dict):
            context.pop("previous_report", None)
    payload["source_catalog"] = [
        {key: row[key] for key in ("id", "kind", "title", "date", "locator") if row.get(key)} for row in items
    ]
    payload["_source_links"] = {row["id"]: row["url"] for row in items if row.get("url")}
    return items


def _catalog_from_stamped(payload: dict) -> list[dict]:
    """Rebuild the full catalog after a second stamp, keeping the links already stored."""
    links = payload.get("_source_links") if isinstance(payload.get("_source_links"), dict) else {}
    items = []
    for row in payload.get("source_catalog") or []:
        if not isinstance(row, dict) or not _ID.match(str(row.get("id") or "")):
            continue
        full = dict(row)
        full["url"] = safe_href(links.get(row["id"]))
        full.setdefault("date", "")
        full.setdefault("locator", "")
        items.append(full)
    return items


def _add_documents(items: list[dict], by_id: dict[str, dict], documents) -> None:
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for index, doc in enumerate(documents, start=1):
        if not isinstance(doc, dict):
            continue
        doc_id = _int(doc.pop("document_id", None))
        ref = f"doc-{doc_id}" if doc_id else f"doc-x{index}"
        doc["ref"] = ref
        url = safe_href(doc.pop("source_url", ""))
        has_file = bool(doc.pop("has_file", False))
        if not url and doc_id and has_file:
            url = f"/api/ai/documents/{doc_id}/download"
        page = _int(doc.get("page"))
        slot = grouped.get(ref)
        if slot is None:
            slot = {
                "id": ref,
                "kind": "document",
                "title": _text(doc.get("title"), 200) or "Document",
                "date": doc.get("date"),
                "locator_org": _text(doc.get("organization"), 120),
                "pages": [],
                "url": url,
            }
            grouped[ref] = slot
            order.append(ref)
        elif url and not slot["url"]:
            slot["url"] = url
        if page and page not in slot["pages"]:
            slot["pages"].append(page)
    for ref in order:
        slot = grouped[ref]
        pages = slot.pop("pages")
        org = slot.pop("locator_org")
        if len(pages) == 1:
            page_text = f"p. {pages[0]}"
        elif pages:
            page_text = "p. " + ", ".join(str(number) for number in pages[:6])
        else:
            page_text = ""
        slot["locator"] = ", ".join(part for part in (org, page_text) if part)
        _add(items, by_id, slot)


def resolve_sources(claims: list, catalog: list[dict], chapters: set[str]) -> list[dict]:
    """Keep claims whose id and chapter we know. The link and the title come from the catalog."""
    by_id = {row["id"]: row for row in catalog if isinstance(row, dict) and row.get("id")}
    allowed = {key for key in chapters if key in SECTION_KEYS}
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        ref = str(claim.get("id") or "").strip().lower()
        chapter = str(claim.get("chapter") or "").strip()
        base = by_id.get(ref)
        if base is None or chapter not in allowed or (chapter, ref) in seen:
            continue
        if counts.get(chapter, 0) >= _MAX_PER_CHAPTER:
            continue
        seen.add((chapter, ref))
        counts[chapter] = counts.get(chapter, 0) + 1
        found.append(_row(base, chapter, claim.get("used_for")))
    return found


def _row(base: dict, chapter: str, used_for) -> dict:
    return {
        "id": base["id"],
        "chapter": chapter,
        "kind": base.get("kind") or "document",
        "title": base.get("title") or base["id"],
        "date": base.get("date") or "",
        "locator": base.get("locator") or "",
        "url": safe_href(base.get("url")),
        "used_for": _text(used_for, 300),
    }


def accept_chapter_sources(rows, chapter: str) -> list[dict]:
    """Sources the editor sends back after a rewrite. URLs that are not links we issued are dropped."""
    if chapter not in SECTION_KEYS or not isinstance(rows, list):
        return []
    found = []
    seen = set()
    for item in rows[:_MAX_PER_CHAPTER]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("id") or "").strip().lower()
        kind = item.get("kind")
        if not _ID.match(ref) or kind not in KINDS or ref in seen:
            continue
        seen.add(ref)
        title = _text(item.get("title"), 200) or ref
        found.append(
            {
                "id": ref,
                "chapter": chapter,
                "kind": kind,
                "title": title,
                "date": _date(item.get("date")),
                "locator": _text(item.get("locator"), 160),
                "url": safe_href(item.get("url")),
                "used_for": _text(item.get("used_for"), 300),
            }
        )
    return found


def _stored_rows(draft, name: str) -> list:
    stored = getattr(draft, "sections", None)
    rows = stored.get(name) if isinstance(stored, dict) else None
    return rows if isinstance(rows, list) else []


def narrative_sources(draft, *, original: bool = False) -> list[dict]:
    """Sources saved on the draft, checked again so a stored value cannot become a bad link."""
    name = "narrative_sources_original" if original else "narrative_sources"
    rows = []
    for item in _stored_rows(draft, name):
        if not isinstance(item, dict):
            continue
        chapter = str(item.get("chapter") or "")
        rows.extend(accept_chapter_sources([item], chapter))
    return rows


def sources_state(draft) -> str:
    """``listed`` when sources are saved, ``none`` when a reply recorded an empty list, ``unrecorded`` before that."""
    stored = getattr(draft, "sections", None)
    if not isinstance(stored, dict) or "narrative_sources" not in stored:
        return "unrecorded"
    return "listed" if narrative_sources(draft) else "none"


def remember_sources(draft, rows: list[dict], *, original: bool) -> None:
    """Replace the saved source list. ``original`` is what Restore puts back."""
    from sqlalchemy.orm.attributes import flag_modified

    stored = dict(draft.sections or {})
    stored["narrative_sources"] = rows
    if original:
        stored["narrative_sources_original"] = list(rows)
    draft.sections = stored
    flag_modified(draft, "sections")


def replace_chapter_sources(draft, updates: dict[str, list]) -> None:
    """Replace the sources of the named chapters and leave every other chapter as it is."""
    from sqlalchemy.orm.attributes import flag_modified

    if not updates:
        return
    kept = [row for row in narrative_sources(draft) if row.get("chapter") not in updates]
    for chapter, rows in updates.items():
        kept.extend(accept_chapter_sources(rows, chapter))
    stored = dict(draft.sections or {})
    stored["narrative_sources"] = kept
    draft.sections = stored
    flag_modified(draft, "sections")
