"""UPR KPI applicability and reference helpers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.ai.validation.parsers import (
    _YEAR_RE,
    _format_int,
    _infer_primary_keyword,
    _parse_int_number,
    _safe_int,
)

logger = logging.getLogger(__name__)


def _upr_kpi_applicable(form_item_label: Optional[str], keyword: str) -> bool:
    """
    Guardrail: only use UPR KPI cards for truly *generic* headcount indicators (e.g. "number of volunteers").
    Do NOT use UPR KPI cards for subset/qualified indicators like "volunteers covered by accident insurance",
    "active volunteers", "trained volunteers", etc., since the UPR KPI card typically reports totals.
    """
    if not form_item_label or not keyword:
        return False
    s = str(form_item_label).strip().lower()
    k = str(keyword).strip().lower()

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

    return k in {"branches", "staff", "volunteers", "local units"}


def _required_terms_for_claims(form_item_label: Optional[str], keyword: str) -> List[str]:
    """Require qualifying terms near extracted numbers for subset indicators."""
    if not form_item_label or not keyword:
        return []
    s = str(form_item_label).strip().lower()
    k = str(keyword).strip().lower()

    if k == "volunteers" and ("insurance" in s or "insured" in s or "accident" in s):
        return ["insurance", "insured", "accident"]
    return []


def _upr_document_label(upr: Optional[Dict[str, Any]]) -> str:
    """Build a short label for the UPR document source (e.g. "UPR Plan 2026")."""
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


def _upr_suggestion_reason(upr: Optional[Dict[str, Any]], value_int: int) -> str:
    """Build a user-facing reason string for a UPR-derived suggestion."""
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
                if cf == cf:
                    conf_txt = f", confidence {int(round(cf * 100))}%"
        except Exception as e:
            logger.debug("confidence format failed: %s", e)
            conf_txt = ""
        page_txt = f" (p. {int(page)})" if isinstance(page, (int, float)) and int(page) > 0 else ""
        title_txt = f"'{title}'" if title else _upr_document_label(upr)
        extraction_txt = f", extraction: {extraction}" if extraction else ""
        return f"Structured KPI card in {title_txt}{page_txt} reports {_format_int(int(value_int))}{conf_txt}{extraction_txt}."
    except Exception as e:
        logger.debug("_upr_suggestion_reason failed: %s", e)
        return f"Structured KPI evidence suggests {_format_int(int(value_int))}."


def retrieve_upr_kpi_reference(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Best-effort retrieval of an IFRC/UPR KPI reference value for generic headcount indicators.
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
        if not _upr_kpi_applicable(label, keyword):
            return None
        if not context.get("country_id"):
            return None
        from app.services.data_retrieval.service import get_upr_kpi_value as get_upr_kpi_value_service

        upr = get_upr_kpi_value_service(
            country_identifier=int(context["country_id"]),
            metric=str(metric),
            prefer_year=_safe_int(context.get("period_year")),
        )
        if not isinstance(upr, dict) or not upr.get("success"):
            return None
        val = upr.get("value")
        if val is None or str(val).strip() == "":
            return None
        return {
            "metric": upr.get("metric") or metric,
            "value": str(val).strip(),
            "value_int": _parse_int_number(val),
            "source": upr.get("source") if isinstance(upr.get("source"), dict) else None,
            "notes": upr.get("notes"),
        }
    except Exception as e:
        logger.debug("retrieve_upr_kpi_reference failed: %s", e)
        return None
