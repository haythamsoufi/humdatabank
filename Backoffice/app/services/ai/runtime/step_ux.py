"""
User-facing step/progress text helpers for agent execution.
"""

from __future__ import annotations

import logging

from typing import Any, Dict, List, Optional

from flask_babel import gettext as _

logger = logging.getLogger(__name__)


def _upr_ux():
    """Lazy import — keeps `upr` UX hooks out of module import order."""
    from app.services.upr import ux as _ux

    return _ux


def document_query_for_display(raw_query: str) -> str:
    """Return a short user-facing label for document search/list queries."""
    if not (raw_query or "").strip():
        return ""
    q = (raw_query or "").strip()
    upr_label = _upr_ux().upr_document_query_display_label(q)
    if upr_label is not None:
        return upr_label
    return q[:50] + ("…" if len(q) > 50 else "")


def _short_label(text: str, max_len: int = 40) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    return t[:max_len] + ("…" if len(t) > max_len else "")


def step_display_message(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Build a short user-facing message for a tool step."""
    args = tool_args or {}
    if tool_name == "get_indicator_value":
        country = args.get("country_identifier") or ""
        indicator = _short_label(args.get("indicator_name") or "")
        if country and indicator:
            return _("Reading %(indicator)s data for %(country)s…", indicator=indicator, country=country)
        if country:
            return _("Reading indicator data for %(country)s…", country=country)
        return _("Reading indicator data…")
    if tool_name in ("search_documents", "search_documents_hybrid"):
        query = args.get("query") or ""
        if query:
            short = document_query_for_display(query) or _short_label(query, 50)
            return _("Searching reports and plans for '%(query)s'…", query=short)
        return _("Searching reports and plans…")
    if tool_name == "list_documents":
        query = args.get("query") or ""
        if query:
            short = document_query_for_display(query) or _short_label(query, 50)
            return _("Browsing documents matching '%(query)s'…", query=short)
        return _("Browsing available documents…")
    if tool_name == "get_country_information":
        country = args.get("country_identifier") or ""
        if country:
            return _("Looking up information for %(country)s…", country=country)
        return _("Looking up country information…")
    if tool_name == "get_upr_kpi_value":
        return _upr_ux().step_display_message_get_upr_kpi_value(tool_args)
    if tool_name == "get_indicator_metadata":
        indicator = _short_label(args.get("indicator_name") or "")
        if indicator:
            return _("Reading details for %(indicator)s…", indicator=indicator)
        return _("Reading indicator details…")
    if tool_name == "get_upr_kpi_values_for_all_countries":
        return _upr_ux().step_display_message_get_upr_kpi_values_for_all_countries(tool_args)
    if tool_name == "get_indicator_values_for_all_countries":
        indicator = _short_label(args.get("indicator_name") or "")
        if indicator:
            return _("Reading %(indicator)s across all countries…", indicator=indicator)
        return _("Reading indicator data across all countries…")
    if tool_name == "get_form_field_values_for_all_countries":
        field = _short_label(args.get("field_label_or_name") or "")
        if args.get("min_share_pct") is not None:
            return _("Analyzing matrix shares across all countries…")
        if field:
            return _("Reading %(field)s across all countries…", field=field)
        return _("Reading form field data across all countries…")
    if tool_name == "get_indicator_timeseries":
        country = args.get("country_identifier") or ""
        indicator = _short_label(args.get("indicator_name") or "")
        if country and indicator:
            return _("Reading %(indicator)s over time for %(country)s…", indicator=indicator, country=country)
        if country:
            return _("Reading indicator trends for %(country)s…", country=country)
        if indicator:
            return _("Reading %(indicator)s over time…", indicator=indicator)
        return _("Reading indicator trends…")
    if tool_name == "search_indicator_bank":
        q = _short_label(args.get("query") or "", 48)
        if q:
            return _("Searching the Indicator Bank for '%(snippet)s'…", snippet=q)
        return _("Searching the Indicator Bank…")
    if tool_name == "browse_indicators":
        return _("Browsing indicators in the Indicator Bank…")
    if tool_name == "get_indicator_bank_stats":
        return _("Reading Indicator Bank statistics…")
    if tool_name == "get_indicator_usage_stats":
        indicator = _short_label(args.get("indicator_name") or "")
        if indicator:
            return _("Checking how %(indicator)s is used…", indicator=indicator)
        return _("Checking indicator usage…")
    if tool_name == "get_indicator_change_history":
        indicator = _short_label(args.get("indicator_name") or "")
        if indicator:
            return _("Reading change history for %(indicator)s…", indicator=indicator)
        return _("Reading indicator change history…")
    if tool_name == "list_indicator_suggestions":
        return _("Reviewing indicator suggestions…")
    if tool_name == "analyze_unified_plans_focus_areas":
        return _("Analyzing Unified Plans focus areas…")
    if tool_name == "compare_countries":
        return _("Comparing countries…")
    if tool_name == "validate_against_guidelines":
        return _("Checking values against guidelines…")
    if tool_name == "search_workflow_docs":
        q = _short_label(args.get("query") or "", 48)
        if q:
            return _("Searching how-to guides for '%(query)s'…", query=q)
        return _("Searching how-to guides…")
    if tool_name == "get_workflow_guide":
        return _("Opening workflow guide…")
    if tool_name == "get_user_assignments":
        country = args.get("country_identifier") or ""
        if country:
            return _("Checking assignments for %(country)s…", country=country)
        return _("Checking your assignments…")
    if tool_name == "get_assignment_indicator_values":
        return _("Reading reported values for this assignment…")
    if tool_name == "get_upr_kpi_timeseries":
        country = args.get("country_identifier") or ""
        metric = _short_label(args.get("metric") or "")
        if country and metric:
            return _("Reading %(metric)s over time from Unified Plans for %(country)s…", metric=metric, country=country)
        if country:
            return _("Reading Unified Plans trends for %(country)s…", country=country)
        return _("Reading Unified Plans trends…")
    return _("Checking data…")


def format_tool_args_detail(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Short one-line detail for progress panels."""
    if not tool_args:
        return ""
    if _upr_ux().suppress_format_tool_args_detail_for_tool(tool_name):
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
            logger.debug("search_documents format_tool_args_detail failed: %s", e)
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
            logger.debug("list_documents format_tool_args_detail failed: %s", e)
            return ""
    skip = {"_progress_callback"}
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


def plan_step_message(plan: Optional[Any], query: Optional[str] = None) -> str:
    """User-facing main line for the planning step."""
    if plan is None:
        return _("This needs multiple steps — starting…")
    return _("I know how to answer this — fetching data…")


def format_plan_for_step(plan: Optional[Any], query: Optional[str] = None) -> str:
    """Optional detail line for the planning step (what will be fetched first)."""
    if plan is None:
        return ""
    return step_display_message(plan.tool_name, plan.tool_args or {})


def _document_titles_from_result(result: Any, max_titles: int = 3) -> List[str]:
    titles: List[str] = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = (
            result.get("documents")
            or result.get("chunks")
            or result.get("results")
            or result.get("result")
            or []
        )
        if not isinstance(items, list):
            items = []
    else:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (
            item.get("title")
            or item.get("document_title")
            or item.get("name")
            or item.get("filename")
        )
        if title:
            t = str(title).strip()
            if t and t not in titles:
                titles.append(t[:60] + ("…" if len(t) > 60 else ""))
        if len(titles) >= max_titles:
            break
    return titles


def format_tool_result_summary(tool_name: str, tool_result: Optional[Dict[str, Any]]) -> str:
    """
    Build a human-readable one-line summary after a tool completes (for step_detail).
    """
    if not tool_result or not isinstance(tool_result, dict):
        return ""
    if not tool_result.get("success", True) or tool_result.get("error"):
        err = str(tool_result.get("error") or _("No results found.")).strip()
        if len(err) > 120:
            err = err[:117] + "…"
        return _("Couldn't complete this step — %(detail)s", detail=err)

    payload = tool_result.get("result")
    if tool_name in ("search_documents", "search_documents_hybrid", "list_documents"):
        total = None
        returned = None
        if isinstance(payload, dict):
            total = payload.get("total_count")
            returned = payload.get("returned_count")
            items = payload.get("result") or payload.get("documents") or payload.get("chunks") or []
        elif isinstance(payload, list):
            items = payload
            returned = len(payload)
        else:
            items = []
        if total is None and isinstance(items, list):
            total = len(items)
        if returned is None and isinstance(items, list):
            returned = len(items)
        count = int(total if total is not None else returned or 0)
        if count <= 0:
            return _("No matching documents found.")
        titles = _document_titles_from_result(payload if isinstance(payload, dict) else items)
        if titles:
            joined = ", ".join(titles[:3])
            if count > len(titles):
                return _("Found %(count)d results — %(sample)s", count=count, sample=joined)
            return _("Found %(count)d — %(sample)s", count=count, sample=joined)
        return _("Found %(count)d results · reviewing…", count=count)

    if tool_name == "search_indicator_bank":
        data = payload if isinstance(payload, dict) else {}
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        count = int(data.get("count") if data.get("count") is not None else len(matches))
        if count <= 0:
            return _("No matching indicators in the Indicator Bank.")
        names = [
            _short_label(str(m.get("name") or ""), 36)
            for m in matches[:3]
            if isinstance(m, dict) and (m.get("name") or "").strip()
        ]
        if names:
            return _("Found %(count)d indicators — %(sample)s", count=count, sample=", ".join(names))
        return _("Found %(count)d indicators · reviewing…", count=count)

    if tool_name in (
        "get_indicator_values_for_all_countries",
        "get_upr_kpi_values_for_all_countries",
        "get_form_field_values_for_all_countries",
    ):
        data = payload if isinstance(payload, dict) else {}
        count = data.get("count")
        if count is None and isinstance(data.get("rows"), list):
            count = len(data["rows"])
        count = int(count or 0)
        if count <= 0:
            return _("No country data returned for this query.")
        return _("Found data for %(count)d countries · reviewing…", count=count)

    if tool_name == "browse_indicators":
        data = payload if isinstance(payload, dict) else {}
        count = int(data.get("total_count") or data.get("count") or 0)
        if count <= 0:
            return _("No indicators matched these filters.")
        return _("Found %(count)d indicators · reviewing…", count=count)

    if tool_name in ("get_indicator_value", "get_upr_kpi_value", "get_indicator_timeseries", "get_upr_kpi_timeseries"):
        if payload:
            return _("Found data · reviewing…")
        return _("No data available for this selection.")

    if tool_name == "get_country_information":
        return _("Found country profile · reviewing…") if payload else _("No country information found.")

    if tool_name == "analyze_unified_plans_focus_areas":
        data = payload if isinstance(payload, dict) else {}
        plans = int(data.get("plans_analyzed") or data.get("plan_count") or data.get("count") or 0)
        if plans > 0:
            return _("Analyzed %(count)d Unified Plans · reviewing…", count=plans)
        return _("Analysis complete · reviewing…")

    if tool_name == "compare_countries":
        data = payload if isinstance(payload, dict) else {}
        count = int(data.get("comparison_count") or len(data.get("comparisons") or []) or 0)
        if count > 0:
            return _("Compared %(count)d countries · reviewing…", count=count)
        return _("Comparison complete · reviewing…")

    if tool_name in ("search_workflow_docs",):
        items = payload if isinstance(payload, list) else []
        count = len(items)
        if count <= 0:
            return _("No matching guides found.")
        return _("Found %(count)d guides · reviewing…", count=count)

    if payload:
        return _("Done — reviewing what I found…")
    return _("No results found.")


def emit_tool_result_step_detail(
    on_step_callback: Optional[Any],
    tool_name: str,
    tool_result: Optional[Dict[str, Any]],
) -> None:
    """Emit a step_detail line summarizing a completed tool call."""
    if not callable(on_step_callback):
        return
    summary = format_tool_result_summary(tool_name, tool_result)
    if not summary:
        return
    try:
        on_step_callback(None, summary)
    except TypeError:
        on_step_callback(summary)
    except Exception as e:
        logger.debug("emit_tool_result_step_detail failed: %s", e)
