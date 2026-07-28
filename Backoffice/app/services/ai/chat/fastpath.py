"""
AI fast-path helpers.

Goal: deterministically answer simple "what is the number of X in Country in 2024" questions
without relying on LLM tool-calling behavior.

These helpers are RBAC-safe because they delegate to data_retrieval_service.get_value_breakdown(),
which enforces country access for the current_user.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import Country

logger = logging.getLogger(__name__)
from app.services.data_retrieval_service import get_value_breakdown as svc_get_value_breakdown
from app.utils.sql_utils import safe_ilike_pattern


_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _format_number(value: Any) -> str:
    try:
        num = float(value)
    except Exception as e:
        logger.debug("_format_number failed for %r: %s", value, e)
        return str(value)
    if num.is_integer():
        return f"{int(num):,}"
    return f"{num:,.2f}".rstrip("0").rstrip(".")


def _detect_indicator_identifier(message: str) -> Optional[str]:
    """
    Very small heuristic mapping for common 'numeric' asks.
    Extend carefully; prefer mapping to stable IndicatorBank names users use.
    """
    msg = (message or "").lower()
    if re.search(r"\bvolunteer(s)?\b", msg):
        return "volunteers"
    if re.search(r"\bpopulation\b", msg):
        return "population"
    if re.search(r"\bbudget\b", msg):
        return "budget"
    return None


def _find_country(country_identifier: str, available_countries: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Resolve a country from either a provided allowed list (preferred for focal points)
    or from DB (admin/system).
    Returns a dict: {id, name, iso3}
    """
    cid = (country_identifier or "").strip()
    if not cid:
        return None

    cid_lower = cid.lower()

    # Prefer provided list (already RBAC-filtered)
    if available_countries:
        for c in available_countries:
            name = (c.get("name") or "").lower()
            iso3 = (c.get("iso3") or "").lower()
            if cid_lower == name or cid_lower == iso3:
                return {"id": c.get("id"), "name": c.get("name"), "iso3": c.get("iso3")}
        for c in available_countries:
            name = (c.get("name") or "").lower()
            if name and name in cid_lower:
                return {"id": c.get("id"), "name": c.get("name"), "iso3": c.get("iso3")}

    # DB fallback (RBAC still enforced downstream by svc_get_value_breakdown)
    country = None
    if len(cid) == 3:
        country = Country.query.filter(Country.iso3.ilike(safe_ilike_pattern(cid, prefix=False, suffix=False))).first()
    if not country:
        country = Country.query.filter(Country.name.ilike(safe_ilike_pattern(cid))).first()
    if not country:
        return None
    return {"id": country.id, "name": country.name, "iso3": getattr(country, "iso3", "")}


def looks_like_value_question(message: str) -> bool:
    """
    Cheap guard: only attempt fast-path for messages that plausibly ask for a numeric value.
    """
    msg = (message or "").lower()
    if not msg:
        return False

    # Must mention a known indicator keyword (we keep this conservative)
    if not _detect_indicator_identifier(msg):
        return False

    # Usually contains a year OR a clear "how many/number/total" phrase
    if _YEAR_RE.search(msg):
        return True
    if any(p in msg for p in ("how many", "number of", "total", "what is the number", "what's the number")):
        return True
    return False


def try_answer_value_question(
    *,
    message: str,
    preferred_language: str = "en",
    available_countries: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[str], List[str]]:
    """
    Attempt to answer a numeric value question deterministically.

    Returns:
      (html_answer_or_none, function_calls_used)
    """
    if not looks_like_value_question(message):
        return None, []

    msg = (message or "").strip()
    msg_lower = msg.lower()

    # Period (optional but commonly present)
    year_match = _YEAR_RE.search(msg_lower)
    period = year_match.group(1) if year_match else None

    # Country: heuristic extraction via DB search. We try to find a country that appears in the message.
    # If we have an RBAC-scoped country list, check those first.
    country = None
    if available_countries:
        for c in available_countries:
            name = (c.get("name") or "").lower()
            iso3 = (c.get("iso3") or "").lower()
            if name and name in msg_lower:
                country = {"id": c.get("id"), "name": c.get("name"), "iso3": c.get("iso3")}
                break
            if iso3 and re.search(rf"\b{re.escape(iso3)}\b", msg_lower):
                country = {"id": c.get("id"), "name": c.get("name"), "iso3": c.get("iso3")}
                break

    # If not found, attempt DB scan via a lightweight "best effort" heuristic:
    # look for "in <country>" / "for <country>" patterns
    if not country:
        # Stop before "in 2024", "for 2024", a bare year, punctuation, or end-of-string.
        m = re.search(
            r"\b(?:in|for)\s+([a-zA-Z][a-zA-Z\s\-'().]{2,80}?)(?=\s+(?:in|for)\s+\d{4}|\s+\d{4}\b|[?.!,]|$)",
            msg,
        )
        if m:
            country = _find_country(m.group(1), available_countries=available_countries)

    if not country:
        return None, []

    indicator_identifier = _detect_indicator_identifier(msg)
    if not indicator_identifier:
        return None, []

    # Call service (RBAC enforced inside).
    result = svc_get_value_breakdown(int(country["id"]), indicator_identifier, period)
    if not isinstance(result, dict):
        return None, []
    if result.get("error"):
        # Return an explicit message (still useful, avoids hanging UX)
        return f"⚠️ {result['error']}", ["get_value_breakdown"]

    indicator = result.get("indicator") or {}
    ind_name = indicator.get("name") or indicator_identifier
    unit = indicator.get("unit") or ""
    total = result.get("total")

    # Check for alternative indicators with data
    alternatives = result.get("alternative_indicators") or []

    # If there are no submitted records for the selected indicator, check if alternatives exist
    records_count = result.get("records_count") or 0
    if records_count <= 0:
        period_txt = f" ({period})" if period else ""
        # If we have alternatives with data, show them instead of just saying "no data"
        if isinstance(alternatives, list) and len(alternatives) > 0:
            items = "".join(
                f"<li><strong>{a.get('name') or a.get('id')}</strong> — {a.get('records_count', 0)} submitted value(s)</li>"
                for a in alternatives[:8]
            )
            return (
                f"<strong>{country['name']}{period_txt} — The indicator \"{ind_name}\" has no submitted data.</strong>"
                f"<br/>However, I found {len(alternatives)} other matching indicator(s) with data:"
                f"<ul>{items}</ul>"
                f"<br/>Please specify which indicator you're looking for.",
                ["get_value_breakdown"],
            )
        else:
            # No data and no alternatives
            return (
                f"<strong>{country['name']}{period_txt} — {ind_name}:</strong> No submitted data found.",
                ["get_value_breakdown"],
            )

    # If the identifier is ambiguous and multiple indicators have submitted data, ask the user to choose.
    if isinstance(alternatives, list) and len(alternatives) > 1:
        period_txt = f" ({period})" if period else ""
        items = "".join(
            f"<li><strong>{a.get('name') or a.get('id')}</strong> — {a.get('records_count', 0)} submitted value(s)</li>"
            for a in alternatives[:8]
        )
        return (
            f"<strong>{country['name']}{period_txt} — I found multiple matching indicators with data.</strong>"
            f"<br/>Which one do you mean?<ul>{items}</ul>",
            ["get_value_breakdown"],
        )

    total_txt = _format_number(total)
    period_txt = f" ({period})" if period else ""
    unit_txt = f" {unit}".rstrip()

    # Minimal language variations (HTML-safe, matches mobile rendering).
    lang = (preferred_language or "en").strip().lower().split("_", 1)[0]
    if lang == "es":
        return (
            f"<strong>{country['name']}{period_txt} — {ind_name}:</strong> {total_txt}{unit_txt}",
            ["get_value_breakdown"],
        )
    if lang == "fr":
        return (
            f"<strong>{country['name']}{period_txt} — {ind_name} :</strong> {total_txt}{unit_txt}",
            ["get_value_breakdown"],
        )
    if lang == "ar":
        return (
            f"<strong>{country['name']}{period_txt} — {ind_name}:</strong> {total_txt}{unit_txt}",
            ["get_value_breakdown"],
        )
    return (
        f"<strong>{country['name']}{period_txt} — {ind_name}:</strong> {total_txt}{unit_txt}",
        ["get_value_breakdown"],
    )
