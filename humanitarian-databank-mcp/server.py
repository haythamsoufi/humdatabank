#!/usr/bin/env python3
"""
Humanitarian Databank MCP server — public API tools for Claude / Cursor.

Transports:
  - stdio (default): local Cursor / Claude Desktop
  - streamable-http: remote Claude.ai custom connector

Env:
  DATABANK_API_BASE  default https://databank.ifrc.org/api/v1
  MCP_TRANSPORT      stdio | streamable-http  (default stdio)
  MCP_HOST           default 0.0.0.0
  PORT / MCP_PORT    default 8000
  MCP_PATH           default /mcp
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastmcp import FastMCP

from databank_client import (
    DatabankAPIError,
    api_base,
    get_indicator,
    get_public_data_all_pages,
    get_public_data_page,
    search_indicators,
)

mcp = FastMCP(
    name="humanitarian-databank",
    instructions=(
        "Query the IFRC Humanitarian Databank public API at databank.ifrc.org. "
        "Use search_indicators to find indicator IDs, get_indicator for metadata, "
        "and get_public_data / get_public_data_all_pages for submitted values "
        "(public privacy items only; scoped filters required). "
        "After fetching, summarize and visualize trends when the user asks."
    ),
)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_error(exc: Exception) -> str:
    if isinstance(exc, DatabankAPIError):
        code = f" (HTTP {exc.status_code})" if exc.status_code else ""
        return f"Databank API error{code}: {exc}"
    return f"Error: {exc}"


@mcp.tool()
def databank_search_indicators(
    search: str = "",
    indicator_type: str = "",
    sector: str = "",
    sub_sector: str = "",
    emergency: str = "",
    archived: str = "",
) -> str:
    """Search the indicator bank catalogue (no auth).

    Returns matching indicators with id, name, definition, type, unit, sector.
    Use the id in get_public_data* calls.
    """
    try:
        archived_val: Optional[str] = archived.strip() or None
        result = search_indicators(
            search=search.strip(),
            indicator_type=indicator_type.strip(),
            sector=sector.strip(),
            sub_sector=sub_sector.strip(),
            emergency=emergency.strip(),
            archived=archived_val,
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
    related: str = "all",
    page: int = 1,
    per_page: int = 500,
) -> str:
    """Fetch one page of public submitted form data (no API key).

    Requires at least one scope filter. Returns data[] plus dimension tables
    (form_items, countries, indicator_bank, etc.). Public privacy items only.
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
        return _json_text(result)
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
    related: str = "all",
    per_page: int = 5000,
    max_pages: int = 20,
) -> str:
    """Fetch and merge multiple pages of public /data (for trends across countries/periods).

    Automatically paginates up to max_pages (default 20, max 5000 rows/page).
    Use for global totals by period when one page is not enough.
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
        return _json_text(result)
    except Exception as exc:
        return _tool_error(exc)


@mcp.tool()
def databank_api_info() -> str:
    """Return configured API base URL and public endpoint summary."""
    return _json_text(
        {
            "api_base": api_base(),
            "public_endpoints": [
                "GET /indicator-bank",
                "GET /indicator-bank/<id>",
                "GET /data (scoped, public privacy only)",
            ],
            "notes": (
                "Unscoped /data returns 401. Use databank_get_public_data with "
                "indicator_bank_id and/or period_name filters."
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
