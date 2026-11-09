"""Public IFRC GO operation documents for one country.

The GO list endpoints do not filter appeal documents by country. Two queries
that do work:

* ``GET /api/v2/appeal_document/?search=MDR{iso2}`` — emergency appeals,
  operations updates, DREF, revisions and final reports. Rows are kept only
  when ``iso`` matches.
* ``GET /api/v2/event/?countries__in={go_country_id}`` plus
  ``GET /api/v2/situation_report/?search={country name}`` — public situation
  reports whose event is actually in that country.

A failed section is omitted. Callers still receive appeal documents when the
situation-report lookup fails.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

GO_API_ROOT = "https://goadmin.ifrc.org/api/v2"
_PAGE_LIMIT = 200
_MAX_PAGES = 3
_TIMEOUT_SECONDS = 12
_CACHE_TTL_SECONDS = 10 * 60

_ALLOWED_HOSTS = frozenset(
    {
        "go-api.ifrc.org",
        "go.ifrc.org",
        "goadmin.ifrc.org",
        "prddsgofilestorage.blob.core.windows.net",
        "prddsgolocstor01.blob.core.windows.net",
    }
)

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = Lock()


def reset_go_documents_cache_for_tests() -> None:
    global _bulk_cache
    with _cache_lock:
        _cache.clear()
        _bulk_cache = None


def public_document_url(raw: Any) -> str | None:
    """Https URL on a known GO document host, or None."""
    text = str(raw or "").strip()
    if not text.lower().startswith("https://"):
        return None
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS or parsed.username or parsed.password:
        return None
    if parsed.port not in (None, 443):
        return None
    return text


def _year(raw: Any) -> int | None:
    text = str(raw or "")
    if len(text) < 4 or not text[:4].isdigit():
        return None
    year = int(text[:4])
    if 1990 <= year <= 2100:
        return year
    return None


def _row(
    title: str,
    url: str,
    document_type: str,
    created_at: Any,
    *,
    emergency: str | None = None,
    emergency_code: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "filename": None,
        "url": url,
        "thumbnail": None,
        "year": _year(created_at),
        "document_type": document_type,
        "language": None,
        "language_code": None,
        "emergency": emergency,
        "emergency_code": emergency_code,
    }


def _appeal_code(item: dict[str, Any]) -> str | None:
    appeal = item.get("appeal")
    if not isinstance(appeal, dict):
        return None
    code = str(appeal.get("code") or "").strip()
    return code or None


def apply_appeal_names(documents: list[dict[str, Any]], names: dict[str, str]) -> None:
    """Fill ``emergency`` from official appeal names. Unknown codes keep the code."""
    for document in documents:
        code = document.get("emergency_code")
        if not isinstance(code, str) or not code or code.startswith("event:"):
            continue
        document["emergency"] = names.get(code) or code


def parse_appeal_documents(items: Any, iso2: str) -> list[dict[str, Any]]:
    """Appeal PDFs whose ``iso`` is this country. Other rows are ignored."""
    if not isinstance(items, list):
        return []
    wanted = (iso2 or "").strip().upper()
    if len(wanted) != 2:
        return []
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("iso") or "").strip().upper() != wanted:
            continue
        url = public_document_url(item.get("document_url") or item.get("document"))
        if not url or url in seen:
            continue
        seen.add(url)
        document_type = str(item.get("type") or "").strip() or "Appeal document"
        title = str(item.get("name") or "").strip() or document_type
        code = _appeal_code(item)
        documents.append(
            _row(
                title,
                url,
                document_type,
                item.get("created_at"),
                emergency_code=code,
            )
        )
    return documents


def _event_iso3s(row: dict[str, Any]) -> set[str]:
    countries = row.get("countries") or []
    if not isinstance(countries, list):
        return set()
    codes: set[str] = set()
    for country in countries:
        if isinstance(country, dict):
            code = str(country.get("iso3") or "").strip().upper()
            if code:
                codes.add(code)
    return codes


def events_for_country(items: Any, iso3: str) -> dict[int, str]:
    """Event id to name for rows that list ``iso3``. An unfiltered page yields nothing."""
    if not isinstance(items, list):
        return {}
    wanted = (iso3 or "").strip().upper()
    events: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict) or wanted not in _event_iso3s(item):
            continue
        try:
            event_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        events[event_id] = str(item.get("name") or "").strip()
    return events


def event_ids_for_country(items: Any, iso3: str) -> set[int]:
    """Event ids on this page that list ``iso3``. An unfiltered page yields nothing."""
    return set(events_for_country(items, iso3))


def parse_situation_reports(
    items: Any,
    events: set[int] | dict[int, str],
) -> list[dict[str, Any]]:
    """Public situation reports for the given events.

    A dict maps event id to the emergency name. A set groups by id only.
    """
    names = events if isinstance(events, dict) else {}
    event_ids = set(events)
    if not isinstance(items, list) or not event_ids:
        return []
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("visibility") != 3:
            continue
        try:
            event_id = int(item.get("event"))
        except (TypeError, ValueError):
            continue
        if event_id not in event_ids:
            continue
        url = public_document_url(item.get("document_url") or item.get("document"))
        if not url or url in seen:
            continue
        seen.add(url)
        type_info = item.get("type") if isinstance(item.get("type"), dict) else {}
        document_type = str(type_info.get("type") or "").strip() or "Situation Report"
        title = str(item.get("name") or "").strip() or document_type
        emergency = str(names.get(event_id) or "").strip() or None
        documents.append(
            _row(
                title,
                url,
                document_type,
                item.get("created_at"),
                emergency=emergency,
                emergency_code=f"event:{event_id}",
            )
        )
    return documents


def _get_page(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(
        f"{GO_API_ROOT}{path}",
        params=params,
        timeout=_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"GO {path} did not return an object")
    return payload


def _iter_results(
    session: requests.Session,
    path: str,
    params: dict[str, Any],
    pages: int | None = None,
):
    offset = 0
    page_limit = _MAX_PAGES if pages is None else pages
    for _ in range(page_limit):
        payload = _get_page(
            session,
            path,
            {**params, "format": "json", "limit": _PAGE_LIMIT, "offset": offset},
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            break
        yield results
        if not payload.get("next") or len(results) < _PAGE_LIMIT:
            break
        offset += _PAGE_LIMIT


def _appeal_documents(session: requests.Session, iso2: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in _iter_results(session, "/appeal_document/", {"search": f"MDR{iso2}"}):
        for document in parse_appeal_documents(page, iso2):
            if document["url"] in seen:
                continue
            seen.add(document["url"])
            documents.append(document)
    return documents


def _go_country(session: requests.Session, iso3: str) -> tuple[int, str] | None:
    payload = _get_page(
        session,
        "/country/",
        {"format": "json", "limit": 20, "search": iso3},
    )
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("iso3") or "").strip().upper() != iso3:
            continue
        try:
            go_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            return go_id, name
    return None


def _situation_reports(session: requests.Session, iso3: str) -> list[dict[str, Any]]:
    country = _go_country(session, iso3)
    if country is None:
        return []
    go_id, go_name = country
    events: dict[int, str] = {}
    for page in _iter_results(session, "/event/", {"countries__in": go_id}):
        matched = events_for_country(page, iso3)
        if not matched:
            break
        events.update(matched)
    if not events:
        return []
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in _iter_results(session, "/situation_report/", {"search": go_name}):
        for document in parse_situation_reports(page, events):
            if document["url"] in seen:
                continue
            seen.add(document["url"])
            documents.append(document)
    return documents


def _needs_appeal_names(documents: list[dict[str, Any]]) -> bool:
    for document in documents:
        code = document.get("emergency_code")
        if isinstance(code, str) and code and not code.startswith("event:"):
            return True
    return False


def _appeal_names(session: requests.Session, iso3: str) -> dict[str, str]:
    """Official appeal names for one country, keyed by appeal code."""
    names: dict[str, str] = {}
    for page in _iter_results(session, "/appeal/", {"country__iso3": iso3}):
        for item in page:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            if code and name:
                names[code] = name
    return names


def fetch_go_operation_documents(*, iso2: str, iso3: str) -> tuple[list[dict[str, Any]], bool]:
    """Return ``(documents, available)``.

    ``available`` is false only when both the appeal-document and situation-report
    lookups fail. An empty list with ``available`` true means GO had nothing.
    """
    iso2 = (iso2 or "").strip().upper()
    iso3 = (iso3 or "").strip().upper()
    if len(iso2) != 2 or len(iso3) != 3:
        return [], True

    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(iso3)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return list(cached[1]), True

    documents: list[dict[str, Any]] = []
    failures = 0
    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"}
        )
        try:
            documents.extend(_appeal_documents(session, iso2))
        except (requests.RequestException, ValueError) as exc:
            failures += 1
            logger.warning("GO appeal documents for %s failed: %s", iso3, exc)
        try:
            documents.extend(_situation_reports(session, iso3))
        except (requests.RequestException, ValueError) as exc:
            failures += 1
            logger.warning("GO situation reports for %s failed: %s", iso3, exc)
        if _needs_appeal_names(documents):
            try:
                apply_appeal_names(documents, _appeal_names(session, iso3))
            except (requests.RequestException, ValueError) as exc:
                logger.warning("GO appeal names for %s failed: %s", iso3, exc)
                apply_appeal_names(documents, {})

    if failures == 2:
        return [], False

    documents.sort(key=lambda row: (-(row["year"] or 0), row["title"].lower()))
    with _cache_lock:
        _cache[iso3] = (time.monotonic(), documents)
    return documents, True


# Pages of the unfiltered GO lists. 20 * 200 rows is enough for the offline pack
# without walking every country.
_BULK_PAGES = 20
_bulk_cache: tuple[float, dict[str, list[dict[str, Any]]]] | None = None


def group_go_documents(
    appeal_items: list,
    event_items: list,
    report_items: list,
    appeal_name_items: list,
    iso2_to_iso3: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Split unfiltered GO pages into the per-country document list.

    Appeal rows join on ISO2. Situation reports join through the event's
    countries. Appeal names replace the code when the worldwide appeal list
    has one.
    """
    by_iso3: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}

    def add(iso3: str, document: dict[str, Any]) -> None:
        if not iso3:
            return
        urls = seen.setdefault(iso3, set())
        url = document.get("url")
        if not isinstance(url, str) or not url or url in urls:
            return
        urls.add(url)
        by_iso3.setdefault(iso3, []).append(document)

    for item in appeal_items:
        if not isinstance(item, dict):
            continue
        iso2 = str(item.get("iso") or "").strip().upper()
        iso3 = iso2_to_iso3.get(iso2, "")
        if not iso3:
            continue
        for document in parse_appeal_documents([item], iso2):
            add(iso3, document)

    event_names: dict[int, str] = {}
    event_countries: dict[int, set[str]] = {}
    for item in event_items:
        if not isinstance(item, dict):
            continue
        try:
            event_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        event_names[event_id] = str(item.get("name") or "").strip()
        event_countries[event_id] = _event_iso3s(item)

    for item in report_items:
        if not isinstance(item, dict):
            continue
        try:
            event_id = int(item.get("event"))
        except (TypeError, ValueError):
            continue
        countries = event_countries.get(event_id) or set()
        if not countries:
            continue
        name = event_names.get(event_id) or ""
        for document in parse_situation_reports([item], {event_id: name}):
            for iso3 in countries:
                add(iso3, document)

    names_by_iso3: dict[str, dict[str, str]] = {}
    for item in appeal_name_items:
        if not isinstance(item, dict):
            continue
        country = item.get("country") if isinstance(item.get("country"), dict) else {}
        iso3 = str(country.get("iso3") or "").strip().upper()
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if iso3 and code and name:
            names_by_iso3.setdefault(iso3, {})[code] = name

    for iso3, documents in by_iso3.items():
        apply_appeal_names(documents, names_by_iso3.get(iso3, {}))
        documents.sort(key=lambda row: (-(row["year"] or 0), row["title"].lower()))
    return by_iso3


def _collect_results(
    session: requests.Session,
    path: str,
    params: dict[str, Any],
    *,
    pages: int,
) -> list:
    rows: list = []
    for page in _iter_results(session, path, params, pages=pages):
        rows.extend(page)
    return rows


def fetch_go_documents_by_iso3(
    iso2_to_iso3: dict[str, str],
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    """Every country's GO document list from the unfiltered GO feeds.

    One pass over appeal documents, events, situation reports, and appeals.
    ``available`` is false when both document feeds fail. Countries with no
    rows are omitted.
    """
    global _bulk_cache
    now = time.monotonic()
    with _cache_lock:
        if _bulk_cache is not None and now - _bulk_cache[0] < _CACHE_TTL_SECONDS:
            return _bulk_cache[1], True

    appeal_items: list = []
    event_items: list = []
    report_items: list = []
    name_items: list = []
    appeal_failed = False
    reports_failed = False
    try:
        with requests.Session() as session:
            session.headers.update(
                {"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"}
            )
            try:
                appeal_items = _collect_results(
                    session, "/appeal_document/", {}, pages=_BULK_PAGES
                )
            except (requests.RequestException, ValueError) as exc:
                appeal_failed = True
                logger.warning("GO appeal document list failed: %s", exc)
            try:
                event_items = _collect_results(session, "/event/", {}, pages=_BULK_PAGES)
                report_items = _collect_results(
                    session, "/situation_report/", {}, pages=_BULK_PAGES
                )
            except (requests.RequestException, ValueError) as exc:
                reports_failed = True
                logger.warning("GO situation report list failed: %s", exc)
            try:
                name_items = _collect_results(session, "/appeal/", {}, pages=_BULK_PAGES)
            except (requests.RequestException, ValueError) as exc:
                logger.warning("GO appeal name list failed: %s", exc)
    except requests.RequestException as exc:
        logger.warning("GO document list failed: %s", exc)
        return {}, False

    if appeal_failed and reports_failed:
        return {}, False

    grouped = group_go_documents(
        appeal_items,
        event_items,
        report_items,
        name_items,
        iso2_to_iso3,
    )
    with _cache_lock:
        _bulk_cache = (time.monotonic(), grouped)
    return grouped, True
