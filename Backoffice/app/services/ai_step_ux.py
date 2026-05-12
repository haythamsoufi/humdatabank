"""
User-facing step/progress text helpers for agent execution.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
from typing import Any, Dict, Optional

from flask_babel import gettext as _

from app.services.upr.ux import (
    step_display_message_get_upr_kpi_value,
    step_display_message_get_upr_kpi_values_for_all_countries,
    suppress_format_tool_args_detail_for_tool,
    upr_document_query_display_label,
)


def document_query_for_display(raw_query: str) -> str:
    """Return a short user-facing label for document search/list queries."""
    if not (raw_query or "").strip():
        return ""
    q = (raw_query or "").strip()
    upr_label = upr_document_query_display_label(q)
    if upr_label is not None:
        return upr_label
    return q[:50] + ("…" if len(q) > 50 else "")


def step_display_message(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Build a short user-facing message for a tool step."""
    if tool_name == "get_indicator_value":
        country = (tool_args or {}).get("country_identifier") or ""
        indicator = (tool_args or {}).get("indicator_name") or ""
        indicator_short = (indicator[:40] + ("…" if len(indicator) > 40 else "")) if indicator else ""
        if country and indicator:
            return _("Getting data (%(indicator)s — %(country)s)", indicator=indicator_short, country=country)
        if country:
            return _("Getting data for %(country)s", country=country)
        return _("Getting data")
    if tool_name in ("search_documents", "search_documents_hybrid"):
        query = (tool_args or {}).get("query") or ""
        if query:
            short = document_query_for_display(query) or (query[:50] + ("…" if len(query) > 50 else ""))
            return _("Searching documents (%(query)s)", query=short)
        return _("Searching documents")
    if tool_name == "list_documents":
        query = (tool_args or {}).get("query") or ""
        if query:
            short = document_query_for_display(query) or (query[:50] + ("…" if len(query) > 50 else ""))
            return _("Listing documents (%(query)s)", query=short)
        return _("Listing documents")
    if tool_name == "get_country_information":
        country = (tool_args or {}).get("country_identifier") or ""
        if country:
            return _("Looking up country (%(country)s)", country=country)
        return _("Looking up country")
    if tool_name == "get_upr_kpi_value":
        return step_display_message_get_upr_kpi_value(tool_args)
    if tool_name == "get_indicator_metadata":
        indicator = (tool_args or {}).get("indicator_name") or ""
        indicator_short = (indicator[:40] + ("…" if len(indicator) > 40 else "")) if indicator else ""
        if indicator:
            return _("Looking up indicator details (%(indicator)s)", indicator=indicator_short)
        return _("Looking up indicator details")
    if tool_name == "get_upr_kpi_values_for_all_countries":
        return step_display_message_get_upr_kpi_values_for_all_countries(tool_args)
    if tool_name == "get_indicator_values_for_all_countries":
        indicator = (tool_args or {}).get("indicator_name") or ""
        indicator_short = (indicator[:40] + ("…" if len(indicator) > 40 else "")) if indicator else ""
        if indicator:
            return _("Getting %(indicator)s for all countries", indicator=indicator_short)
        return _("Getting indicator values for all countries")
    if tool_name == "get_indicator_timeseries":
        country = (tool_args or {}).get("country_identifier") or ""
        indicator = (tool_args or {}).get("indicator_name") or ""
        indicator_short = (indicator[:40] + ("…" if len(indicator) > 40 else "")) if indicator else ""
        if country and indicator:
            return _("Getting data (%(indicator)s — %(country)s)", indicator=indicator_short, country=country)
        if country:
            return _("Getting data for %(country)s", country=country)
        if indicator:
            return _("Getting data (%(indicator)s)", indicator=indicator_short)
        return _("Getting data")
    return _("Checking data…")


def format_tool_args_detail(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Short one-line detail for progress panels."""
    if not tool_args:
        return ""
    if suppress_format_tool_args_detail_for_tool(tool_name):
        return ""
    if tool_name in ("search_documents", "search_documents_hybrid"):
        try:
            return_all = bool((tool_args or {}).get("return_all_countries"))
            country = (tool_args or {}).get("country_identifier") or ""
            doc_type = (tool_args or {}).get("document_type") or ""
            parts = []
            if return_all:
                parts.append(_("Searching across all countries"))
            elif country:
                parts.append(_("Country: %(country)s", country=str(country)[:50]))
            if doc_type:
                parts.append(_("File type: %(t)s", t=str(doc_type)[:30]))
            return ", ".join([p for p in parts if p]) if parts else ""
        except Exception as e:
            logger.debug("search_documents step_display_message failed: %s", e)
            return ""
    if tool_name == "list_documents":
        try:
            country = (tool_args or {}).get("country_identifier") or ""
            file_type = (tool_args or {}).get("file_type") or ""
            parts = []
            if country:
                parts.append(_("Country: %(country)s", country=str(country)[:50]))
            if file_type:
                parts.append(_("File type: %(t)s", t=str(file_type)[:30]))
            return ", ".join([p for p in parts if p]) if parts else ""
        except Exception as e:
            logger.debug("list_documents step_display_message failed: %s", e)
            return ""
    skip = {"_progress_callback"}
    # Internal / tuning args — not meaningful in the progress panel.
    skip_internal = frozenset(
        {
            "include_saved",
            "limit_periods",
        }
    )
    key_labels = {
        "country_identifier": _("Country"),
        "metric": _("Metric"),
        "query": _("Query"),
        "indicator_name": _("Indicator"),
        "field_label_or_name": _("Field"),
        "template_identifier": _("Template"),
        "period": _("Period"),
    }
    parts = []
    for k, v in sorted(tool_args.items()):
        if k in skip or k in skip_internal or v is None or v == "":
            continue
        if str(k).startswith("_"):
            continue
        if isinstance(v, (list, dict)) and len(str(v)) > 60:
            label = key_labels.get(k, k)
            parts.append(f"{label}: …")
        else:
            sv = str(v)[:50] + ("…" if len(str(v)) > 50 else "")
            label = key_labels.get(k, k)
            parts.append(f"{label}: {sv}")
    return ", ".join(parts) if parts else ""


def format_plan_for_step(plan: Optional[Any], query: Optional[str] = None) -> str:
    """One-line user-facing summary for the planning step detail."""
    if plan is None:
        q = (query or "").strip()
        if len(q) > 160:
            q = q[:157] + "…"
        if q:
            return _(
                "No single-tool shortcut for this request — reviewing: %(snippet)s",
                snippet=q,
            )
        return _(
            "No single-tool shortcut; using the full planning and reasoning path."
        )
    msg = step_display_message(plan.tool_name, plan.tool_args or {})
    if getattr(plan, "output_hint", None) and plan.output_hint != "text":
        return _("Planned first step: %(step)s", step=msg)
    return _("Planned first step: %(step)s", step=msg)
