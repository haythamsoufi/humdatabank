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

Parallel document-search calls (investigation notes, 2026-08):
  - Production Application Gateway backend timeout is ~30s (see Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md).
    GET /public/documents/search is not in the extended-timeout AI chat routes; two concurrent broad
    searches can exceed 30s and return 504 with no JSON body to the MCP client.
  - FastMCP @mcp.tool sync handlers run in a thread pool; client-side cancellation surfaces as
    asyncio.CancelledError (BaseException), which is not caught by `except Exception` — symptom:
    "no result, no error". Mitigation for callers: use country_ids batched search, avoid parallel
    broad queries; confirm via App Service / AGW logs at failure timestamps before server-side fixes.
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
    get_country_report,
    get_indicator,
    get_public_data_all_pages,
    get_public_data_page,
    get_public_document,
    get_public_documents_catalog,
    get_public_global_trend,
    get_report_template,
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
    country_ids: str = "",
    file_type: str = "",
    search_mode: str = "hybrid",
    require_phrase: str = "",
) -> str:
    """Search public Unified Plan/Report document chunks (UPR narrative Q&A).

    Returns text chunks from documents marked public in the AI Knowledge Base.
    Answer only from chunks[].content; cite document_title + page_number per claim.
    Use full_coverage=true for cross-country themes (e.g. migration in 2026 Unified Plans).
    Paginate with page/per_page when coverage.has_more_pages is true.

    Phrase search: wrap multi-word terms in double quotes in query (e.g. "Post Office")
    to bias keyword ranking toward literal phrase matches (Postgres websearch_to_tsquery).
    For a hard requirement that the phrase appear in every chunk, pass require_phrase.

    Multi-country: pass country_ids as comma-separated numeric ids (e.g. "153,167") or
    "all" for one batched search with by_country grouping in the response.
    Avoid firing multiple parallel broad searches — production gateway timeout is ~30s.
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
            country_ids=country_ids.strip(),
            file_type=file_type.strip(),
            search_mode=search_mode.strip() or "hybrid",
            require_phrase=require_phrase.strip(),
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
    include_documents: bool = False,
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
def databank_build_country_report(
    country: str,
    period_hint: str = "",
    report_type: str = "combined",
    include_prior_period: bool = True,
    template_style: str = "",
) -> str:
    """Assemble a one-country report spec (headline KPIs + trend + cited narrative themes).

    Use for "build/generate a report/one-pager for <country> using <period> data" — this
    single call resolves the country and reporting period, fetches a curated FDRS headline
    KPI bundle (volunteers, staff, branches, local units, governing board, income,
    expenditure, blood donations, first-aid trained) for the resolved period plus the prior
    one, a multi-period volunteers trend, and cited themes from public Unified
    Plan/Report/Midyear Report documents. Render the actual visual one-pager yourself from
    the returned JSON (chart + KPI cards + narrative bullets) — this tool never returns
    HTML or images.

    period_hint accepts free text like '2026 midyear', '2026', 'Jan-Jun 2026', or '' (latest
    available). There is no exact period_name catalog, so the resolver matches against real
    periods discovered for this country; read period.available_periods and
    coverage.period_match_note when the requested year/cycle has no public data yet — say so
    explicitly rather than substituting unrelated numbers.

    report_type: 'fdrs' (numbers only), 'upr' (narrative Unified Plan/Report themes only —
    not UPR-specific numeric indicators), or 'combined' (default, both).

    Set template_style='default' (recommended) to embed the IFRC Brand System-aligned
    design_template inline — Montserrat/Open Sans, IFRC horizontal logo, red+navy layout.
    Fill html_template placeholders; do not invent a generic card/dashboard layout.
    Leave template_style empty only if the user explicitly asks for a freeform render.

    This tool (and the underlying API) never generates or returns a PDF or HTML file — it
    only returns data plus a style/layout spec. For the final deliverable, use your own
    file-creation/code-execution capability (e.g. the pdf skill) to generate a real,
    downloadable PDF one-pager from this JSON, following design_template. An inline
    HTML/canvas render is fine only as a quick in-chat preview, not as the final artifact —
    when the user wants something to keep, print, or share, produce an actual PDF file.
    """
    try:
        result = get_country_report(
            country,
            period_hint=period_hint,
            report_type=report_type,
            include_prior_period=include_prior_period,
            template_style=template_style,
        )
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_get_report_template(style: str = "default") -> str:
    """Return an HTML/CSS one-pager skeleton plus design tokens for country reports.

    Use alongside databank_build_country_report when the user wants the one-pager to
    follow a specific layout/palette instead of a freeform render: fill the returned
    html_template's {{PLACEHOLDER}} tokens with the report spec's data (repeat the
    KPI_CARD and THEME_ITEM blocks per entry), and apply design_tokens (colors, fonts,
    spacing) even if you ultimately render as markdown, a canvas component, or an
    image-generation prompt rather than raw HTML. Call with no arguments (style='default')
    to see the only bundled style; pass an unrecognized style to list available_styles.

    For a final deliverable, use design_tokens to generate a real PDF file yourself (e.g.
    via the pdf skill/code execution) rather than only returning HTML — this tool never
    renders or converts anything server-side. Most code-execution sandboxes have no network
    access: the IFRC logo is already inline as SVG in html_template, so don't fetch it; for
    fonts, use Montserrat/Open Sans only if already available locally, otherwise fall back
    to a built-in sans-serif (e.g. Helvetica) instead of failing the report.
    """
    try:
        return _json_text(get_report_template(style))
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
                "GET /public/reports/country",
                "GET /public/reports/template",
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
                "country_report": "databank_build_country_report(country='Syria', period_hint='2026 midyear')",
                "report_template": "databank_get_report_template(style='default')",
            },
            "notes": (
                "Unscoped /data returns 401. Multiple submissions per country+period "
                "require dedupe — use databank_aggregate_global_trend for network totals, or "
                "databank_get_submission_coverage to count countries that submitted (not sum values). "
                "Use databank_get_documents_catalog to count/list public documents by type/year/country "
                "instead of paginating databank_search_public_documents. "
                "Document answers must cite chunks from databank_search_public_documents only. "
                "For a country one-pager, prefer databank_build_country_report over chaining the "
                "tools above by hand — pass template_style to also get a layout/style guide."
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
