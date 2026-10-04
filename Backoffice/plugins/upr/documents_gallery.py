"""Public landscape gallery of IFRC GO unified plans and reports.

Same catalogue as the mobile app's unified-planning documents screen: PublicSiteAppeals
types Plan (1851), Mid-Year Report (10009), and Annual Report (10011). The page is
meant to be opened directly or iframed from a Power BI HTML visual
(``?format=powerbi`` returns the iframe snippet).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlencode

import requests
from flask import Response, render_template, request, url_for
from markupsafe import escape

from app.utils.client_ip import get_client_ip
from app.utils.constants import APPEALS_TYPE_DEFAULT_IDS_STR, APPEALS_TYPE_DISPLAY_NAMES
from app.utils.external_url_validation import validate_allowlisted_https_url
from app.utils.rate_limiting import rate_limit
from app.utils.session_persistence import suppress_session_cookie_for_request
from plugins.upr import bp

logger = logging.getLogger(__name__)

# Same rule as ``IFRC_APPEALS_TITLE_YEAR_RE`` and the mobile year expression:
# first 2000–2099 in AppealOrigType + AppealsName, with digit boundaries.
_TITLE_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_ISO2_SUFFIX_RE = re.compile(r"\s*\([A-Z]{2}\)\s*$")
_DOWNLOAD_FILE_RE = re.compile(r"/DownloadFile/(\d+)/", re.IGNORECASE)
_DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_IFRC_LIST_URL = (
    "https://go-api.ifrc.org/Api/PublicSiteAppeals"
    f"?AppealsTypeId={APPEALS_TYPE_DEFAULT_IDS_STR}"
)
_THUMB_PATH = "/api/mobile/v1/data/unified-planning-thumbnail"

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"
SORT_COUNTRY_AZ = "country_az"
SORT_COUNTRY_ZA = "country_za"
_SORTS = (SORT_NEWEST, SORT_OLDEST, SORT_COUNTRY_AZ, SORT_COUNTRY_ZA)
_SORT_LABELS = (
    (SORT_NEWEST, "Publish date: newest first"),
    (SORT_OLDEST, "Publish date: oldest first"),
    (SORT_COUNTRY_AZ, "Country: A–Z"),
    (SORT_COUNTRY_ZA, "Country: Z–A"),
)

_ERROR_MESSAGES = {
    "credentials": "IFRC documents are not available. Contact your administrator.",
    "auth": "Could not access IFRC documents. Contact your administrator if this continues.",
    "upstream": "Could not load documents from IFRC GO. Try again later.",
}

_CACHE_TTL_SECONDS = 10 * 60
_cached_at = 0.0
_cached_docs: list["UprGalleryDocument"] | None = None
_cache_lock = Lock()
_fetch_lock = Lock()


class UprGalleryUnavailable(Exception):
    """IFRC catalogue could not be loaded. ``code`` selects the visitor-facing message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class UprGalleryDocument:
    url: str
    title: str
    country_code: str | None
    country_name: str | None
    appeals_type_id: int | None
    document_type_label: str | None
    year: int | None
    published_at: datetime | None


@dataclass(frozen=True)
class GalleryFilters:
    q: str = ""
    country: str = ""
    type_id: int | None = None
    year: int | None = None
    sort: str = SORT_NEWEST


def reset_gallery_cache_for_tests() -> None:
    global _cached_at, _cached_docs
    with _cache_lock:
        _cached_at = 0.0
        _cached_docs = None


def filters_from_args(args: Mapping[str, str]) -> GalleryFilters:
    """Read the gallery query string. Unknown sort values fall back to newest."""
    q = " ".join((args.get("q") or "").split())[:120]
    country = " ".join((args.get("country") or "").split())[:200]
    type_id = _optional_int(args.get("type") or "")
    year = _optional_int(args.get("year") or "")
    if year is not None and not 2000 <= year <= 2099:
        year = None
    sort = (args.get("sort") or "").strip().lower()
    if sort not in _SORTS:
        sort = SORT_NEWEST
    return GalleryFilters(q=q, country=country, type_id=type_id, year=year, sort=sort)


def parse_ifrc_appeals(
    items: Any,
    *,
    url_ok: Callable[[str], bool] | None = None,
) -> list[UprGalleryDocument]:
    """Turn a PublicSiteAppeals payload into gallery rows.

    Mirrors the mobile ``IfrcUnifiedPlanningService.fetchDocuments`` rules: skip
    hidden rows, require a file URL, collapse duplicate ``/DownloadFile/{id}/``
    entries, and read the year from the title text.
    """
    if not isinstance(items, list):
        return []
    accept = url_ok or _allowlisted_document_url
    documents: list[UprGalleryDocument] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("Hidden") is True:
            continue
        base_dir = item.get("BaseDirectory") or ""
        base_file = item.get("BaseFileName") or ""
        if not str(base_dir).strip() or not str(base_file).strip():
            continue
        url = _normalize_url(f"{base_dir}{base_file}")
        if not url.lower().startswith("https://") or not accept(url):
            continue
        dedupe_key = _dedupe_key(url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        type_id = _as_int(item.get("AppealsTypeId"))
        orig = str(item.get("AppealOrigType") or "")
        name = str(item.get("AppealsName") or "")
        title = " ".join(name.split()) or " ".join(orig.split()) or "Document"
        year_match = _TITLE_YEAR_RE.search(f"{orig} {name}")
        year = int(year_match.group(1)) if year_match else None
        code = str(item.get("LocationCountryCode") or "").strip().upper() or None
        country = _country_name(item.get("LocationCountryName"))
        documents.append(
            UprGalleryDocument(
                url=url,
                title=title,
                country_code=code,
                country_name=country,
                appeals_type_id=type_id,
                document_type_label=_type_label(type_id),
                year=year,
                published_at=parse_appeals_date(item.get("AppealsDate")),
            )
        )
    return documents


def parse_appeals_date(raw: Any) -> datetime | None:
    """Parse IFRC ``AppealsDate`` (ISO, epoch seconds/ms, or .NET ``/Date(ms)/``)."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        value = int(round(raw))
        magnitude = abs(value)
        if magnitude >= 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if magnitude >= 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return None
    text = str(raw).strip()
    if not text:
        return None
    dotnet = _DOTNET_DATE_RE.search(text)
    if dotnet:
        return datetime.fromtimestamp(int(dotnet.group(1)) / 1000, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def document_matches(doc: UprGalleryDocument, filters: GalleryFilters) -> bool:
    if filters.country and (doc.country_name or "").strip().lower() != filters.country.strip().lower():
        return False
    if filters.type_id is not None and doc.appeals_type_id != filters.type_id:
        return False
    if filters.year is not None and doc.year != filters.year:
        return False
    if filters.q and filters.q.lower() not in _search_haystack(doc):
        return False
    return True


def sort_documents(docs: list[UprGalleryDocument], mode: str) -> list[UprGalleryDocument]:
    """Order rows the way the mobile list does. Missing dates and countries sort last."""

    def title(doc: UprGalleryDocument) -> str:
        return doc.title.lower()

    def country(doc: UprGalleryDocument) -> str:
        return (doc.country_name or "").strip().lower()

    if mode == SORT_OLDEST:
        missing = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(
            docs,
            key=lambda doc: (doc.published_at is None, doc.published_at or missing, title(doc)),
        )
    if mode == SORT_COUNTRY_AZ:
        return sorted(docs, key=lambda doc: ((not country(doc)), country(doc), title(doc)))
    if mode == SORT_COUNTRY_ZA:
        named = [doc for doc in docs if country(doc)]
        unnamed = [doc for doc in docs if not country(doc)]
        named.sort(key=title)
        named.sort(key=country, reverse=True)
        unnamed.sort(key=title)
        return named + unnamed
    return sorted(
        docs,
        key=lambda doc: (
            doc.published_at is None,
            -(doc.published_at.timestamp()) if doc.published_at is not None else 0,
            title(doc),
        ),
    )


def is_published_recently(published: datetime | None, now: datetime) -> bool:
    """True for the publication day, the two days before it, or one day ahead (UTC)."""
    if published is None:
        return False
    delta = (now.astimezone(timezone.utc).date() - published.astimezone(timezone.utc).date()).days
    return delta in (-1, 0, 1, 2)


def load_gallery_documents() -> list[UprGalleryDocument]:
    """Return the IFRC catalogue, reusing a short in-process cache."""
    fresh = _fresh_cache()
    if fresh is not None:
        return fresh
    with _fetch_lock:
        fresh = _fresh_cache()
        if fresh is not None:
            return fresh
        try:
            docs = _fetch_from_ifrc()
        except UprGalleryUnavailable:
            stale = _stale_cache()
            if stale is not None:
                logger.warning("UPR gallery serving stale catalogue after IFRC refresh failed")
                return stale
            raise
        _store_cache(docs)
        return list(docs)


def render_powerbi_snippet(page_url: str) -> str:
    """Iframe markup for the Power BI HTML Content visual."""
    safe_url = escape(page_url)
    return (
        "<!-- Power BI HTML visual: this iframe loads the live UPR documents gallery. -->"
        '<iframe title="Unified plans and reports" '
        f'src="{safe_url}" '
        'sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox" '
        'referrerpolicy="no-referrer" '
        'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;"></iframe>'
    )


def _gallery_rate_limit_response() -> Response:
    body = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Too many requests</title></head><body>"
        "<h1>Too many requests</h1>"
        "<p>Please wait a minute, then reload this page.</p>"
        "</body></html>"
    )
    response = Response(body, status=429, mimetype="text/html; charset=utf-8")
    response.headers["Retry-After"] = "60"
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/api/v1/upr/documents", methods=["GET"])
@rate_limit(
    requests_per_minute=120,
    key_func=lambda: f"upr_gallery:{get_client_ip()}",
    on_limit=_gallery_rate_limit_response,
)
def upr_documents_gallery():
    """Landscape HTML catalogue, or an iframe snippet when ``format=powerbi``."""
    _suppress_anonymous_session()
    filters = filters_from_args(request.args)
    if (request.args.get("format") or "").strip().lower() == "powerbi":
        return _html(render_powerbi_snippet(_page_url(filters)))

    error = None
    documents: list[UprGalleryDocument] = []
    try:
        documents = load_gallery_documents()
    except UprGalleryUnavailable as exc:
        error = _ERROR_MESSAGES.get(exc.code, _ERROR_MESSAGES["upstream"])
        logger.warning("UPR gallery unavailable: %s", exc.code)

    now = datetime.now(timezone.utc)
    body = render_template(
        "plugins/upr/documents_gallery.html",
        **_template_context(documents, filters, error=error, now=now),
    )
    return _html(body)


def _template_context(
    documents: list[UprGalleryDocument],
    filters: GalleryFilters,
    *,
    error: str | None,
    now: datetime,
) -> dict[str, Any]:
    ordered = sort_documents(documents, filters.sort)
    rows = [_row(doc, filters, now) for doc in ordered]
    countries = sorted(
        {(doc.country_name or "").strip() for doc in documents if (doc.country_name or "").strip()},
        key=str.lower,
    )
    types: dict[int, str] = {}
    years: set[int] = set()
    for doc in documents:
        if doc.appeals_type_id is not None:
            types[doc.appeals_type_id] = doc.document_type_label or f"Type {doc.appeals_type_id}"
        if doc.year is not None:
            years.add(doc.year)
    selected_country = _canonical_country(filters.country, countries)
    shown = sum(1 for row in rows if row["visible"])
    return {
        "documents": rows,
        "countries": countries,
        "types": sorted(types.items(), key=lambda item: item[1].lower()),
        "years": sorted(years, reverse=True),
        "sort_options": _SORT_LABELS,
        "filters": filters,
        "selected_country": selected_country,
        "shown": shown,
        "total": len(rows),
        "error": error,
        "form_action": url_for("upr.upr_documents_gallery"),
        "clear_url": url_for("upr.upr_documents_gallery"),
        "retry_url": _page_url(filters),
    }


def _row(doc: UprGalleryDocument, filters: GalleryFilters, now: datetime) -> dict[str, Any]:
    label = doc.document_type_label or "Document"
    country = (doc.country_name or "").strip()
    aria_bits = [doc.title, label]
    if country:
        aria_bits.append(country)
    if doc.year is not None:
        aria_bits.append(str(doc.year))
    return {
        "url": doc.url,
        "title": doc.title,
        "country_name": country,
        "type_label": label,
        "year": doc.year,
        "published_label": _published_label(doc.published_at),
        "published_sort": _published_sort(doc.published_at),
        "thumb_url": _THUMB_PATH + "?url=" + quote(doc.url, safe=""),
        "type_class": _type_css_class(doc.document_type_label),
        "fresh": is_published_recently(doc.published_at, now),
        "visible": document_matches(doc, filters),
        "search": _search_haystack(doc),
        "country_key": country.lower(),
        "type_key": "" if doc.appeals_type_id is None else str(doc.appeals_type_id),
        "year_key": "" if doc.year is None else str(doc.year),
        "title_key": doc.title.lower(),
        "aria_label": "PDF: " + ", ".join(aria_bits),
    }


def _page_url(filters: GalleryFilters) -> str:
    base = url_for("upr.upr_documents_gallery", _external=True)
    params: dict[str, str] = {}
    if filters.q:
        params["q"] = filters.q
    if filters.country:
        params["country"] = filters.country
    if filters.type_id is not None:
        params["type"] = str(filters.type_id)
    if filters.year is not None:
        params["year"] = str(filters.year)
    if filters.sort != SORT_NEWEST:
        params["sort"] = filters.sort
    if not params:
        return base
    return base + "?" + urlencode(params)


def _html(body: str, status: int = 200) -> Response:
    response = Response(body, status=status, mimetype="text/html; charset=utf-8")
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _suppress_anonymous_session() -> None:
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return
    except Exception:
        logger.debug("UPR gallery session check skipped", exc_info=True)
    suppress_session_cookie_for_request()


def _fetch_from_ifrc() -> list[UprGalleryDocument]:
    from app.routes.ai_documents.helpers import _get_ifrc_basic_auth

    auth = _get_ifrc_basic_auth()
    if auth is None:
        raise UprGalleryUnavailable("credentials")
    try:
        response = requests.get(
            _IFRC_LIST_URL,
            headers={"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"},
            auth=auth,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        logger.warning("UPR gallery IFRC HTTP %s", status)
        if status == 401:
            raise UprGalleryUnavailable("auth") from exc
        raise UprGalleryUnavailable("upstream") from exc
    except (requests.RequestException, ValueError) as exc:
        logger.warning("UPR gallery IFRC fetch failed: %s", type(exc).__name__)
        raise UprGalleryUnavailable("upstream") from exc
    if not isinstance(payload, list):
        raise UprGalleryUnavailable("upstream")
    documents = parse_ifrc_appeals(payload)
    logger.info("UPR gallery catalogue loaded: %s documents", len(documents))
    return documents


def _fresh_cache() -> list[UprGalleryDocument] | None:
    with _cache_lock:
        if _cached_docs is None:
            return None
        if time.monotonic() - _cached_at < _CACHE_TTL_SECONDS:
            return list(_cached_docs)
    return None


def _stale_cache() -> list[UprGalleryDocument] | None:
    with _cache_lock:
        if _cached_docs is None:
            return None
        return list(_cached_docs)


def _store_cache(docs: list[UprGalleryDocument]) -> None:
    global _cached_at, _cached_docs
    with _cache_lock:
        _cached_docs = list(docs)
        _cached_at = time.monotonic()


def _allowlisted_document_url(url: str) -> bool:
    ok, reason = validate_allowlisted_https_url(url)
    if not ok:
        logger.debug("UPR gallery skipped document URL: %s", reason)
    return ok


def _normalize_url(url: str) -> str:
    from app.routes.ai_documents.helpers import _normalize_ifrc_source_url

    return _normalize_ifrc_source_url(url)


def _dedupe_key(url: str) -> str:
    match = _DOWNLOAD_FILE_RE.search(url)
    if match:
        return f"ifrc_download:{match.group(1)}"
    return url


def _country_name(raw: Any) -> str | None:
    text = _ISO2_SUFFIX_RE.sub("", str(raw or "").strip()).strip()
    return text or None


def _type_label(type_id: int | None) -> str | None:
    if type_id is None:
        return None
    return APPEALS_TYPE_DISPLAY_NAMES.get(type_id) or f"Type {type_id}"


def _type_css_class(label: str | None) -> str:
    text = (label or "").lower()
    if "mid" in text:
        return "type-myr"
    if "annual" in text:
        return "type-ar"
    if "plan" in text:
        return "type-plan"
    return "type-other"


def _search_haystack(doc: UprGalleryDocument) -> str:
    return " ".join(
        part.lower()
        for part in (doc.title, doc.country_name or "", doc.document_type_label or "", doc.country_code or "")
        if part
    )


def _published_label(published: datetime | None) -> str:
    if published is None:
        return ""
    utc = published.astimezone(timezone.utc)
    return f"{utc.day} {_MONTHS[utc.month - 1]} {utc.year}"


def _published_sort(published: datetime | None) -> str:
    if published is None:
        return ""
    return published.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_country(wanted: str, countries: list[str]) -> str:
    key = wanted.strip().lower()
    if not key:
        return ""
    for name in countries:
        if name.lower() == key:
            return name
    return wanted.strip()


def _optional_int(raw: str) -> int | None:
    text = (raw or "").strip()
    if not re.fullmatch(r"-?\d{1,9}", text):
        return None
    return int(text)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None
