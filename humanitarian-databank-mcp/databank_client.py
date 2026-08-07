"""HTTP client for the IFRC Humanitarian Databank public API."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

DEFAULT_BASE = "https://databank.ifrc.org/api/v1"
PUBLIC_DATA_MAX_PER_PAGE = 5000
MAX_AUTO_PAGES = 20
REQUEST_TIMEOUT = 60.0


class DatabankAPIError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def api_base() -> str:
    return (os.environ.get("DATABANK_API_BASE") or DEFAULT_BASE).rstrip("/")


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{api_base()}{path}"
    clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=clean)
    except httpx.RequestError as exc:
        raise DatabankAPIError(f"Request failed: {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text[:500] if resp.text else resp.reason_phrase
        raise DatabankAPIError(
            f"HTTP {resp.status_code} from {url}: {detail}",
            status_code=resp.status_code,
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise DatabankAPIError(f"Non-JSON response from {url}") from exc


def search_indicators(
    *,
    search: str = "",
    indicator_type: str = "",
    sector: str = "",
    sub_sector: str = "",
    emergency: str = "",
    archived: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if search:
        params["search"] = search
    if indicator_type:
        params["type"] = indicator_type
    if sector:
        params["sector"] = sector
    if sub_sector:
        params["sub_sector"] = sub_sector
    if emergency:
        params["emergency"] = emergency
    if archived is not None:
        params["archived"] = archived
    data = _get("/indicator-bank", params)
    indicators = data.get("indicators", data if isinstance(data, list) else [])
    return {"indicators": indicators, "count": len(indicators)}


def get_indicator(indicator_id: int) -> Dict[str, Any]:
    return _get(f"/indicator-bank/{int(indicator_id)}")


def get_public_global_trend(
    *,
    query: str = "",
    indicator_bank_id: Optional[int] = None,
    period_name: str = "",
    max_pages: int = 20,
) -> Dict[str, Any]:
    """Compact deduped global totals via GET /public/global-trend."""
    params: Dict[str, Any] = {"max_pages": max(1, min(int(max_pages), 20))}
    if indicator_bank_id is not None:
        params["indicator_bank_id"] = int(indicator_bank_id)
    if query.strip():
        params["query"] = query.strip()
    if period_name.strip():
        params["period_name"] = period_name.strip()
    if indicator_bank_id is None and not query.strip():
        raise DatabankAPIError("Provide indicator_bank_id or query for global trend.")
    return _get("/public/global-trend", params)


def resolve_public_indicator(
    query: str,
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    """Map natural-language metric to indicator id via GET /public/indicators/resolve."""
    raw = (query or "").strip()
    if not raw:
        raise DatabankAPIError("query is required")
    return _get(
        "/public/indicators/resolve",
        {"query": raw, "limit": max(1, min(int(limit), 20))},
    )


def search_public_documents(
    query: str,
    *,
    full_coverage: bool = False,
    page: int = 1,
    per_page: int = 80,
    latest_per_country: Optional[bool] = None,
    top_k: int = 8,
    min_score: float = 0.25,
    country_name: str = "",
    country_id: Optional[int] = None,
    file_type: str = "",
    search_mode: str = "hybrid",
) -> Dict[str, Any]:
    """Search public AI document chunks via GET /public/documents/search."""
    raw = (query or "").strip()
    if not raw:
        raise DatabankAPIError("query is required")

    params: Dict[str, Any] = {
        "query": raw,
        "full_coverage": "true" if full_coverage else "false",
        "page": max(1, int(page)),
        "per_page": max(1, min(int(per_page), 200)),
        "top_k": max(1, min(int(top_k), 12)),
        "min_score": min_score,
        "search_mode": search_mode or "hybrid",
    }
    if latest_per_country is True:
        params["latest_per_country"] = "true"
    elif latest_per_country is False:
        params["latest_per_country"] = "false"
    if country_name.strip():
        params["country_name"] = country_name.strip()
    if country_id is not None:
        params["country_id"] = int(country_id)
    if file_type.strip():
        params["file_type"] = file_type.strip()
    return _get("/public/documents/search", params)


def get_public_document(document_id: int) -> Dict[str, Any]:
    """Public metadata for one AI document via GET /public/documents/<id>."""
    return _get(f"/public/documents/{int(document_id)}")


def get_public_documents_catalog(
    *,
    document_type: str = "",
    year: Optional[int] = None,
    country_id: Optional[int] = None,
    country_name: str = "",
    file_type: str = "",
    include_documents: bool = True,
) -> Dict[str, Any]:
    """Inventory public documents by type/year/country via GET /public/documents/catalog."""
    params: Dict[str, Any] = {"include_documents": "true" if include_documents else "false"}
    if document_type.strip():
        params["document_type"] = document_type.strip()
    if year is not None:
        params["year"] = int(year)
    if country_id is not None:
        params["country_id"] = int(country_id)
    if country_name.strip():
        params["country_name"] = country_name.strip()
    if file_type.strip():
        params["file_type"] = file_type.strip()
    return _get("/public/documents/catalog", params)


def get_submission_coverage(
    *,
    template_id: Optional[int] = None,
    indicator_bank_id: Optional[int] = None,
    query: str = "",
    period_name: str = "",
    country_id: Optional[int] = None,
    max_pages: int = 20,
) -> Dict[str, Any]:
    """Count countries with public submitted data via GET /public/submissions/coverage."""
    if template_id is None and indicator_bank_id is None and not query.strip():
        raise DatabankAPIError("Provide template_id, indicator_bank_id, or query for submission coverage.")

    params: Dict[str, Any] = {"max_pages": max(1, min(int(max_pages), 20))}
    if template_id is not None:
        params["template_id"] = int(template_id)
    if indicator_bank_id is not None:
        params["indicator_bank_id"] = int(indicator_bank_id)
    if query.strip():
        params["query"] = query.strip()
    if period_name.strip():
        params["period_name"] = period_name.strip()
    if country_id is not None:
        params["country_id"] = int(country_id)
    return _get("/public/submissions/coverage", params)


def resolve_public_country(query: str, *, limit: int = 5) -> Dict[str, Any]:
    """Map a country name/ISO code/id to Country reference fields via GET /public/countries/resolve."""
    raw = (query or "").strip()
    if not raw:
        raise DatabankAPIError("query is required")
    return _get(
        "/public/countries/resolve",
        {"query": raw, "limit": max(1, min(int(limit), 20))},
    )


def get_public_data_page(
    *,
    indicator_bank_id: Optional[int] = None,
    indicator_bank_ids: Optional[str] = None,
    template_id: Optional[int] = None,
    country_id: Optional[int] = None,
    country_iso2: Optional[str] = None,
    country_iso3: Optional[str] = None,
    period_name: Optional[str] = None,
    submission_type: Optional[str] = None,
    item_id: Optional[int] = None,
    related: str = "all",
    page: int = 1,
    per_page: int = 500,
) -> Dict[str, Any]:
    if not any(
        [
            indicator_bank_id,
            indicator_bank_ids,
            template_id,
            country_id,
            country_iso2,
            country_iso3,
            period_name,
            item_id,
        ]
    ):
        raise DatabankAPIError(
            "At least one scope filter is required for public /data "
            "(e.g. indicator_bank_id, template_id, country_iso3, period_name)."
        )

    per_page = min(max(1, int(per_page)), PUBLIC_DATA_MAX_PER_PAGE)
    params: Dict[str, Any] = {
        "page": max(1, int(page)),
        "per_page": per_page,
        "related": related or "all",
    }
    if indicator_bank_id is not None:
        params["indicator_bank_id"] = int(indicator_bank_id)
    if indicator_bank_ids:
        params["indicator_bank_ids"] = indicator_bank_ids
    if template_id is not None:
        params["template_id"] = int(template_id)
    if country_id is not None:
        params["country_id"] = int(country_id)
    if country_iso2:
        params["country_iso2"] = country_iso2.strip().upper()
    if country_iso3:
        params["country_iso3"] = country_iso3.strip().upper()
    if period_name:
        params["period_name"] = period_name
    if submission_type:
        params["submission_type"] = submission_type
    if item_id is not None:
        params["item_id"] = int(item_id)

    return _get("/data", params)


def get_public_data_all_pages(
    *,
    max_pages: int = MAX_AUTO_PAGES,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Fetch and merge paginated public /data responses."""
    first = get_public_data_page(page=1, **kwargs)
    merged_rows: List[Any] = list(first.get("data") or [])
    total_pages = int(first.get("total_pages") or 1)
    pages_fetched = 1
    cap = min(max(1, int(max_pages)), MAX_AUTO_PAGES)

    per_page = kwargs.get("per_page", 500)
    fetch_kwargs = dict(kwargs)

    while pages_fetched < total_pages and pages_fetched < cap:
        pages_fetched += 1
        nxt = get_public_data_page(page=pages_fetched, **fetch_kwargs)
        merged_rows.extend(nxt.get("data") or [])

    out = dict(first)
    out["data"] = merged_rows
    out["pages_fetched"] = pages_fetched
    out["total_pages"] = total_pages
    out["truncated"] = pages_fetched < total_pages
    if out["truncated"]:
        out["warning"] = (
            f"Stopped after {pages_fetched} of {total_pages} pages "
            f"(max_pages={cap}). Narrow filters or increase max_pages."
        )
    return out
