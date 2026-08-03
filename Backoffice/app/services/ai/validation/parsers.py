"""Parsing helpers for AI form-data validation (claim extraction)."""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_PAREN_CODE_RE = re.compile(r"\(([A-Za-z0-9_\-]{1,40})\)")
_NUMBER_TOKEN_RE = re.compile(r"[-+]?\d[\d,\u00A0\u202F ]*(?:\.\d+)?")

def _is_blankish_value(v: Any) -> bool:
    """
    Treat None/empty/"null" (string) as missing.
    Some legacy/import scripts stored the literal string "null" in FormData.value/disagg_data.
    """
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        return (s == "") or (s.lower() == "null")
    return False


def _normalize_disagg_for_presence(d: Any) -> Optional[Dict[str, Any]]:
    """
    Best-effort normalize disagg_data for presence checks.
    Returns None for None/empty/"null"/invalid; returns dict otherwise (even if not fully validated).
    """
    if d is None:
        return None
    if isinstance(d, str):
        s = d.strip()
        if (s == "") or (s.lower() == "null"):
            return None
        # Unexpected string payload; treat as missing rather than erroring downstream.
        # (If we later decide to support JSON-in-string, we can parse here.)
        return None
    if not isinstance(d, dict):
        return None
    if len(d) == 0:
        return None
    values = d.get("values") if isinstance(d.get("values"), dict) else None
    if values is not None:
        has_any = False
        for vv in values.values():
            if vv is None:
                continue
            if isinstance(vv, str) and vv.strip().lower() in ("", "null"):
                continue
            has_any = True
            break
        if not has_any:
            return None
    return d


@dataclass
class ValidationResult:
    status: str  # completed | failed
    verdict: Optional[str]  # good | discrepancy | uncertain
    confidence: Optional[float]
    opinion_text: Optional[str]
    evidence: Dict[str, Any]
    provider: Optional[str]
    model: Optional[str]
    error_message: Optional[str] = None


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception as e:
        logger.debug("_safe_int failed for %r: %s", v, e)
        return None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction of the first JSON object from a model response.
    """
    if not text:
        return None
    s = text.strip()
    # Common: model returns ```json ... ```
    if s.startswith("```"):
        s = s.strip("`")
        # Drop leading 'json' label if present
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = s[start : end + 1]
    try:
        obj = json.loads(blob)
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        logger.debug("_extract_json_object json.loads failed: %s", e)
        return None


def _parse_int_number(value: Any) -> Optional[int]:
    """
    Parse a human-formatted integer: '4,665' -> 4665.
    Returns None when parsing is not possible.
    """
    if value is None:
        return None
    # Guard: bool is an int subclass in Python; never treat it as a numeric value here.
    if isinstance(value, bool):
        return None

    # Fast paths
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        # Convert through string to avoid float repr surprises (e.g. 1.0 -> "1.0")
        value = str(value)

    s = str(value).strip()
    if not s:
        return None

    # Extract the first number-like token (handles prefixes/suffixes like "CHF 5,902.0", "5,902.0%").
    m = _NUMBER_TOKEN_RE.search(s)
    if not m:
        return None
    token = (m.group(0) or "").strip()
    if not token:
        return None

    # Normalize common thousand separators/spaces.
    token = token.replace("\u00A0", "").replace("\u202F", "").replace(" ", "")

    # If token is in a dot-thousands format like "59.270" or "1.234.567", treat dots as thousand separators.
    # (Do NOT do this for decimals like "5902.0".)
    if ("," not in token) and re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", token or ""):
        token = token.replace(".", "")
    else:
        token = token.replace(",", "")

    try:
        d = Decimal(token)
    except (InvalidOperation, ValueError):
        return None

    # Convert to int safely. For values like "5902.0" this returns 5902 (not 59020).
    try:
        i = int(d.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception as e:
        logger.debug("_parse_int_number to_integral failed: %s", e)
        return None
    return i


def _infer_primary_keyword(form_item_label: Optional[str]) -> Optional[str]:
    """
    Best-effort mapping of a form item label to a document KPI keyword.
    """
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

    # Disqualifiers that indicate a subset rather than total headcount.
    subset_terms = [
        "insurance", "insured", "accident", "covered", "coverage",
        "active", "trained", "training", "certified", "accredited",
        "first aid", "aid", "blood", "donor",
        "youth", "women", "men", "girls", "boys", "children",
        "with disability", "disability", "disabled",
        "migrants", "refugee", "refugees",
        "reached", "assisted", "benefited", "beneficiaries",
        "percentage", "proportion", "rate", "%",
        # Death/safety-related: UPR KPI "volunteers" = total headcount, never deaths
        "death", "deaths", "fatality", "fatalities", "on duty", "injuries", "injured",
    ]
    if any(t in s for t in subset_terms):
        return False

    # Only allow for the basic UPR KPI set.
    return k in {"branches", "staff", "volunteers", "local units"}


def _required_terms_for_claims(form_item_label: Optional[str], keyword: str) -> List[str]:
    """
    Extra precision for document-claim extraction.
    When an indicator is a qualified subset (e.g. accident insurance volunteers),
    require that at least one of these terms appears near the extracted number.
    """
    if not form_item_label or not keyword:
        return []
    s = str(form_item_label).strip().lower()
    k = str(keyword).strip().lower()

    if k == "volunteers" and ("insurance" in s or "insured" in s or "accident" in s):
        return ["insurance", "insured", "accident"]
    return []


def _parse_year_from_period(period_name: Any) -> Optional[int]:
    """
    Best-effort parse of a year from AssignedForm.period_name (often '2024', 'FY2024', '2024-2025', etc.)
    """
    if period_name is None:
        return None
    s = str(period_name)
    m = _YEAR_RE.findall(s)
    if not m:
        return None
    try:
        return max(int(x) for x in m)
    except Exception as e:
        logger.debug("_parse_year_from_period failed for %r: %s", period_name, e)
        return None


def _upr_document_label(upr: Optional[Dict[str, Any]]) -> str:
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


def _upr_suggestion_reason(upr: Optional[Dict[str, Any]], value_int: int) -> str:
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
        title_txt = f"'{title}'" if title else _upr_document_label(upr)
        extraction_txt = f", extraction: {extraction}" if extraction else ""
        return f"Structured KPI card in {title_txt}{page_txt} reports {_format_int(int(value_int))}{conf_txt}{extraction_txt}."
    except Exception as e:
        logger.debug("_upr_suggestion_reason failed: %s", e)
        return f"Structured KPI evidence suggests {_format_int(int(value_int))}."


def _format_int(n: Optional[int]) -> str:
    if n is None:
        return "-"
    try:
        return f"{int(n):,}"
    except Exception as e:
        logger.debug("_format_int failed for %r: %s", n, e)
        return str(n)


def _median_int(values: List[int]) -> Optional[int]:
    if not values:
        return None
    vals = sorted(int(v) for v in values)
    mid = len(vals) // 2
    if len(vals) % 2 == 1:
        return vals[mid]
    return int(round((vals[mid - 1] + vals[mid]) / 2.0))


def _extract_keyword_number_claims(
    *,
    keyword: str,
    evidence_chunks: List[Dict[str, Any]],
    max_claims: int = 12,
    required_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract (keyword, number) claims from chunk content.
    Returns a list of dicts containing value_int + citations.
    """
    if not keyword:
        return []

    # Prefer strict, local patterns so we don't "attach" unrelated numbers to a keyword.
    # Examples:
    # - "4,665 volunteers"
    # - "volunteers: 73,000"
    # - "- National Society volunteers: 73,000"
    #
    # We intentionally do NOT use wide "within N characters" matching because UPR/PDF OCR blocks
    # can contain multiple metrics and numbers on the same page.
    kw = re.escape(keyword)
    kw_alt = kw
    if keyword.endswith("s"):
        kw_alt = f"(?:{kw}|{re.escape(keyword[:-1])})"
    num = r"(\d[\d,]*(?:\.\d+)?)"
    pat_colon = re.compile(rf"(?i)\b{kw_alt}\b\s*[:\-]\s*{num}")
    pat_after = re.compile(rf"(?i)\b{num}\s+\b{kw_alt}\b")

    claims: List[Dict[str, Any]] = []

    def _add_claim(chunk: Dict[str, Any], value_raw: str, matched_kw: str, start_idx: int, end_idx: int) -> None:
        if len(claims) >= int(max_claims):
            return
        v_int = _parse_int_number(value_raw)
        if v_int is None:
            return
        content = str(chunk.get("content") or "")
        lo = max(0, start_idx - 80)
        hi = min(len(content), end_idx + 80)
        quote = content[lo:hi].strip()
        if required_terms:
            ql = quote.lower()
            if not any(str(t).lower() in ql for t in required_terms if t):
                return
        claims.append(
            {
                "keyword": keyword,
                "value": v_int,
                "document_id": chunk.get("document_id"),
                "page_number": chunk.get("page_number"),
                "chunk_id": chunk.get("chunk_id"),
                "score": chunk.get("score"),
                "quote": quote[:400],
                "matched": str(matched_kw).lower(),
            }
        )

    for chunk in evidence_chunks or []:
        content = str(chunk.get("content") or "")
        if not content:
            continue

        for m in pat_colon.finditer(content):
            if len(claims) >= int(max_claims):
                break
            matched_kw = keyword
            num_raw = m.group(1) or ""
            _add_claim(chunk, num_raw, matched_kw, m.start(), m.end())

        for m in pat_after.finditer(content):
            if len(claims) >= int(max_claims):
                break
            num_raw = m.group(1) or ""
            matched_kw = keyword
            _add_claim(chunk, num_raw, matched_kw, m.start(), m.end())

    # De-dupe by (document_id, page_number, value)
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for c in claims:
        key = (c.get("document_id"), c.get("page_number"), c.get("value"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped
