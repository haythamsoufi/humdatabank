"""
Query intent and helper utilities for the agent executor.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


_USAGE_HELP_RE = re.compile(
    r"\b("
    r"how\s+to|how\s+do\s+i|how\s+can\s+i|where\s+is|where\s+can\s+i\s+find|"
    r"where\s+do\s+i\s+find|guide|help|steps?|workflow|menu|screen|page|"
    r"click|navigate|open|create|assign|assignment|template"
    r")\b",
    re.IGNORECASE,
)

_DOCUMENT_LOOKUP_RE = re.compile(
    r"\b("
    r"document|pdf|report|file|download|upload|excerpt|page\s+\d+|"
    r"search\s+documents|in\s+the\s+documents|from\s+documents"
    r")\b",
    re.IGNORECASE,
)
from typing import Any, Dict, List, Optional, Tuple


def bulk_tool_call_signature(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, str]:
    """Build a deterministic signature for idempotent bulk tools."""
    args = (tool_args or {}).copy()
    args_normalized = {k: v for k, v in sorted(args.items()) if v is not None}
    args_key = json.dumps(args_normalized, sort_keys=True, default=str)
    return (tool_name, args_key)


def build_reasoning_doc_query_from_steps(
    steps: List[Dict[str, Any]],
    fallback_query: str,
) -> Tuple[str, Optional[str]]:
    """
    Build a focused document search query to explain major time-series changes.
    Extract country + indicator + key change years from prior
    get_indicator_timeseries steps when available.
    """
    country = ""
    indicator = ""
    years: List[int] = []
    try:
        for s in reversed(steps or []):
            if (s or {}).get("action") != "get_indicator_timeseries":
                continue
            ai = (s or {}).get("action_input") or {}
            if isinstance(ai, dict):
                country = str(ai.get("country_identifier") or "").strip() or country
                indicator = str(ai.get("indicator_name") or "").strip() or indicator
            obs = (s or {}).get("observation") or {}
            result = obs.get("result") if isinstance(obs, dict) else None
            series = (result or {}).get("series") if isinstance(result, dict) else None
            series = series if isinstance(series, list) else []
            best_inc = None
            best_dec = None
            prev = None
            for pt in series:
                if not isinstance(pt, dict):
                    continue
                try:
                    y = int(pt.get("year"))
                    v = float(pt.get("value"))
                except Exception as e:
                    logger.debug("build_reasoning_doc_query_from_steps point parse failed: %s", e)
                    continue
                if prev is not None:
                    py, pv = prev
                    delta = v - pv
                    if best_inc is None or delta > best_inc[0]:
                        best_inc = (delta, py, y)
                    if best_dec is None or delta < best_dec[0]:
                        best_dec = (delta, py, y)
                prev = (y, v)
            for tup in (best_inc, best_dec):
                if not tup:
                    continue
                _, y0, y1 = tup
                years.extend([int(y0), int(y1)])
            break
    except Exception as e:
        logger.debug("build_reasoning_doc_query_from_steps failed: %s", e)
    years = sorted({y for y in years if 1900 <= int(y) <= 2100})
    years_part = " ".join(str(y) for y in years[:6])
    core = " ".join([p for p in [country, indicator, years_part] if p]).strip()
    if not core:
        core = (fallback_query or "").strip()
    q = (core + " COVID-19 reporting definition change recruitment campaign emergency response data cleanup").strip()
    return q, (country or None)


def infer_metric_label_from_query(query: str) -> str:
    """Best-effort metric label inference for per-country extraction outputs."""
    q = str(query or "").strip().lower()
    if "volunteer" in q:
        return "Volunteers"
    if "staff" in q:
        return "Staff"
    if "branch" in q:
        return "Branches"
    if "local unit" in q or "local_units" in q or "local units" in q:
        return "Local units"
    return "Value"


def build_per_country_values_text_response(payload: Dict[str, Any]) -> str:
    """User-facing text for document-extracted per-country values (often partial)."""
    try:
        metric = str((payload or {}).get("metric") or "Value").strip() or "Value"
        n = len((payload or {}).get("countries") or [])
    except Exception as e:
        logger.debug("build_per_country_values_text_response parse failed: %s", e)
        metric = "Value"
        n = 0
    if n <= 0:
        return (
            f"I searched the available documents, but couldn’t extract a reliable **{metric}** total by country "
            "from the text results."
        )
    if n == 1:
        return (
            f"I extracted a **best-effort** per-country value for **{metric}** from document text. "
            "Coverage is partial (1 country with a clear total found)."
        )
    return (
        f"I extracted **best-effort** per-country values for **{metric}** from document text. "
        f"Coverage is partial (**{n} countries** with a clear total found)."
    )


def is_assignment_form_question(query: str) -> bool:
    """
    True if query is about assignment/form data and should be answered with
    assignment/template tools, not document search.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip().lower()
    assignment_form_phrases = (
        "fdrs",
        "unified country plan",
        "unified country report",
        "indicators",
        "form indicators",
        "assignment indicators",
        "reported values",
        "form values",
        "submitted values",
        "what values did",
        "list of indicators",
        "which indicators",
        "assignment for",
        "form data for",
    )
    return any(p in q for p in assignment_form_phrases)


# Pattern: user is describing what they see on screen (one country / "only X" in the list).
_DASHBOARD_COUNTRY_LIST_RE = re.compile(
    r"\b("
    r"why\s+(?:am\s+i\s+)?only\s+seeing|"
    r"only\s+seeing\s+(?:(?:one\s+)?country|\w+)\s+(?:in\s+the\s+)?(?:list|list\s+of\s+countries)|"
    r"why\s+(?:do\s+i\s+)?(?:only\s+)?see\s+(?:one\s+)?\w+\s+in\s+the\s+list|"
    r"(?:the\s+)?list\s+of\s+countries\s+(?:only\s+shows|shows\s+only)|"
    r"why\s+(?:does\s+)?(?:the\s+)?dashboard\s+show\s+only"
    r")\b",
    re.IGNORECASE,
)


def is_dashboard_country_list_question(query: str) -> bool:
    """
    True when the user is asking why they only see one country (or a specific country)
    in a list on the UI — typically the dashboard country selector or assigned countries.
    Used together with page_context to avoid routing to document tools.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip()
    if len(q) < 10:
        return False
    return bool(_DASHBOARD_COUNTRY_LIST_RE.search(q))


def is_platform_usage_help_question(query: str) -> bool:
    """
    True when the user is asking how to use/navigate the platform UI rather than
    requesting data extraction from documents or indicators.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip()
    if len(q) < 6:
        return False

    has_usage_signal = bool(_USAGE_HELP_RE.search(q))
    has_document_signal = bool(_DOCUMENT_LOOKUP_RE.search(q))
    has_question_form = "?" in q or q.lower().startswith(("how", "where", "what", "can i"))

    return bool((has_usage_signal and not has_document_signal) or (has_usage_signal and has_question_form))


def is_template_assignment_ambiguous(query: str) -> bool:
    """
    True when 'template' likely refers to assignment/template workflow in the
    platform and needs clarification before document/data search.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip().lower()
    if "template" not in q:
        return False
    if bool(_DOCUMENT_LOOKUP_RE.search(q)):
        return False
    # If users mention period/country/assignment around template, this is very
    # likely assignment workflow intent rather than document lookup.
    if any(k in q for k in ("assignment", "assign", "period", "country", "form", "fdrs")):
        return True
    # Bare "template" asks are frequently workflow/navigation asks in this app.
    return True
