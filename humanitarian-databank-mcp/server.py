#!/usr/bin/env python3
"""
Humanitarian Databank MCP server — public API tools for Claude / Cursor.

Transports:
  - stdio (default): local Cursor / Claude Desktop
  - streamable-http: remote Claude.ai custom connector

Env:
  DATABANK_API_BASE     default https://databank.ifrc.org/api/v1
  MCP_TRANSPORT         stdio | streamable-http  (default stdio)
  MCP_HOST              default 0.0.0.0
  PORT / MCP_PORT       default 8000
  MCP_PATH              default /mcp
  MCP_PUBLIC_BASE_URL   public origin for connector icon (default https://databank.ifrc.org)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from mcp.types import Icon
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from databank_analytics import search_indicators_ranked, slim_public_data_response
from databank_client import (
    DatabankAPIError,
    api_base,
    get_indicator,
    get_public_data_all_pages,
    get_public_data_page,
    get_public_document,
    get_public_documents_catalog,
    get_public_global_trend,
    get_submission_coverage,
    resolve_public_country,
    resolve_public_indicator,
    search_public_documents,
)
from instructions import MCP_INSTRUCTIONS

_ICON_PATH = Path(__file__).resolve().parent / "assets" / "ifrc_icon.svg"
_MCP_PATH = (os.environ.get("MCP_PATH") or "/mcp").strip() or "/mcp"
_MCP_PUBLIC_BASE = (
    os.environ.get("MCP_PUBLIC_BASE_URL") or "https://databank.ifrc.org"
).strip().rstrip("/")
_ICON_ROUTE = f"{_MCP_PATH.rstrip('/')}/icon.svg"
_ICON_URL = f"{_MCP_PUBLIC_BASE}{_ICON_ROUTE}"

mcp = FastMCP(
    name="IFRC Network Databank",
    website_url="https://databank.ifrc.org",
    icons=[Icon(src=_ICON_URL, mimeType="image/svg+xml")],
    instructions=MCP_INSTRUCTIONS,
)


@mcp.custom_route(_ICON_ROUTE, methods=["GET"])
async def mcp_icon(_request: Request) -> Response:
    """Public IFRC icon for Claude.ai / MCP connector listings."""
    return FileResponse(_ICON_PATH, media_type="image/svg+xml")


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_error(exc: Exception) -> str:
    if isinstance(exc, DatabankAPIError):
        code = f" (HTTP {exc.status_code})" if exc.status_code else ""
        return f"Databank API error{code}: {exc}"
    return f"Error: {exc}"


@mcp.tool()
def databank_resolve_indicator(query: str, limit: int = 5) -> str:
    """Resolve a natural-language or numeric indicator reference to an indicator bank id.

    Maps e.g. volunteers to indicator bank id (724 / KPI_PeopleVol). Prefer this
    before broad databank_search_indicators calls.
    """
    try:
        return _json_text(resolve_public_indicator(query, limit=limit))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_aggregate_global_trend(
    query: str = "",
    indicator_bank_id: Optional[int] = None,
    period_name: str = "",
    max_pages: int = 20,
) -> str:
    """Global totals grouped by reporting period (preferred for network-wide trends).

    Provide query (e.g. 'volunteers', 'staff') or indicator_bank_id. Deduplicates
    multiple submissions per country+period on the server. Only includes public data
    with data_status='available'. Returns compact by_period totals — do not sum raw
    databank_get_public_data rows for worldwide totals.
    """
    try:
        result = get_public_global_trend(
            indicator_bank_id=indicator_bank_id,
            query=query.strip(),
            period_name=period_name.strip(),
            max_pages=max_pages,
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_submission_coverage(
    template_id: Optional[int] = None,
    indicator_bank_id: Optional[int] = None,
    query: str = "",
    period_name: str = "",
    country_id: Optional[int] = None,
    max_pages: int = 20,
) -> str:
    """Count countries with a public submitted value, grouped by reporting period.

    Answers "how many countries submitted FDRS/UPR data for <period>, or across all
    years?" — pass template_id=21 for FDRS or template_id=22/24 for UPR (or an
    indicator_bank_id / query to scope to one indicator). Prefer this over paginating
    databank_get_public_data_all_pages and counting distinct countries yourself.
    Counts **public data coverage** only (data_status='available' on privacy=public
    form items) — this is not the same as internal assignment/workflow status, which
    is never exposed without an API key. See countries_submitted_total and by_period[].
    """
    try:
        result = get_submission_coverage(
            template_id=template_id,
            indicator_bank_id=indicator_bank_id,
            query=query.strip(),
            period_name=period_name.strip(),
            country_id=country_id,
            max_pages=max_pages,
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_resolve_country(query: str, limit: int = 5) -> str:
    """Resolve a country name, ISO2/ISO3 code, or numeric id to Country reference fields.

    Returns id, name, iso2, iso3, region. Use this instead of paginating the full
    countries[] dimension table just to look up one country's id.
    """
    try:
        return _json_text(resolve_public_country(query, limit=limit))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_search_public_documents(
    query: str,
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
) -> str:
    """Search public Unified Plan/Report document chunks (UPR narrative Q&A).

    Returns text chunks from documents marked public in the AI Knowledge Base.
    Answer only from chunks[].content; cite document_title + page_number per claim.
    Use full_coverage=true for cross-country themes (e.g. migration in 2026 Unified Plans).
    Paginate with page/per_page when coverage.has_more_pages is true.
    """
    try:
        result = search_public_documents(
            query,
            full_coverage=full_coverage,
            page=page,
            per_page=per_page,
            latest_per_country=latest_per_country,
            top_k=top_k,
            min_score=min_score,
            country_name=country_name.strip(),
            country_id=country_id,
            file_type=file_type.strip(),
            search_mode=search_mode.strip() or "hybrid",
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_documents_catalog(
    document_type: str = "",
    year: Optional[int] = None,
    country_id: Optional[int] = None,
    country_name: str = "",
    file_type: str = "",
    include_documents: bool = True,
) -> str:
    """Inventory public documents by type/year/country — counts, not semantic search.

    Answers "how many countries submitted an annual report (FDRS) or a Unified Plan
    (UPR) for 2024, or across all years?" directly from document metadata — much
    cheaper than databank_search_public_documents for counting questions.
    document_type is one of annual_report, unified_plan, midyear_report, other
    (omit for all types). Set include_documents=false for counts only (by_type,
    by_year, countries_count) without the per-country document listing.
    """
    try:
        result = get_public_documents_catalog(
            document_type=document_type.strip(),
            year=year,
            country_id=country_id,
            country_name=country_name.strip(),
            file_type=file_type.strip(),
            include_documents=include_documents,
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_public_document(document_id: int) -> str:
    """Get public metadata for one AI document (title, countries, source_url, links).

    Use when a databank_search_public_documents chunk lacks document_url and the
    user needs a shareable link, or to confirm a document's countries/date/category.
    """
    try:
        return _json_text(get_public_document(document_id))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_search_indicators(
    search: str = "",
    indicator_type: str = "",
    sector: str = "",
    sub_sector: str = "",
    emergency: str = "",
    archived: str = "",
    limit: int = 10,
) -> str:
    """Search the indicator bank catalogue (no auth).

    Returns top matches with slim fields (id, name, type, unit, fdrs_kpi_code,
    sector, tags). Results are relevance-ranked and capped (default 10).
    For headcount metrics use databank_resolve_indicator instead.
    """
    try:
        archived_val: Optional[str] = archived.strip() or None
        result = search_indicators_ranked(
            search=search.strip(),
            indicator_type=indicator_type.strip(),
            sector=sector.strip(),
            sub_sector=sub_sector.strip(),
            emergency=emergency.strip(),
            archived=archived_val,
            limit=limit,
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_indicator(indicator_id: int) -> str:
    """Get full metadata for one indicator bank entry by numeric id."""
    try:
        return _json_text(get_indicator(indicator_id))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_public_data(
    indicator_bank_id: Optional[int] = None,
    indicator_bank_ids: str = "",
    template_id: Optional[int] = None,
    country_id: Optional[int] = None,
    country_iso2: str = "",
    country_iso3: str = "",
    period_name: str = "",
    submission_type: str = "",
    item_id: Optional[int] = None,
    related: str = "page",
    page: int = 1,
    per_page: int = 500,
    include_dimensions: bool = False,
) -> str:
    """Fetch one page of public submitted form data (no API key).

    Requires at least one scope filter. By default returns data[] and pagination
    only (dimension tables stripped). Never set include_dimensions=true unless the
    user explicitly needs join tables. Multiple submissions may exist per
    country+period — use databank_aggregate_global_trend for network totals.
    FDRS-only: template_id=21; UPR numeric: template_id=22 or 24.
    """
    try:
        result = get_public_data_page(
            indicator_bank_id=indicator_bank_id,
            indicator_bank_ids=indicator_bank_ids.strip() or None,
            template_id=template_id,
            country_id=country_id,
            country_iso2=country_iso2.strip() or None,
            country_iso3=country_iso3.strip() or None,
            period_name=period_name.strip() or None,
            submission_type=submission_type.strip() or None,
            item_id=item_id,
            related=related,
            page=page,
            per_page=per_page,
        )
        return _json_text(slim_public_data_response(result, include_dimensions=include_dimensions))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_public_data_all_pages(
    indicator_bank_id: Optional[int] = None,
    indicator_bank_ids: str = "",
    template_id: Optional[int] = None,
    country_id: Optional[int] = None,
    country_iso2: str = "",
    country_iso3: str = "",
    period_name: str = "",
    submission_type: str = "",
    item_id: Optional[int] = None,
    related: str = "page",
    per_page: int = 5000,
    max_pages: int = 20,
    include_dimensions: bool = False,
) -> str:
    """Fetch and merge multiple pages of public /data.

    Automatically paginates up to max_pages (default 20, max 5000 rows/page).
    Dimension tables are stripped by default. WARNING: rows are not deduplicated;
    for global totals by period use databank_aggregate_global_trend instead.
    """
    try:
        result = get_public_data_all_pages(
            indicator_bank_id=indicator_bank_id,
            indicator_bank_ids=indicator_bank_ids.strip() or None,
            template_id=template_id,
            country_id=country_id,
            country_iso2=country_iso2.strip() or None,
            country_iso3=country_iso3.strip() or None,
            period_name=period_name.strip() or None,
            submission_type=submission_type.strip() or None,
            item_id=item_id,
            related=related,
            per_page=per_page,
            max_pages=max_pages,
        )
        return _json_text(slim_public_data_response(result, include_dimensions=include_dimensions))
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_api_info() -> str:
    """Return configured API base URL and public endpoint summary."""
    return _json_text(
        {
            "api_base": api_base(),
            "public_endpoints": [
                "GET /public/global-trend",
                "GET /public/indicators/resolve",
                "GET /public/submissions/coverage",
                "GET /public/countries/resolve",
                "GET /public/documents/search",
                "GET /public/documents/catalog",
                "GET /public/documents/<id>",
                "GET /public/documents/<id>/download",
                "GET /indicator-bank",
                "GET /indicator-bank/<id>",
                "GET /data (scoped, public privacy only)",
            ],
            "recommended_tools": {
                "global_trends": "databank_aggregate_global_trend(query='volunteers')",
                "find_indicator": "databank_resolve_indicator(query='total volunteers')",
                "find_country": "databank_resolve_country(query='Kenya')",
                "count_submissions": "databank_get_submission_coverage(template_id=21, period_name='Annual 2024')",
                "count_documents": "databank_get_documents_catalog(document_type='annual_report', year=2024)",
                "upr_documents": "databank_search_public_documents(query='Syria unified plan 2026')",
                "one_document": "databank_get_public_document(document_id=ID)",
                "raw_rows": "databank_get_public_data(indicator_bank_id=ID, include_dimensions=false)",
            },
            "notes": (
                "Unscoped /data returns 401. Multiple submissions per country+period "
                "require dedupe — use databank_aggregate_global_trend for network totals, or "
                "databank_get_submission_coverage to count countries that submitted (not sum values). "
                "Use databank_get_documents_catalog to count/list public documents by type/year/country "
                "instead of paginating databank_search_public_documents. "
                "Document answers must cite chunks from databank_search_public_documents only."
            ),
        }
    )


# ASGI app for gunicorn/uvicorn: gunicorn server:app -k uvicorn.workers.UvicornWorker
app = mcp.http_app(transport="streamable-http")


def main() -> None:
    transport = (os.environ.get("MCP_TRANSPORT") or "stdio").strip().lower()
    if transport in ("streamable-http", "http"):
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("PORT") or os.environ.get("MCP_PORT") or "8000")
        path = os.environ.get("MCP_PATH", "/mcp")
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            path=path,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
