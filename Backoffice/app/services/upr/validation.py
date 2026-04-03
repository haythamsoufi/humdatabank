"""
upr.validation
──────────────
UPR-specific validation helpers extracted from the monolithic
``ai_formdata_validation_service`` module.

Public API
----------
upr_kpi_applicable              – guardrail: is a UPR KPI card relevant for this indicator?
upr_document_label              – human-readable label for a UPR document source
upr_suggestion_reason           – user-facing reason string for a UPR-derived suggestion
retrieve_upr_kpi_reference      – fetch + format a UPR KPI reference value
format_ifrc_upr_extraction      – prettify raw IFRC/UPR extraction tokens
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_NUMBER_TOKEN_RE = re.compile(r"[-+]?\d[\d,\u00A0\u202F ]*(?:\.\d+)?")


# ---------------------------------------------------------------------------
# Private helpers (duplicated from ai_formdata_validation_service for
# self-containment; they are tiny pure-functions).
# ---------------------------------------------------------------------------

def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception as e:
        logger.debug("_safe_int failed for %r: %s", v, e)
        return None


def _safe_str(v: Any) -> str:
    try:
        s = str(v).strip()
    except Exception as e:
        logger.debug("_safe_str failed: %s", e)
        return ""
    if s.lower() in ("none", "null", "undefined"):
        return ""
    return s


def _parse_int_number(value: Any) -> Optional[int]:
    """
    Lenient integer parser that handles thousand separators, currency prefixes, etc.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        value = str(value)

    s = str(value).strip()
    if not s:
        return None

    m = _NUMBER_TOKEN_RE.search(s)
    if not m:
        return None
    token = (m.group(0) or "").strip()
    if not token:
        return None

    token = token.replace("\u00A0", "").replace("\u202F", "").replace(" ", "")

    if ("," not in token) and re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", token or ""):
        token = token.replace(".", "")
    else:
        token = token.replace(",", "")

    try:
        d = Decimal(token)
    except (InvalidOperation, ValueError):
        return None

    try:
        i = int(d.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception as e:
        logger.debug("_parse_int_number to_integral failed: %s", e)
        return None
    return i


def _format_int(n: Optional[int]) -> str:
    if n is None:
        return "-"
    try:
        return f"{int(n):,}"
    except Exception as e:
        logger.debug("_format_int failed for %r: %s", n, e)
        return str(n)


def _infer_primary_keyword(form_item_label: Optional[str]) -> Optional[str]:
    """Best-effort mapping of a form item label to a document KPI keyword."""
    if not form_item_label:
        return None
    s = str(form_item_label).strip().lower()
    if "volunteer" in s:
        return "volunteers"
    if "staff" in s:
        return "staff"
    if "branch" in s:
        return "branches"
    if "local unit" in s or "localunit" in s:
        return "local units"
    return None


def _title_case_report_type(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ").strip()
    mapping = {
        "midyear report": "Mid-year Report",
        "mid year report": "Mid-year Report",
        "annual report": "Annual Report",
        "unified plan": "Unified Plan",
    }
    key = re.sub(r"\s+", " ", s.lower()).strip()
    if key in mapping:
        return mapping[key]
    return " ".join(w.capitalize() if w.isalpha() else w for w in re.split(r"\s+", s))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upr_kpi_applicable(form_item_label: Optional[str], keyword: str) -> bool:
    """
    Guardrail: only use UPR KPI cards for truly *generic* headcount indicators (e.g. "number of volunteers").
    Do NOT use UPR KPI cards for subset/qualified indicators like "volunteers covered by accident insurance",
    "active volunteers", "trained volunteers", etc., since the UPR KPI card typically reports totals.
    """
    if not form_item_label or not keyword:
        return False
    s = str(form_item_label).strip().lower()

    subset_terms = [
        "insurance", "insured", "accident", "covered", "coverage",
        "active", "trained", "training", "certified", "accredited",
        "first aid", "aid", "blood", "donor",
        "youth", "women", "men", "girls", "boys", "children",
        "with disability", "disability", "disabled",
        "migrants", "refugee", "refugees",
        "reached", "assisted", "benefited", "beneficiaries",
        "percentage", "proportion", "rate", "%",
        "death", "deaths", "fatality", "fatalities", "on duty", "injuries", "injured",
    ]
    if any(t in s for t in subset_terms):
        return False

    k = str(keyword).strip().lower()
    return k in {"branches", "staff", "volunteers", "local units"}


def upr_document_label(upr: Optional[Dict[str, Any]]) -> str:
    """
    Build a short, clear label for the UPR document source (e.g. "UPR Plan 2026") for use in opinions.
    """
    if not isinstance(upr, dict):
        return "UPR document"
    source = upr.get("source") if isinstance(upr.get("source"), dict) else {}
    title = (source.get("document_title") or "").strip()
    filename = (source.get("document_filename") or "").strip()
    year = None
    for s in (title, filename):
        if s:
            m = _YEAR_RE.findall(s)
            if m:
                try:
                    year = max(int(x) for x in m)
                    break
                except Exception as e:
                    logger.debug("Optional validation step failed: %s", e)
    if title and len(title) <= 80:
        return title
    if year is not None:
        return f"UPR Plan {year}"
    return "UPR document"


def upr_suggestion_reason(upr: Optional[Dict[str, Any]], value_int: int) -> str:
    """
    Build a precise, user-facing reason string for a UPR-derived suggestion.
    Includes document title + page when available (from get_upr_kpi_value()).
    """
    try:
        src = upr.get("source") if isinstance(upr, dict) and isinstance(upr.get("source"), dict) else {}
        title = (src.get("document_title") or "").strip()
        page = src.get("page_number")
        extraction = (src.get("extraction") or "").strip()
        conf = src.get("confidence")
        conf_txt = ""
        try:
            if conf is not None:
                cf = float(conf)
                if cf == cf:  # not NaN
                    conf_txt = f", confidence {int(round(cf * 100))}%"
        except Exception as e:
            logger.debug("confidence format failed: %s", e)
            conf_txt = ""
        page_txt = f" (p. {int(page)})" if isinstance(page, (int, float)) and int(page) > 0 else ""
        title_txt = f"'{title}'" if title else upr_document_label(upr)
        extraction_txt = f", extraction: {extraction}" if extraction else ""
        return f"Structured KPI card in {title_txt}{page_txt} reports {_format_int(int(value_int))}{conf_txt}{extraction_txt}."
    except Exception as e:
        logger.debug("upr_suggestion_reason failed: %s", e)
        return f"Structured KPI evidence suggests {_format_int(int(value_int))}."


def retrieve_upr_kpi_reference(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Best-effort retrieval of an IFRC/UPR KPI reference value for a small set of generic headcount indicators.

    This is a structured signal derived from accessible AI documents that carry UPR KPI metadata, and is used
    as additional evidence alongside narrative document chunks and historical submissions.
    """
    try:
        label = context.get("form_item_label")
        keyword = _infer_primary_keyword(label) or ""
        metric = {
            "branches": "branches",
            "staff": "staff",
            "volunteers": "volunteers",
            "local units": "local_units",
        }.get(str(keyword or "").strip().lower())
        if not metric:
            return None
        if not upr_kpi_applicable(label, keyword):
            return None
        if not context.get("country_id"):
            return None
        from app.services.upr.data_retrieval import get_upr_kpi_value

        upr = get_upr_kpi_value(
            country_identifier=int(context["country_id"]),
            metric=str(metric),
            prefer_year=_safe_int(context.get("period_year")),
        )
        if not isinstance(upr, dict) or not upr.get("success"):
            return None
        val = upr.get("value")
        if val is None or str(val).strip() == "":
            return None
        out: Dict[str, Any] = {
            "metric": upr.get("metric") or metric,
            "value": str(val).strip(),
            "value_int": _parse_int_number(val),
            "source": upr.get("source") if isinstance(upr.get("source"), dict) else None,
            "notes": upr.get("notes"),
        }
        return out
    except Exception as e:
        logger.debug("retrieve_upr_kpi_reference failed: %s", e)
        return None


def format_ifrc_upr_extraction(extraction: str) -> str:
    """
    Turn internal extraction tokens like:
      'ype=midyear_report; year=2024 - National Society local units: 94 - ...'
    into a user-friendly one-liner.
    """
    s = _safe_str(extraction)
    if not s:
        return ""
    s2 = s.replace("\r", " ").replace("\n", " ").strip()
    meta: Dict[str, str] = {}
    try:
        left, _, right = s2.partition("-")
        for part in re.split(r"[;,\|]\s*", left):
            if "=" in part:
                k, v = part.split("=", 1)
                meta[k.strip().lower()] = v.strip()
        if not meta:
            return s2
        pieces = []
        rtype = meta.get("ype") or meta.get("pe") or meta.get("type")
        year = meta.get("year")
        if rtype:
            pieces.append(_title_case_report_type(rtype))
        if year and str(year).strip().isdigit():
            pieces.append(str(int(year)))
        prefix = " — ".join([p for p in pieces if p])
        if right:
            right_clean = right.strip()
            right_clean = re.sub(r"\s*-\s*", "; ", right_clean)
            return (f"{prefix} — {right_clean}" if prefix else right_clean).strip()
        return prefix or s2
    except Exception as e:
        logger.debug("prefix merge failed: %s", e)
        return s2
