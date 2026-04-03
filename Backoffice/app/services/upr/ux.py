"""
User-facing UX strings and helpers for Unified Planning and Reporting (UPR).

Centralises UPR-related step messages, document-query display patterns, tool
name humanisation labels for response sanitisation, and source qualifier text
so other modules (e.g. ``ai_step_ux``, ``ai_response_policy``,
``ai_payload_inference``) share a single source of truth.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from flask_babel import gettext as _

# Human-readable replacements when sanitising agent answers that mention tool names.
UPR_TOOL_LABELS = {
    "get_upr_kpi_values_for_all_countries": "the bulk UPR KPI query",
    "get_upr_kpi_value": "the UPR KPI query",
}

# Payload / source line qualifier when data comes from UPR document context.
UPR_SOURCE_QUALIFIER = "from UPR documents"

# Document search/list queries that are shorthand for UPR vs UPL scopes.
_RE_UPR_ONLY = re.compile(r"^UPR:?\s*$", re.IGNORECASE)
_RE_UPL_ONLY = re.compile(r"^UPL-?\s*$", re.IGNORECASE)
_RE_UPR_UPL_OR = re.compile(r"^(UPR:?|UPL-?)(\s+OR\s+.*)?$", re.IGNORECASE)


def upr_document_query_display_label(raw_query: str) -> Optional[str]:
    """If *raw_query* is a UPR/UPL document-scope shorthand, return the display label; else ``None``."""
    if not (raw_query or "").strip():
        return None
    q = (raw_query or "").strip()
    if _RE_UPR_ONLY.match(q):
        return _("Unified Planning and Reporting")
    if _RE_UPL_ONLY.match(q):
        return _("Unified Plans")
    if _RE_UPR_UPL_OR.match(q) and len(q) < 30:
        if "UPL" in q.upper() and "UPR" not in q.upper():
            return _("Unified Plans")
        if "UPR" in q.upper():
            return _("Unified Planning and Reporting")
    return None


def step_display_message_get_upr_kpi_value(tool_args: Dict[str, Any]) -> str:
    """User-facing step line for ``get_upr_kpi_value``."""
    country = (tool_args or {}).get("country_identifier") or ""
    metric = (tool_args or {}).get("metric") or ""
    metric_short = (metric[:30] + ("…" if len(metric) > 30 else "")) if metric else ""
    if country and metric:
        return _("Looking in Unified Plans and Reports (%(metric)s — %(country)s)", metric=metric_short, country=country)
    if country:
        return _("Looking in Unified Plans and Reports (%(country)s)", country=country)
    return _("Looking in Unified Plans and Reports")


def step_display_message_get_upr_kpi_values_for_all_countries(tool_args: Dict[str, Any]) -> str:
    """User-facing step line for ``get_upr_kpi_values_for_all_countries``."""
    metric = (tool_args or {}).get("metric") or ""
    if metric:
        return _("Getting %(metric)s for all countries from Unified Plans and Reports", metric=metric)
    return _("Getting data for all countries from Unified Plans and Reports")


def suppress_format_tool_args_detail_for_tool(tool_name: str) -> bool:
    """Return True when ``format_tool_args_detail`` should return an empty string for *tool_name*."""
    return tool_name == "get_upr_kpi_values_for_all_countries"
