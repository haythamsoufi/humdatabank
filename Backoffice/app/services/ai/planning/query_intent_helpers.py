"""
Query intent and helper utilities for the agent executor.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

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


def extract_matrix_share_tool_result(steps: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Return the latest bulk form-field matrix share tool result from agent steps."""
    if not steps:
        return None
    for step in reversed(steps):
        action = (step or {}).get("action")
        if action != "get_form_field_values_for_all_countries":
            continue
        obs = (step or {}).get("observation")
        payload = obs
        if isinstance(obs, dict) and "result" in obs:
            payload = obs.get("result")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = None
        if isinstance(payload, dict) and payload.get("matrix_share_rows") and payload.get("success"):
            return payload
    return None


def build_matrix_share_text_response(payload: Dict[str, Any]) -> str:
    """Concise user-facing summary when the platform renders a matrix-share table."""
    count = int(payload.get("count") or len(payload.get("rows") or []) or 0)
    scanned = payload.get("countries_with_data")
    min_pct = payload.get("min_share_pct")
    field = str(payload.get("field_label_resolved") or payload.get("field_label_or_name") or "form matrix").strip()
    template = str(payload.get("template_name") or "").strip()
    share_rows = payload.get("matrix_share_rows") or []
    rows = payload.get("rows") or []

    source_phrase = " or ".join(str(r) for r in share_rows) if share_rows else "selected sources"
    threshold = f"≥{min_pct:g}% " if isinstance(min_pct, (int, float)) else ""
    scope = f"**{count}** National Societies"
    if isinstance(scanned, int) and scanned > count:
        scope += f" (of **{scanned}** with {field} data)"

    line1 = f"{scope} receive {threshold}of their {field} funding from **{source_phrase}**"
    if template:
        line1 += f" in **{template}**"
    line1 += "."

    home_label = foreign_label = None
    for label in share_rows:
        low = str(label).lower()
        if "home" in low and "government" in low:
            home_label = label
        elif "foreign" in low and "government" in low:
            foreign_label = label

    home_n = foreign_n = 0
    for row in rows:
        matching = row.get("matching_sources") or []
        if home_label and home_label in matching:
            home_n += 1
        if foreign_label and foreign_label in matching:
            foreign_n += 1

    line2_parts: List[str] = []
    if count > 0 and (home_label or foreign_label):
        if home_n and not foreign_n:
            line2_parts.append(
                f"All **{count}** match via **{home_label or 'Home Government'}**; "
                "none via foreign government alone."
            )
        elif foreign_n and not home_n:
            line2_parts.append(f"All **{count}** match via **{foreign_label or 'Foreign Government'}**.")
        elif home_n or foreign_n:
            line2_parts.append(
                f"**{home_n}** via home government, **{foreign_n}** via foreign government "
                "(some countries may match both criteria)."
            )
    line2 = " ".join(line2_parts)

    kpi = payload.get("denominator_kpi_code")
    denom_used = f"**{kpi}** when reported, otherwise matrix row sum" if kpi else "matrix row sum"
    line3 = f"Percentages use {denom_used}. Reporting periods vary by country — see the table for details."

    org = payload.get("organization_name") or "Humanitarian Databank"
    source_line = f"- {org} — {template + ' ' if template else ''}{field} matrix (bulk query)"
    parts = [p for p in (line1, line2, line3) if p]
    return "\n\n".join(parts) + f"\n\n## Sources\n\n{source_line}"


_BULK_DATABANK_TOOLS = frozenset({
    "get_indicator_values_for_all_countries",
    "get_form_field_values_for_all_countries",
    "get_upr_kpi_values_for_all_countries",
})


def bulk_databank_tool_satisfied(steps: Optional[List[Dict[str, Any]]]) -> bool:
    """True when a bulk databank tool already returned rows for this query."""
    if not steps:
        return False
    for step in steps:
        action = (step or {}).get("action")
        if action not in _BULK_DATABANK_TOOLS:
            continue
        obs = (step or {}).get("observation")
        payload = obs
        if isinstance(obs, dict) and "result" in obs:
            payload = obs.get("result")
        if isinstance(payload, str):
            try:
                import json
                payload = json.loads(payload)
            except Exception:
                payload = None
        if isinstance(payload, dict) and payload.get("success"):
            count = payload.get("count")
            rows = payload.get("rows")
            if isinstance(count, int) and count > 0:
                return True
            if isinstance(rows, list) and len(rows) > 0:
                return True
    return False
