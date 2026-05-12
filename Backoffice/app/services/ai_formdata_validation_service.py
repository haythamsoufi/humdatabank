from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.extensions import db
from app.models import (
    AIFormDataValidation,
    AssignedForm,
    AssignmentEntityStatus,
    DynamicIndicatorData,
    FormData,
    FormItem,
    IndicatorBank,
    PublicSubmission,
)
from app.services.ai_vector_store import AIVectorStore
from app.utils.datetime_helpers import utcnow

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


class AIFormDataValidationService:
    """
    Validate a single FormData record against documents in the AI Knowledge Base.

    Evidence is retrieved via the vector store (hybrid search).
    The LLM produces a JSON verdict + opinion, which is stored latest-only in AIFormDataValidation.
    """

    def __init__(self) -> None:
        self.vector_store = AIVectorStore()

    def _normalize_sources(self, sources: Any) -> Optional[Dict[str, bool]]:
        """
        Normalize user-provided sources selection.

        Supported inputs:
        - None: return None (keep legacy behavior)
        - ['historical','system_documents','upr_documents'] (list/tuple/set)
        - {'historical': True, 'system_documents': True, 'upr_documents': False} (dict-like)
        """
        if sources is None:
            return None
        allowed = {"historical", "system_documents", "upr_documents"}
        out: Dict[str, bool] = {"historical": False, "system_documents": False, "upr_documents": False}
        try:
            if isinstance(sources, dict):
                for k in allowed:
                    if k in sources:
                        out[k] = bool(sources.get(k))
            elif isinstance(sources, (list, tuple, set)):
                for v in sources:
                    s = str(v or "").strip()
                    if s in allowed:
                        out[s] = True
            else:
                # Unknown shape -> ignore (legacy)
                return None
        except Exception as e:
            logger.debug("_normalize_sources failed: %s", e)
            return None

        # Guardrail: if nothing selected, fall back to a sensible default (historical + system docs).
        if not any(out.values()):
            out["historical"] = True
            out["system_documents"] = True
            out["upr_documents"] = False
        return out

    def _empty_historical(self) -> Dict[str, Any]:
        return {"summary": {"count": 0}, "series": []}

    def _retrieve_upr_kpi_reference(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            if not _upr_kpi_applicable(label, keyword):
                return None
            if not context.get("country_id"):
                return None
            from app.services.data_retrieval_service import get_upr_kpi_value as get_upr_kpi_value_service

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
            out: Dict[str, Any] = {
                "metric": upr.get("metric") or metric,
                "value": str(val).strip(),
                "value_int": _parse_int_number(val),
                "source": upr.get("source") if isinstance(upr.get("source"), dict) else None,
                "notes": upr.get("notes"),
            }
            return out
        except Exception as e:
            logger.debug("_retrieve_upr_kpi_reference failed: %s", e)
            return None

    def upsert_validation(
        self,
        *,
        form_data_id: int,
        run_by_user_id: Optional[int],
        top_k: int = 12,
        sources: Any = None,
    ) -> Tuple[AIFormDataValidation, ValidationResult]:
        fd = FormData.query.get(int(form_data_id))
        if not fd:
            raise ValueError("FormData not found")

        context = self._build_context(fd)
        sources_cfg = self._normalize_sources(sources)

        # Log disaggregation/matrix data if present
        if context.get("disagg_values"):
            disagg_preview = context["disagg_values"]
            # Truncate for logging if too many entries
            if isinstance(disagg_preview, dict) and len(disagg_preview) > 5:
                preview_items = list(disagg_preview.items())[:5]
                logger.info(
                    "Matrix data resolved: %d values, sample=%s ...",
                    len(disagg_preview),
                    dict(preview_items),
                )
            else:
                logger.info("Matrix data resolved: %s", disagg_preview)

        # IFRC/UPR KPI reference (structured evidence) where applicable.
        upr_kpi = None
        if sources_cfg is None or sources_cfg.get("upr_documents", False):
            upr_kpi = self._retrieve_upr_kpi_reference(context) or None
        if upr_kpi:
            context = {**context, "upr_kpi": upr_kpi}

        evidence_chunks = self._retrieve_evidence(context, top_k=top_k, sources_cfg=sources_cfg)
        if sources_cfg is None or sources_cfg.get("historical", False):
            historical = self._retrieve_historical_values(context=context, exclude_form_data_id=int(fd.id), limit_periods=10)
        else:
            historical = self._empty_historical()

        # Log historical data retrieval results
        hist_summary = historical.get("summary", {})
        hist_series = historical.get("series", [])
        logger.info(
            "Historical data retrieval: count=%d periods=%s latest=%s value=%s",
            hist_summary.get("count", 0),
            [s.get("period_name") for s in hist_series],
            hist_summary.get("latest_period_name"),
            hist_summary.get("latest_value_int"),
        )

        # Pass both summary and series to the LLM so it can reason about historical trends
        hist_for_llm = historical.get("summary") or {}
        hist_series_for_llm = historical.get("series") or []
        if hist_series_for_llm:
            # Include a compact series representation (period_name + value) for the LLM
            hist_for_llm = {
                **hist_for_llm,
                "series": [
                    {"period": s.get("period_name"), "value": s.get("value_int")}
                    for s in hist_series_for_llm
                ],
            }

        provider, model, verdict_payload, raw_text, err = self._run_llm_validation(
            context={**context, "historical": hist_for_llm},
            evidence_chunks=evidence_chunks,
        )

        # Heuristic fallback: always produce an explanation and a quality estimate
        heuristic = self._heuristic_validate(context=context, evidence_chunks=evidence_chunks, historical=historical)

        verdict = None
        confidence = None
        opinion_text = None
        status = "completed"
        error_message = None

        llm_verdict = (verdict_payload.get("verdict") if isinstance(verdict_payload, dict) else None) if verdict_payload else None
        llm_opinion = (
            (verdict_payload.get("opinion_summary") if isinstance(verdict_payload, dict) else None)
            or (verdict_payload.get("opinion") if isinstance(verdict_payload, dict) else None)
        ) if verdict_payload else None
        llm_conf = (verdict_payload.get("confidence") if isinstance(verdict_payload, dict) else None) if verdict_payload else None

        # If provider failed OR returned empty/invalid payload, use heuristic results.
        llm_is_useful = bool(llm_verdict or llm_opinion or (raw_text and raw_text.strip()))
        if err or not llm_is_useful:
            verdict = heuristic.get("verdict") or "uncertain"
            confidence = heuristic.get("quality")  # use DB confidence field as quality estimate
            opinion_text = heuristic.get("opinion")
            error_message = err
            provider = "heuristic" if not provider else provider
            if provider != "heuristic" and err:
                # Prefer to clearly indicate fallback in provider name
                provider = "heuristic"
                model = None
        else:
            verdict = (str(llm_verdict).strip().lower() if llm_verdict else None) or (heuristic.get("verdict") or "uncertain")
            confidence = llm_conf
            try:
                if confidence is not None:
                    confidence = float(confidence)
            except Exception as e:
                logger.debug("confidence float failed: %s", e)
                confidence = None
            if confidence is None:
                confidence = heuristic.get("quality")
            opinion_text = (str(llm_opinion).strip() if llm_opinion else None) or (raw_text.strip() if raw_text else None)
            if not opinion_text:
                opinion_text = heuristic.get("opinion")
            else:
                # If the LLM didn't explain much, append a short heuristic summary.
                if len(opinion_text) < 40 and heuristic.get("opinion"):
                    opinion_text = (opinion_text + " " + heuristic.get("opinion")).strip()

            # Guardrail: avoid flagging discrepancies based on non-equivalent proxy evidence
            # (e.g., comparing "local units" to "branches/sub-branches") when historical and/or UPR KPI
            # strongly supports the reported value.
            try:
                keyword = _infer_primary_keyword(context.get("form_item_label")) or ""
                reported_int = _parse_int_number(context.get("value"))
                upr_val_int = None
                try:
                    if isinstance(context.get("upr_kpi"), dict):
                        upr_val_int = _parse_int_number((context.get("upr_kpi") or {}).get("value"))
                except Exception as e:
                    logger.debug("upr_val_int parse failed: %s", e)
                    upr_val_int = None

                hist_summary = (historical or {}).get("summary") if isinstance(historical, dict) else None
                hist_count = int(hist_summary.get("count") or 0) if isinstance(hist_summary, dict) else 0
                hist_min = hist_summary.get("min") if isinstance(hist_summary, dict) else None
                hist_max = hist_summary.get("max") if isinstance(hist_summary, dict) else None
                hist_strong_match = False
                try:
                    if reported_int is not None and hist_count >= 3 and hist_min is not None and hist_max is not None:
                        hist_strong_match = (int(hist_min) == int(hist_max) == int(reported_int))
                except Exception as e:
                    logger.debug("hist_strong_match failed: %s", e)
                    hist_strong_match = False

                # Time-alignment guardrail for UPR KPI:
                # Do not flag a discrepancy for a 2024 row solely based on a UPR KPI value coming from a different year.
                try:
                    upr_year = None
                    upr_rtype = None
                    upr_src = None
                    if isinstance(context.get("upr_kpi"), dict):
                        upr_src = (context.get("upr_kpi") or {}).get("source") if isinstance((context.get("upr_kpi") or {}).get("source"), dict) else None
                    if isinstance(upr_src, dict):
                        upr_year = upr_src.get("year")
                        upr_rtype = upr_src.get("report_type")
                    row_year = _safe_int(context.get("period_year"))
                    if str(verdict or "").strip().lower() == "discrepancy" and row_year and upr_year and int(upr_year) != int(row_year):
                        # If history strongly supports reported value, do not flag discrepancy.
                        if hist_strong_match:
                            verdict = "good"
                            confidence = max(float(confidence or 0.0), 0.70)
                            opinion_text = (
                                f"Decision: Accept the reported value. Historical submissions support {int(reported_int):,}. "
                                f"The IFRC Unified Plan KPI card reference is from a different period ({upr_rtype + ' ' if upr_rtype else ''}{int(upr_year)}), "
                                f"so it should not be treated as a direct conflict for {int(row_year)}."
                            )
                        else:
                            verdict = "uncertain"
                            confidence = min(float(confidence or 0.55), 0.55)
                            opinion_text = (
                                f"Decision: Needs review. The IFRC Unified Plan KPI card reference is from a different period "
                                f"({upr_rtype + ' ' if upr_rtype else ''}{int(upr_year)}), so it should not be treated as a direct conflict "
                                f"for {int(row_year)} without additional evidence. Please verify with same-year sources or historical submissions."
                            )
                except Exception as e:
                    logger.debug("Optional validation step failed: %s", e)

                def _mentions_local_units(txt: str) -> bool:
                    if not txt:
                        return False
                    return bool(re.search(r"\blocal\s+units?\b", txt, flags=re.IGNORECASE))

                llm_citations = (verdict_payload or {}).get("citations") if isinstance(verdict_payload, dict) else None
                cited_quotes = []
                if isinstance(llm_citations, list):
                    for c in llm_citations[:10]:
                        if isinstance(c, dict):
                            q = str(c.get("quote") or "").strip()
                            if q:
                                cited_quotes.append(q)
                has_direct_term = any(_mentions_local_units(q) for q in cited_quotes)
                if not has_direct_term:
                    # Fall back to chunk text if model didn't provide explicit citations.
                    for ch in (evidence_chunks or [])[:12]:
                        if isinstance(ch, dict) and _mentions_local_units(str(ch.get("content") or "")):
                            has_direct_term = True
                            break

                if str(verdict or "").strip().lower() == "discrepancy" and str(keyword).strip().lower() == "local units":
                    upr_supports = (reported_int is not None and upr_val_int is not None and int(upr_val_int) == int(reported_int))
                    if (upr_supports or hist_strong_match) and (not has_direct_term):
                        # Treat as definition/proxy mismatch. Do NOT flag discrepancy.
                        if upr_supports:
                            verdict = "good"
                            confidence = max(float(confidence or 0.0), 0.75)
                            opinion_text = (
                                f"Decision: Accept the reported value. The IFRC/UPR KPI reference and historical submissions "
                                f"support {int(reported_int):,}. The cited document excerpt refers to branches/sub-branches, "
                                f"which may not be equivalent to 'local units' without an explicit definition."
                            )
                        else:
                            verdict = "uncertain"
                            confidence = min(float(confidence or 0.55), 0.55)
                            opinion_text = (
                                "Decision: Needs review. Historical submissions support the reported value, but the cited "
                                "document excerpt appears to reference branches/sub-branches rather than 'local units'. "
                                "Please verify the indicator definition and consult additional sources."
                            )
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)

        # When the reported value is missing, we only suggest — do not show a "good" validation verdict.
        reported_value_raw = context.get("value")
        has_reported_value = not _is_blankish_value(reported_value_raw)
        if not has_reported_value:
            previous_verdict = verdict
            verdict = "uncertain"
            # Use suggestion-style confidence (e.g. 55%) so UI shows "uncertain" + suggestion, not "good (85%)"
            if confidence is None or (isinstance(confidence, (int, float)) and float(confidence) > 0.6):
                confidence = 0.55
            # When we override an LLM "good" verdict, clarify that this is a suggestion only
            if previous_verdict == "good" and opinion_text and opinion_text.strip():
                if not opinion_text.strip().lower().startswith("no reported value"):
                    opinion_text = f"No reported value; suggestion only: {opinion_text.strip()}"

        # Only compute a suggested value when the reported value is truly missing.
        # If data was marked as "not applicable" / "data not available", do not suggest.
        suggestion_obj = None
        is_missing_reported_value = (context.get("data_status") == "available") and (not has_reported_value)
        if is_missing_reported_value:
            suggestion_obj = self._compute_suggestion(
                context=context,
                evidence_chunks=evidence_chunks,
                historical=historical,
                llm_json=verdict_payload if isinstance(verdict_payload, dict) else None,
                heuristic=heuristic or {},
            )

        # If the suggestion is based on a structured UPR KPI card, make that explicit in the opinion text
        # to avoid confusion when the narrative evidence search didn't include the KPI card itself.
        try:
            if isinstance(suggestion_obj, dict) and suggestion_obj.get("source") == "upr":
                s_reason = (suggestion_obj.get("reason") or "").strip()
                if s_reason and (not (opinion_text or "").lower().strip().endswith(s_reason.lower())):
                    if opinion_text and opinion_text.strip():
                        if "structured kpi" not in opinion_text.lower():
                            opinion_text = (opinion_text.strip() + " " + s_reason).strip()
                    else:
                        opinion_text = s_reason
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # Build a short summary + an expandable detailed opinion (sources + decision basis).
        # Store the full verbose opinion in evidence, while keeping opinion_text short for UI tables.
        opinion_full_text = (opinion_text or "").strip() if opinion_text else ""

        evidence: Dict[str, Any] = {
            "context": context,
            "chunks": evidence_chunks,
            "llm_json": verdict_payload if isinstance(verdict_payload, dict) else None,
            "llm_raw": raw_text,
            "provider_error": err,
            "heuristic": heuristic,
            "historical": historical,
            "sources_config": sources_cfg,
        }
        if suggestion_obj:
            evidence["suggestion"] = suggestion_obj

        try:
            opinion_ui = self._build_opinion_ui(
                context=context,
                verdict=str(verdict or "uncertain"),
                confidence=confidence,
                opinion_full_text=opinion_full_text,
                evidence_chunks=evidence_chunks,
                historical=historical,
                llm_json=verdict_payload if isinstance(verdict_payload, dict) else None,
                heuristic=heuristic if isinstance(heuristic, dict) else {},
                suggestion=suggestion_obj if isinstance(suggestion_obj, dict) else None,
            )
            if isinstance(opinion_ui, dict) and opinion_ui:
                evidence["opinion_ui"] = opinion_ui
                # Keep full text for audit/debug (and so we don't lose prior behavior).
                if opinion_full_text:
                    evidence["opinion_full_text"] = opinion_full_text
                # Use summary for the primary `opinion_text` field shown in the grid.
                ui_summary = (opinion_ui.get("summary") or "").strip()
                if ui_summary:
                    opinion_text = ui_summary
        except Exception as e:
            logger.debug("UI formatting failed: %s", e)
            # Best-effort: never fail validation due to UI formatting.

        rec = AIFormDataValidation.query.filter_by(form_data_id=int(fd.id)).first()
        now = utcnow()
        if not rec:
            rec = AIFormDataValidation(
                form_data_id=int(fd.id),
                created_at=now,
            )
            db.session.add(rec)

        rec.status = status
        rec.verdict = str(verdict) if verdict is not None else None
        rec.confidence = confidence
        rec.opinion_text = (opinion_text or None)
        rec.evidence = evidence
        rec.provider = provider
        rec.model = model
        rec.run_by_user_id = run_by_user_id
        rec.updated_at = now

        db.session.commit()
        return rec, ValidationResult(
            status=status,
            verdict=rec.verdict,
            confidence=rec.confidence,
            opinion_text=rec.opinion_text,
            evidence=evidence,
            provider=provider,
            model=model,
            error_message=error_message,
        )

    def validate_missing_assigned_item(
        self,
        *,
        assignment_entity_status_id: int,
        form_item_id: int,
        run_by_user_id: Optional[int],
        top_k: int = 12,
        sources: Any = None,
    ) -> ValidationResult:
        """
        Produce an AI suggestion/opinion for a non-reported item WITHOUT creating FormData rows.

        This supports "virtual missing rows" (e.g. id like 'm:<aes_id>:<form_item_id>') in Explore Data.
        The result is not persisted to AIFormDataValidation because there is no FormData primary key.
        """
        aes = AssignmentEntityStatus.query.get(int(assignment_entity_status_id))
        if not aes:
            raise ValueError("AssignmentEntityStatus not found")
        item = FormItem.query.get(int(form_item_id))
        if not item:
            raise ValueError("FormItem not found")

        # Build a transient FormData-like object for context generation.
        fd = FormData(
            assignment_entity_status_id=int(assignment_entity_status_id),
            form_item_id=int(form_item_id),
            value=None,
        )
        # Explicitly treat as "available but missing value".
        fd.data_not_available = False
        fd.not_applicable = False
        fd.assignment_entity_status = aes
        fd.form_item = item

        context = self._build_context(fd)
        sources_cfg = self._normalize_sources(sources)
        upr_kpi = None
        if sources_cfg is None or sources_cfg.get("upr_documents", False):
            upr_kpi = self._retrieve_upr_kpi_reference(context) or None
        if upr_kpi:
            context = {**context, "upr_kpi": upr_kpi}
        evidence_chunks = self._retrieve_evidence(context, top_k=top_k, sources_cfg=sources_cfg)
        if sources_cfg is None or sources_cfg.get("historical", False):
            historical = self._retrieve_historical_values(context=context, exclude_form_data_id=None, limit_periods=10)
        else:
            historical = self._empty_historical()

        # Pass both summary and series to the LLM so it can reason about historical trends
        hist_for_llm = historical.get("summary") or {}
        hist_series_for_llm = historical.get("series") or []
        if hist_series_for_llm:
            hist_for_llm = {
                **hist_for_llm,
                "series": [
                    {"period": s.get("period_name"), "value": s.get("value_int")}
                    for s in hist_series_for_llm
                ],
            }

        provider, model, verdict_payload, raw_text, err = self._run_llm_validation(
            context={**context, "historical": hist_for_llm},
            evidence_chunks=evidence_chunks,
        )

        heuristic = self._heuristic_validate(context=context, evidence_chunks=evidence_chunks, historical=historical)

        llm_verdict = (verdict_payload.get("verdict") if isinstance(verdict_payload, dict) else None) if verdict_payload else None
        llm_opinion = (
            (verdict_payload.get("opinion_summary") if isinstance(verdict_payload, dict) else None)
            or (verdict_payload.get("opinion") if isinstance(verdict_payload, dict) else None)
        ) if verdict_payload else None
        llm_conf = (verdict_payload.get("confidence") if isinstance(verdict_payload, dict) else None) if verdict_payload else None

        # Use heuristic when provider fails
        llm_is_useful = bool(llm_verdict or llm_opinion or (raw_text and raw_text.strip()))
        if err or not llm_is_useful:
            verdict = heuristic.get("verdict") or "uncertain"
            confidence = heuristic.get("quality")
            opinion_text = heuristic.get("opinion")
            provider = "heuristic"
            model = None
        else:
            verdict = (str(llm_verdict).strip().lower() if llm_verdict else None) or (heuristic.get("verdict") or "uncertain")
            confidence = llm_conf
            try:
                if confidence is not None:
                    confidence = float(confidence)
            except Exception as e:
                logger.debug("confidence float failed: %s", e)
                confidence = None
            if confidence is None:
                confidence = heuristic.get("quality")
            opinion_text = (str(llm_opinion).strip() if llm_opinion else None) or (raw_text.strip() if raw_text else None)
            if not opinion_text:
                opinion_text = heuristic.get("opinion")

        # Missing rows are suggestion-only by definition.
        verdict = "uncertain"
        if confidence is None or (isinstance(confidence, (int, float)) and float(confidence) > 0.6):
            confidence = 0.55
        if opinion_text and opinion_text.strip() and not opinion_text.strip().lower().startswith("no reported value"):
            opinion_text = f"No reported value; suggestion only: {opinion_text.strip()}"

        suggestion_obj = self._compute_suggestion(
            context=context,
            evidence_chunks=evidence_chunks,
            historical=historical,
            llm_json=verdict_payload if isinstance(verdict_payload, dict) else None,
            heuristic=heuristic or {},
        )

        # Build evidence payload similar to upsert_validation (for UI rendering)
        evidence: Dict[str, Any] = {
            "context": context,
            "chunks": evidence_chunks,
            "llm_json": verdict_payload if isinstance(verdict_payload, dict) else None,
            "llm_raw": raw_text,
            "provider_error": err,
            "heuristic": heuristic,
            "historical": historical,
            "sources_config": sources_cfg,
        }
        if suggestion_obj:
            evidence["suggestion"] = suggestion_obj

        # opinion_ui helps the frontend render sources/basis consistently.
        try:
            opinion_ui = self._build_opinion_ui(
                context=context,
                verdict=str(verdict or "uncertain"),
                confidence=confidence,
                opinion_full_text=(opinion_text or "").strip(),
                evidence_chunks=evidence_chunks,
                historical=historical,
                llm_json=verdict_payload if isinstance(verdict_payload, dict) else None,
                heuristic=heuristic if isinstance(heuristic, dict) else {},
                suggestion=suggestion_obj if isinstance(suggestion_obj, dict) else None,
            )
            if isinstance(opinion_ui, dict) and opinion_ui:
                evidence["opinion_ui"] = opinion_ui
                ui_summary = (opinion_ui.get("summary") or "").strip()
                if ui_summary:
                    opinion_text = ui_summary
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        return ValidationResult(
            status="completed",
            verdict=str(verdict),
            confidence=confidence,
            opinion_text=opinion_text,
            evidence=evidence,
            provider=provider,
            model=model,
            error_message=err,
        )

    def upsert_missing_assigned_validation(
        self,
        *,
        assignment_entity_status_id: int,
        form_item_id: int,
        run_by_user_id: Optional[int],
        top_k: int = 12,
        sources: Any = None,
    ) -> Tuple[AIFormDataValidation, ValidationResult]:
        """
        Persist an AI opinion for a virtual missing row, keyed by (assignment_entity_status_id, form_item_id).

        Does NOT create FormData rows.
        """
        vr = self.validate_missing_assigned_item(
            assignment_entity_status_id=int(assignment_entity_status_id),
            form_item_id=int(form_item_id),
            run_by_user_id=run_by_user_id,
            top_k=top_k,
            sources=sources,
        )

        rec = (
            AIFormDataValidation.query
            .filter(AIFormDataValidation.form_data_id.is_(None))
            .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status_id))
            .filter(AIFormDataValidation.form_item_id == int(form_item_id))
            .first()
        )
        now = utcnow()
        if not rec:
            rec = AIFormDataValidation(
                form_data_id=None,
                assignment_entity_status_id=int(assignment_entity_status_id),
                form_item_id=int(form_item_id),
                created_at=now,
            )
            db.session.add(rec)

        rec.status = getattr(vr, "status", None) or "completed"
        rec.verdict = getattr(vr, "verdict", None)
        rec.confidence = getattr(vr, "confidence", None)
        rec.opinion_text = getattr(vr, "opinion_text", None)
        rec.evidence = getattr(vr, "evidence", None)
        rec.provider = getattr(vr, "provider", None)
        rec.model = getattr(vr, "model", None)
        rec.run_by_user_id = run_by_user_id
        rec.updated_at = now

        db.session.commit()
        return rec, vr

    def _build_opinion_ui(
        self,
        *,
        context: Dict[str, Any],
        verdict: str,
        confidence: Optional[float],
        opinion_full_text: str,
        evidence_chunks: List[Dict[str, Any]],
        historical: Optional[Dict[str, Any]],
        llm_json: Optional[Dict[str, Any]],
        heuristic: Dict[str, Any],
        suggestion: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build a UI-friendly opinion payload:
          - short summary (1–2 sentences)
          - detailed expandable text with explicit sources + decision basis
          - sources list (document title/page/quote)
        """
        def _safe_str(v: Any) -> str:
            try:
                s = str(v).strip()
            except Exception as e:
                logger.debug("_safe_str failed: %s", e)
                return ""
            # Treat common null-ish strings as empty (some providers return "None"/"null").
            if s.lower() in ("none", "null", "undefined"):
                return ""
            return s

        def _truncate(s: str, n: int) -> str:
            s = (s or "").strip()
            if len(s) <= n:
                return s
            return (s[: max(0, n - 1)].rstrip() + "…").strip()

        def _summarize(text: str) -> str:
            t = _safe_str(text).replace("\r", " ").replace("\n", " ").strip()
            if not t:
                return ""
            # Prefer first 1–2 sentences; fall back to truncation.
            parts = re.split(r"(?<=[\.\!\?])\s+", t)
            s1 = parts[0].strip() if parts else t
            s2 = (s1 + " " + parts[1].strip()).strip() if len(parts) > 1 and len(s1) < 120 else s1
            return _truncate(s2, 260)

        def _title_case_report_type(v: str) -> str:
            s = (v or "").strip()
            if not s:
                return ""
            s = s.replace("_", " ").replace("-", " ").strip()
            # Common IFRC API tokens
            mapping = {
                "midyear report": "Mid-year Report",
                "mid year report": "Mid-year Report",
                "annual report": "Annual Report",
                "unified plan": "Unified Plan",
            }
            key = re.sub(r"\s+", " ", s.lower()).strip()
            if key in mapping:
                return mapping[key]
            # Fallback: capitalize words conservatively
            return " ".join(w.capitalize() if w.isalpha() else w for w in re.split(r"\s+", s))

        def _format_ifrc_upr_extraction(extraction: str) -> str:
            """
            Turn internal extraction tokens like:
              'ype=midyear_report; year=2024 - National Society local units: 94 - ...'
            into a user-friendly one-liner.
            """
            s = _safe_str(extraction)
            if not s:
                return ""
            # Normalize separators
            s2 = s.replace("\r", " ").replace("\n", " ").strip()
            # Extract key=value metadata prefix (ype/pe/year) if present
            meta = {}
            try:
                # Split on '-' once; left side usually contains "ype=...; year=..."
                left, _, right = s2.partition("-")
                # Parse key/value pairs in the left part
                for part in re.split(r"[;,\|]\s*", left):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        meta[k.strip().lower()] = v.strip()
                # If no meta keys found, keep original
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
                    # Clean up " - " list into semicolons for readability
                    right_clean = right.strip()
                    right_clean = re.sub(r"\s*-\s*", "; ", right_clean)
                    return (f"{prefix} — {right_clean}" if prefix else right_clean).strip()
                return prefix or s2
            except Exception as e:
                logger.debug("prefix merge failed: %s", e)
                return s2

        def _extract_ifrc_meta(text: str) -> Dict[str, Any]:
            """
            Parse IFRC API extraction prefixes like:
              'pe=midyear_report; year=2024 - ...'
              'ype=annual_report; year=2024 - ...'
            Returns: { report_type: 'Mid-year report'|'Annual report'|..., year: 2024|None }
            """
            out: Dict[str, Any] = {"report_type": None, "year": None}
            s = _safe_str(text)
            if not s:
                return out
            if ("pe=" not in s.lower()) and ("ype=" not in s.lower()) and ("year=" not in s.lower()):
                return out
            try:
                left, _, _right = s.replace("\r", " ").replace("\n", " ").partition("-")
                meta = {}
                for part in re.split(r"[;,\|]\s*", left):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        meta[k.strip().lower()] = v.strip()
                rtype = meta.get("ype") or meta.get("pe") or meta.get("type")
                year = meta.get("year")
                if rtype:
                    out["report_type"] = _title_case_report_type(str(rtype))
                if year and str(year).strip().isdigit():
                    out["year"] = int(str(year).strip())
            except Exception as e:
                logger.debug("year parse failed: %s", e)
                return out
            return out

        def _pretty_source_type(v: str) -> str:
            s = (v or "").strip().lower()
            if not s:
                return ""
            if s in ("api", "ifrc api"):
                return "IFRC API"
            if s in ("system", "system upload", "system document"):
                return "System upload"
            if s in ("local", "local upload"):
                return "Local upload"
            return v

        verdict_norm = _safe_str(verdict).lower() or "uncertain"
        conf_norm = None
        try:
            conf_norm = float(confidence) if confidence is not None else None
        except Exception as e:
            logger.debug("conf_norm float failed: %s", e)
            conf_norm = None

        reported_raw = context.get("value")
        has_reported_value = not _is_blankish_value(reported_raw)

        # Decision (explicit, UI-friendly)
        if not has_reported_value and suggestion:
            decision = "suggest_value"
        elif not has_reported_value:
            decision = "needs_review"
        elif verdict_norm == "good":
            decision = "accept_reported_value"
        elif verdict_norm == "discrepancy":
            decision = "flag_discrepancy"
        else:
            decision = "needs_review"

        decision_label = {
            "accept_reported_value": "Accept the reported value",
            "flag_discrepancy": "Flag as discrepancy",
            "needs_review": "Needs review",
            "suggest_value": "No reported value — suggestion only",
        }.get(decision, decision)

        # Build source index from evidence chunks
        doc_title_by_id: Dict[Any, str] = {}
        doc_type_by_id: Dict[Any, str] = {}
        chunk_by_id: Dict[Any, Dict[str, Any]] = {}
        for ch in evidence_chunks or []:
            try:
                did = ch.get("document_id")
                if did is not None and did not in doc_title_by_id:
                    doc_title_by_id[did] = _safe_str(ch.get("document_title")) or _safe_str(ch.get("document_filename")) or f"Document {did}"
                    doc_type_by_id[did] = _safe_str(ch.get("document_type")) or ""
                cid = ch.get("chunk_id")
                if cid is not None and cid not in chunk_by_id:
                    chunk_by_id[cid] = ch
            except Exception as e:
                logger.debug("chunk_by_id build failed: %s", e)
                continue

        # Collect citations: ONLY from LLM citations and UPR. Do NOT fall back to heuristic claims.
        # Heuristic claims can match loosely (e.g. keyword "volunteers" in unrelated docs) and would
        # incorrectly surface irrelevant documents as "sources" when the LLM correctly found none usable.
        sources: List[Dict[str, Any]] = []
        raw_citations = None
        try:
            raw_citations = (llm_json or {}).get("citations") if isinstance(llm_json, dict) else None
        except Exception as e:
            logger.debug("raw_citations get failed: %s", e)
            raw_citations = None
        if isinstance(raw_citations, list) and raw_citations:
            for c in raw_citations[:8]:
                if not isinstance(c, dict):
                    continue
                did = c.get("document_id")
                pn = c.get("page_number")
                cid = c.get("chunk_id")
                quote = _safe_str(c.get("quote"))
                ch = chunk_by_id.get(cid) if cid is not None else None
                title = doc_title_by_id.get(did) or (_safe_str(ch.get("document_title")) if isinstance(ch, dict) else "") or (f"Document {did}" if did is not None else "Document")
                doc_type = (doc_type_by_id.get(did) or _safe_str(ch.get("document_type")) if isinstance(ch, dict) else "")
                section = _safe_str(ch.get("section_title")) if isinstance(ch, dict) else ""
                source_type = _safe_str(ch.get("source")) if isinstance(ch, dict) else ""
                sources.append(
                    {
                        "document_id": did,
                        "document_title": title,
                        "document_type": (doc_type or None),
                        "document_url": (f"/api/ai/documents/{int(did)}/download" if did is not None and str(did).strip().isdigit() else None),
                        "page_number": pn,
                        "chunk_id": cid,
                        "section_title": section or None,
                        "source_type": (source_type or None),
                        "quote": _truncate(quote, 320) if quote else None,
                    }
                )

        # Also include the structured IFRC/UPR KPI reference as a source when it was actually used.
        try:
            upr = context.get("upr_kpi")
            if isinstance(upr, dict) and upr.get("source") and upr.get("value") is not None:
                src = upr.get("source") if isinstance(upr.get("source"), dict) else {}
                did = src.get("document_id")
                pn = src.get("page_number")
                cid = src.get("chunk_id")
                title = _safe_str(src.get("document_title") or src.get("document_filename")) or (f"Document {did}" if did is not None else "IFRC Unified Plan")
                extraction = _safe_str(src.get("extraction"))
                metric = _safe_str(upr.get("metric"))
                val = _safe_str(upr.get("value"))
                quote = _format_ifrc_upr_extraction(extraction) or (f"IFRC Unified Plan KPI card reports {metric} = {val}" if metric and val else None)
                # De-dupe against existing sources by (document_id, page_number, chunk_id)
                key = (did, pn, cid)
                existing_keys = {(s.get("document_id"), s.get("page_number"), s.get("chunk_id")) for s in (sources or [])}
                if key not in existing_keys:
                    sources.insert(
                        0,
                        {
                            "document_id": did,
                            "document_title": title,
                            "document_type": "Unified Plan",
                            "document_url": _safe_str(src.get("document_url")) or (f"/api/ai/documents/{int(did)}/download" if did is not None and str(did).strip().isdigit() else None),
                            "page_number": pn,
                            "chunk_id": cid,
                            "section_title": None,
                            "source_type": "IFRC API",
                            "quote": _truncate(str(quote), 320) if quote else None,
                        },
                    )
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # IMPORTANT: "Sources" in the UI should reflect *used* evidence, not "documents we happened to retrieve".
        # Previously we force-added an arbitrary system-uploaded chunk when the LLM only cited UPL/API sources,
        # which could surface irrelevant quotes (e.g. Annual Report pages unrelated to the metric).
        #
        # If you still want to enforce visibility of system uploads, opt-in via config AND only add a system chunk
        # that looks relevant to the current form item.
        try:
            force_system_source = bool(current_app.config.get("AI_VALIDATION_FORCE_SYSTEM_SOURCE", False))
            if force_system_source:
                have_system = any(
                    _safe_str(s.get("source_type")).lower() in ("system upload", "system")
                    for s in sources
                    if isinstance(s, dict)
                )
                if not have_system:
                    item_label = _safe_str(context.get("form_item_label"))
                    keyword = _infer_primary_keyword(item_label) or ""
                    required_terms = _required_terms_for_claims(item_label, keyword)
                    period_year = _parse_year_from_period(context.get("period_name") or context.get("period_year"))

                    def _chunk_looks_relevant(ch: Dict[str, Any]) -> bool:
                        try:
                            content = _safe_str(ch.get("content")).lower()
                        except Exception as e:
                            logger.debug("content check failed: %s", e)
                            return False
                        if not content:
                            return False
                        if keyword:
                            k = keyword.lower().strip()
                            # Handle singular/plural variants for common keywords.
                            if k == "local units":
                                if ("local unit" not in content) and ("local units" not in content):
                                    return False
                            elif k not in content:
                                return False
                        if required_terms and not any(t in content for t in required_terms):
                            return False
                        # If the chunk clearly references a different year, don't surface it as a "source".
                        if period_year:
                            years = _YEAR_RE.findall(content)
                            try:
                                years_int = {int(y) for y in years if y and str(y).isdigit()}
                            except Exception as e:
                                logger.debug("years_int parse failed: %s", e)
                                years_int = set()
                            if years_int and (period_year not in years_int):
                                return False
                        return True

                    sys_chunk = None
                    for ch in evidence_chunks or []:
                        if not isinstance(ch, dict):
                            continue
                        if not (bool(ch.get("is_system_document")) or _safe_str(ch.get("source")).lower() == "system"):
                            continue
                        if _chunk_looks_relevant(ch):
                            sys_chunk = ch
                            break

                    if sys_chunk and isinstance(sys_chunk, dict):
                        did = sys_chunk.get("document_id")
                        title = _safe_str(sys_chunk.get("document_title") or sys_chunk.get("document_filename")) or (
                            f"Document {did}" if did is not None else "System document"
                        )
                        pn = sys_chunk.get("page_number")
                        cid = sys_chunk.get("chunk_id")
                        quote = re.sub(r"\s+", " ", _safe_str(sys_chunk.get("content"))).strip()
                        # Insert at the front so it doesn't get dropped by sources[:8].
                        sources.insert(
                            0,
                            {
                                "document_id": did,
                                "document_title": title,
                                "document_type": _safe_str(sys_chunk.get("document_type")) or None,
                                "document_url": (
                                    f"/api/ai/documents/{int(did)}/download"
                                    if did is not None and str(did).strip().isdigit()
                                    else None
                                ),
                                "page_number": pn,
                                "chunk_id": cid,
                                "section_title": _safe_str(sys_chunk.get("section_title")) or None,
                                "source_type": "System upload",
                                "quote": _truncate(quote, 320) if quote else None,
                            },
                        )
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # Post-process sources for user-friendliness:
        # - remove pe=/ype= tokens from quotes
        # - show report type (Mid-year Report / Annual Report) in the document title when available
        # - normalize source_type labels
        try:
            # First, infer report types per document_id (so all entries for the same doc share the same label).
            doc_report_type: Dict[Any, str] = {}
            # Seed from structured UPR KPI reference if available (even when the LLM citations omit pe=/ype= tokens).
            try:
                upr_seed = context.get("upr_kpi")
                if isinstance(upr_seed, dict) and isinstance(upr_seed.get("source"), dict):
                    src = upr_seed.get("source") or {}
                    did_seed = src.get("document_id")
                    if did_seed is not None:
                        rt_seed = (src.get("report_type") or "").strip()
                        if rt_seed:
                            doc_report_type[did_seed] = rt_seed
                        else:
                            ext = _safe_str(src.get("extraction"))
                            meta = _extract_ifrc_meta(ext)
                            rt2 = (meta.get("report_type") or "").strip() if isinstance(meta, dict) else ""
                            if rt2:
                                doc_report_type[did_seed] = rt2
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)
            for s in sources or []:
                if not isinstance(s, dict):
                    continue
                did = s.get("document_id")
                if did is None or did in doc_report_type:
                    continue
                raw_q = _safe_str(s.get("quote"))
                meta = _extract_ifrc_meta(raw_q)
                rt = (meta.get("report_type") or "").strip() if isinstance(meta, dict) else ""
                if rt:
                    doc_report_type[did] = rt

            enhanced: List[Dict[str, Any]] = []
            for s in sources or []:
                if not isinstance(s, dict):
                    continue
                title = _safe_str(s.get("document_title"))
                quote_raw = _safe_str(s.get("quote"))
                # Try to infer report type from this quote, otherwise use doc-level inferred type.
                meta = _extract_ifrc_meta(quote_raw)
                rt = ""
                try:
                    rt = (meta.get("report_type") or "").strip() if isinstance(meta, dict) else ""
                except Exception as e:
                    logger.debug("report_type get failed: %s", e)
                    rt = ""
                if not rt:
                    try:
                        rt = (doc_report_type.get(s.get("document_id")) or "").strip()
                    except Exception as e:
                        logger.debug("doc_report_type get failed: %s", e)
                        rt = ""

                # Rewrite the title into the more explicit type-specific name.
                # Examples:
                #   "Syria 2025 Unified Plan (UPL-2025-...)" + Mid-year Report
                #     -> "Syria 2025 Mid-year Report (UPL-2025-...)"
                #   "UPL_SYRIA_2023 (UPL-2023-...)" + Annual Report
                #     -> "UPL_SYRIA_2023 Annual Report (UPL-2023-...)"
                if rt:
                    try:
                        # Extract the UPL code in parentheses if present
                        m = re.search(r"\((UPL-[A-Za-z0-9\-]+)\)", title)
                        upl_code = m.group(1).strip() if m else ""
                        base = title
                        if upl_code:
                            base = re.sub(r"\s*\(" + re.escape(upl_code) + r"\)\s*", " ", base).strip()
                        base_norm = base.lower()
                        rt_norm = rt.strip()
                        if "unified plan" in base_norm:
                            base = re.sub(r"(?i)\bunified\s+plan\b", rt_norm, base).strip()
                        else:
                            # Avoid duplicates
                            if rt_norm.lower() not in base_norm:
                                base = (base + " " + rt_norm).strip()
                        title = (f"{base} ({upl_code})".strip() if upl_code else base).strip()
                    except Exception as e:
                        logger.debug("title build failed: %s", e)
                        # fallback: do not block rendering

                quote = quote_raw
                if quote and (("pe=" in quote.lower()) or ("ype=" in quote.lower())):
                    quote = _format_ifrc_upr_extraction(quote)
                # If the title already carries the report type/year (e.g. "Syria 2024 Mid-year Report ..."),
                # avoid repeating that prefix inside the quote.
                try:
                    if quote:
                        quote = re.sub(
                            r"^(Mid-year Report|Annual Report)\s+—\s+(19\d{2}|20\d{2})\s+—\s+",
                            "",
                            quote.strip(),
                            flags=re.IGNORECASE,
                        ).strip()
                except Exception as e:
                    logger.debug("Optional validation step failed: %s", e)
                st = _pretty_source_type(_safe_str(s.get("source_type") or ""))
                s2 = {**s}
                if title:
                    s2["document_title"] = title
                if quote:
                    s2["quote"] = _truncate(quote, 320)
                if st:
                    s2["source_type"] = st
                enhanced.append(s2)
            sources = enhanced
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # Basis (what the decision is based on)
        basis_codes: List[str] = []
        try:
            hist_summary = (historical or {}).get("summary") if isinstance(historical, dict) else None
            if isinstance(hist_summary, dict) and (hist_summary.get("count") or 0) > 0:
                basis_codes.append("historical")
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)
        if sources:
            basis_codes.append("documents")
        try:
            if suggestion and (suggestion.get("source") == "upr" or suggestion.get("upr_source")):
                basis_codes.append("upr_kpi_card")
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)
        try:
            upr = context.get("upr_kpi")
            if isinstance(upr, dict) and upr.get("value") is not None and str(upr.get("value")).strip() != "":
                basis_codes.append("upr_kpi_card")
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)
        # de-dupe preserve order
        basis_codes = list(dict.fromkeys([b for b in basis_codes if b]))

        basis_display_map = {
            "documents": "Documents",
            "historical": "Databank history",
            "upr_kpi_card": "IFRC Unified Plan KPI card",
        }
        basis = [basis_display_map.get(b, b) for b in basis_codes]

        def _extract_keyword_ints_from_sources(*, keyword: str, srcs: List[Dict[str, Any]]) -> List[int]:
            """
            Pull numeric values for a keyword from UI sources (best-effort).
            Example match: "National Society local units: 94"
            """
            kw = (keyword or "").strip().lower()
            if not kw:
                return []
            # Build regex for common keywords.
            if kw == "local units":
                kw_re = r"local\s+units?"
            elif kw == "branches":
                kw_re = r"branches?"
            elif kw == "staff":
                kw_re = r"staff"
            elif kw == "volunteers":
                kw_re = r"volunteers?"
            else:
                kw_re = re.escape(kw)

            out: List[int] = []
            rx = re.compile(rf"\b{kw_re}\b\s*[:=]\s*([0-9][0-9,\.\u00A0\u202F ]*)", flags=re.IGNORECASE)
            for s in (srcs or [])[:12]:
                try:
                    q = _safe_str(s.get("quote"))
                    if not q:
                        continue
                    m = rx.search(q)
                    if not m:
                        continue
                    val_raw = (m.group(1) or "").strip()
                    vi = _parse_int_number(val_raw)
                    if vi is None:
                        continue
                    out.append(int(vi))
                except Exception as e:
                    logger.debug("vi append failed: %s", e)
                    continue
            # de-dupe preserve order
            return list(dict.fromkeys(out))

        def _source_titles_hint(srcs: List[Dict[str, Any]]) -> str:
            try:
                titles = []
                for s in (srcs or [])[:2]:
                    t = _safe_str(s.get("document_title"))
                    if t:
                        titles.append(t)
                if not titles:
                    return ""
                if len(titles) == 1:
                    return f" Source: {titles[0]}."
                return f" Sources: {titles[0]}; {titles[1]}."
            except Exception as e:
                logger.debug("_citation_summary failed: %s", e)
                return ""

        # Summary (brief)
        llm_sum = ""
        try:
            llm_sum = _safe_str((llm_json or {}).get("opinion_summary") if isinstance(llm_json, dict) else "")
        except Exception as e:
            logger.debug("llm_sum get failed: %s", e)
            llm_sum = ""
        summary = _summarize(llm_sum or opinion_full_text)

        # If the summary is low-signal (common heuristic phrasing), generate a more useful one.
        try:
            low_signal = False
            if summary:
                s_norm = summary.strip().lower()
                low_signal = (
                    s_norm.startswith("quality estimate:")
                    or s_norm.startswith("quality estimate")
                    or s_norm.startswith("current period reports")
                    or (len(s_norm) < 40 and ("reports" in s_norm))
                )
            if low_signal or (not summary):
                keyword = _infer_primary_keyword(context.get("form_item_label")) or ""
                reported_int = _parse_int_number(reported_raw) if has_reported_value else None
                kw_vals = _extract_keyword_ints_from_sources(keyword=keyword, srcs=sources or [])
                hint = _source_titles_hint(sources or [])

                if decision == "flag_discrepancy" and reported_int is not None and kw_vals:
                    # Prefer an explicitly conflicting value when possible
                    conflict = next((v for v in kw_vals if int(v) != int(reported_int)), None)
                    if conflict is not None:
                        # Badge already shows "Discrepancy (..%)" so don't repeat "Flag as discrepancy" here.
                        summary = f"Reported {int(reported_int):,} vs {keyword or 'source evidence'} {int(conflict):,}.{hint}".strip()
                    else:
                        summary = f"Reported {int(reported_int):,} differs from some evidence; please review.{hint}".strip()
                elif decision == "accept_reported_value" and reported_int is not None:
                    if kw_vals and any(int(v) == int(reported_int) for v in kw_vals):
                        summary = f"Reported {int(reported_int):,} matches evidence.{hint}".strip()
                    else:
                        summary = f"Reported {int(reported_int):,} is supported by the available evidence.{hint}".strip()
                elif decision == "needs_review" and reported_int is not None:
                    if kw_vals:
                        summary = f"Reported {int(reported_int):,}; evidence contains {', '.join(f'{int(v):,}' for v in kw_vals[:2])} for {keyword or 'this metric'}. Please verify definition.{hint}".strip()
                    else:
                        summary = f"Reported {int(reported_int):,}; insufficient aligned evidence to confirm.{hint}".strip()
                elif decision == "suggest_value" and suggestion and suggestion.get("value") is not None:
                    try:
                        sv = suggestion.get("value")
                        summary = f"Suggested value {sv}.{hint}".strip()
                    except Exception as e:
                        logger.debug("summary build failed: %s", e)
                        summary = f"{decision_label}.{hint}".strip()
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        if not summary:
            # Final fallback: an explicit decision line
            if decision == "accept_reported_value":
                summary = "Decision: Accept the reported value."
            elif decision == "flag_discrepancy":
                summary = "Decision: Flag as discrepancy; please review."
            elif decision == "suggest_value":
                summary = "Decision: No reported value; see suggested value and sources."
            else:
                summary = "Decision: Needs review; insufficient evidence to confirm."

        # Detailed text (expandable)
        details_lines: List[str] = []
        details_lines.append(f"Decision: {decision_label}.")

        # Context line (helps the user understand what was validated)
        try:
            country = _safe_str(context.get("country_name"))
            period = _safe_str(context.get("period_name"))
            label = _safe_str(context.get("form_item_label"))
            rv = _safe_str(reported_raw) if has_reported_value else "(missing)"
            ctx_bits = [b for b in [country, period, label] if b]
            if ctx_bits:
                details_lines.append(f"Item: {' / '.join(ctx_bits)}. Reported: {rv}.")
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        if conf_norm is not None:
            details_lines.append(f"Confidence: {int(round(conf_norm * 100))}%.")

        if basis:
            details_lines.append("Based on: " + ", ".join(basis) + ".")

        # Historical detail
        try:
            hist_summary = (historical or {}).get("summary") if isinstance(historical, dict) else None
            if isinstance(hist_summary, dict) and (hist_summary.get("count") or 0) > 0:
                latest_p = hist_summary.get("latest_period_name")
                latest_v = hist_summary.get("latest_value_int")
                hmin = hist_summary.get("min")
                hmax = hist_summary.get("max")
                hmed = hist_summary.get("median")
                hline = "Historical: "
                parts = []
                if latest_p and latest_v is not None:
                    parts.append(f"most recent prior period {latest_p} = {int(latest_v):,}")
                if hmin is not None and hmax is not None:
                    if hmin == hmax:
                        parts.append(f"all prior values = {int(hmin):,}")
                    else:
                        parts.append(f"range {int(hmin):,}–{int(hmax):,}")
                if hmed is not None:
                    parts.append(f"median {int(hmed):,}")
                if parts:
                    st = hist_summary.get("statuses") if isinstance(hist_summary.get("statuses"), list) else None
                    st_txt = f" (statuses: {', '.join([str(x) for x in st[:4] if x])})" if st else ""
                    details_lines.append(hline + "; ".join(parts) + f".{st_txt}")
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # Document sources are returned as structured `sources` so the UI can render hyperlinks.
        # Keep the text details focused on rationale to avoid duplicating the source list in the UI.

        # If the LLM produced additional details, append them (kept concise).
        try:
            llm_details = _safe_str((llm_json or {}).get("opinion_details") if isinstance(llm_json, dict) else "")
            llm_details = llm_details.strip()
            if llm_details:
                details_lines.append("")
                details_lines.append("LLM notes:")
                details_lines.append(_truncate(llm_details, 1200))
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        details = "\n".join([ln for ln in details_lines if ln is not None and str(ln).strip() != ""]).strip()

        return {
            "summary": summary,
            "details": details,
            # Use display strings for UI, keep codes available for integrations/debugging.
            "decision": decision_label,
            "decision_code": decision,
            "basis": basis,
            "basis_codes": basis_codes,
            "sources": sources[:8],
        }

    def _resolve_disagg_labels(
        self,
        disagg_data: Any,
        form_item: Optional[FormItem],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve matrix/disaggregation data keys to human-readable labels.

        For matrix data like {"IFRC Secretariat_SP1": 500000, "IFRC Secretariat_SP2": 2000000},
        resolve the column codes (SP1, SP2) to their labels (e.g., "Longer term programmes",
        "Climate & environment") from the form_item's matrix_config.

        Returns a dict with resolved labels as keys and values, suitable for LLM context.
        """
        if not isinstance(disagg_data, dict) or not disagg_data:
            return None

        # Get matrix column definitions from form_item config
        column_labels: Dict[str, str] = {}
        if form_item and isinstance(form_item.config, dict):
            matrix_config = form_item.config.get("matrix_config", {})
            if isinstance(matrix_config, dict):
                columns = matrix_config.get("columns", [])
                if isinstance(columns, list):
                    for col in columns:
                        if isinstance(col, dict):
                            col_id = col.get("id") or col.get("name")
                            col_name = col.get("name") or col.get("label") or col_id
                            # Also check name_translations for English
                            name_trans = col.get("name_translations", {})
                            if isinstance(name_trans, dict) and name_trans.get("en"):
                                col_name = name_trans["en"]
                            if col_id:
                                column_labels[str(col_id)] = str(col_name)

        # Handle nested format: {"values": {...}, "mode": "..."}
        data_to_resolve = disagg_data
        if isinstance(disagg_data, dict) and "values" in disagg_data:
            data_to_resolve = disagg_data.get("values", {})

        if not isinstance(data_to_resolve, dict):
            return None

        resolved: Dict[str, Any] = {}
        for key, value in data_to_resolve.items():
            if key.startswith("_"):
                continue  # Skip metadata keys

            # Handle variable-column format: {"modified": ..., "original": ...}
            if isinstance(value, dict) and ("modified" in value or "original" in value):
                value = value.get("modified") if value.get("modified") is not None else value.get("original")

            # Parse the key (e.g., "IFRC Secretariat_SP1" -> row="IFRC Secretariat", col="SP1")
            parts = str(key).rsplit("_", 1)
            if len(parts) == 2:
                row_part, col_code = parts
                col_label = column_labels.get(col_code, col_code)
                resolved_key = f"{row_part} - {col_label}"
            else:
                resolved_key = key

            # Format numeric values
            if isinstance(value, (int, float)):
                resolved[resolved_key] = value
            elif value is not None:
                try:
                    resolved[resolved_key] = float(str(value).replace(",", ""))
                except (ValueError, TypeError):
                    resolved[resolved_key] = str(value)

        return resolved if resolved else None

    def _build_context(self, fd: FormData) -> Dict[str, Any]:
        # Submission metadata
        submission_type = "assigned" if fd.assignment_entity_status_id else "public" if fd.public_submission_id else "unknown"
        aes: Optional[AssignmentEntityStatus] = fd.assignment_entity_status if fd.assignment_entity_status_id else None
        ps: Optional[PublicSubmission] = fd.public_submission if fd.public_submission_id else None

        assigned_form: Optional[AssignedForm] = None
        if aes and aes.assigned_form:
            assigned_form = aes.assigned_form
        elif ps and getattr(ps, "assigned_form", None):
            assigned_form = ps.assigned_form

        country = None
        try:
            if aes and aes.country:
                country = aes.country
            elif ps and getattr(ps, "country", None):
                country = ps.country
        except Exception as e:
            logger.debug("country resolve failed: %s", e)
            country = None

        item: Optional[FormItem] = fd.form_item if fd.form_item_id else None
        item_label = None
        try:
            item_label = item.label if item else None
        except Exception as e:
            logger.debug("item.label failed: %s", e)
            item_label = None

        template_id = getattr(assigned_form, "template_id", None) if assigned_form else None
        period_name = getattr(assigned_form, "period_name", None) if assigned_form else None

        # Value summary (keep small + stable)
        data_status = "available"
        if fd.data_not_available:
            data_status = "data_not_available"
        elif fd.not_applicable:
            data_status = "not_applicable"

        value_preview: Optional[str] = None
        scalar_value_preview: Optional[str] = None
        disagg_values_resolved: Optional[Dict[str, Any]] = None  # resolved breakdown for LLM context
        disagg_clean: Optional[Dict[str, Any]] = None

        # Include both scalar value AND disaggregation/matrix data when present.
        # Many indicators store a total in `value` and the breakdown in `disagg_data`; validation must see both.
        if data_status == "available":
            if (fd.value is not None) and (not _is_blankish_value(fd.value)):
                scalar_value_preview = str(fd.value).strip()

            disagg_clean = _normalize_disagg_for_presence(getattr(fd, "disagg_data", None))
            if disagg_clean is not None:
                try:
                    disagg_values_resolved = self._resolve_disagg_labels(disagg_clean, item)
                except Exception as e:
                    logger.warning("Failed to resolve disagg labels: %s", e)
                    disagg_values_resolved = None

            # Prefer scalar as "value" preview (stable), but still include disagg_values separately.
            if scalar_value_preview:
                value_preview = scalar_value_preview
            elif disagg_clean is not None:
                # Provide a compact, readable preview for evidence retrieval when scalar is missing.
                try:
                    if disagg_values_resolved:
                        total_value = sum(
                            v for v in disagg_values_resolved.values()
                            if isinstance(v, (int, float))
                        )
                        value_preview = f"matrix total {total_value:,.0f}" if total_value else "matrix data"
                    elif isinstance(disagg_clean, dict) and "values" in disagg_clean:
                        value_preview = f"disaggregation({disagg_clean.get('mode')})"
                    elif isinstance(disagg_clean, dict):
                        value_preview = "disaggregation(matrix)"
                    else:
                        value_preview = "disaggregation"
                except Exception as e:
                    logger.debug("value_preview failed: %s", e)
                    value_preview = "disaggregation"

        # Item metadata (helps the LLM choose correct suggestion formats)
        item_type = None
        field_type_for_js = None
        allowed_disagg_modes: List[str] = []
        matrix_schema: Optional[Dict[str, Any]] = None
        choice_options: Optional[List[Dict[str, Any]]] = None
        try:
            item_type = getattr(item, "item_type", None) if item else None
            field_type_for_js = getattr(item, "field_type_for_js", None) if item else None
        except Exception as e:
            logger.debug("item_type/field_type_for_js failed: %s", e)

        # Disaggregation modes apply to indicators only (questions have a default config field too; ignore it).
        try:
            if item and getattr(item, "is_indicator", False):
                adm = getattr(item, "allowed_disaggregation_options", None)
                if isinstance(adm, list):
                    allowed_disagg_modes = [str(x) for x in adm if x is not None]
        except Exception as e:
            logger.debug("allowed_disagg_modes failed: %s", e)
            allowed_disagg_modes = []

        try:
            if item_type == "matrix" and item and isinstance(getattr(item, "config", None), dict):
                cfg = item.config or {}
                mc = cfg.get("matrix_config") if isinstance(cfg.get("matrix_config"), dict) else None
                if mc:
                    # Keep compact: enough to build cell keys <rowId>_<columnName>
                    cols = mc.get("columns", [])
                    rows = mc.get("rows", [])
                    matrix_schema = {
                        "row_mode": mc.get("row_mode") or cfg.get("row_mode"),
                        "columns": [
                            {
                                "id": (c.get("id") or c.get("name")) if isinstance(c, dict) else str(c),
                                "name": c.get("name") if isinstance(c, dict) else str(c),
                                "label": (c.get("label") or c.get("name")) if isinstance(c, dict) else str(c),
                            }
                            for c in cols
                            if c is not None
                        ][:40],
                        "rows": rows[:80] if isinstance(rows, list) else None,
                        "lookup_list_id": mc.get("lookup_list_id"),
                    }
        except Exception as e:
            logger.debug("matrix_schema failed: %s", e)
            matrix_schema = None

        # Choice question options (single_choice / multiple_choice):
        # The stored answer is the option "value" (often a code like "CHF"), not a display label.
        try:
            if item_type == "question" and str(field_type_for_js or "").strip().lower() in ("single_choice", "multiple_choice"):
                raw_opts = getattr(item, "options", []) if item else []
                if isinstance(raw_opts, list) and raw_opts:
                    parsed: List[Dict[str, Any]] = []
                    for opt in raw_opts[:250]:
                        if isinstance(opt, dict):
                            v = opt.get("value") if opt.get("value") is not None else opt.get("id")
                            lbl = opt.get("label") if opt.get("label") is not None else v
                            if v is None:
                                continue
                            parsed.append({"value": str(v), "label": (str(lbl) if lbl is not None else str(v))})
                        else:
                            s = str(opt).strip()
                            if not s:
                                continue
                            parsed.append({"value": s, "label": s})
                    choice_options = parsed if parsed else None
        except Exception as e:
            logger.debug("choice_options parse failed: %s", e)
            choice_options = None

        # Disaggregation suggestion target:
        # - indicators with allowed disaggregation: suggest `{"mode":..., "values": {...}}`
        # - matrix: suggest raw dict of cellKey -> value (same as entry_form hidden field)
        suggestion_disagg_format = None
        if item_type == "matrix":
            suggestion_disagg_format = "matrix_raw"
        elif item and getattr(item, "is_indicator", False) and getattr(item, "supports_disaggregation", False) and allowed_disagg_modes:
            suggestion_disagg_format = "indicator_mode_values"

        indicator_bank_id = None
        try:
            if item and getattr(item, "is_indicator", False) and getattr(item, "indicator_bank_id", None):
                indicator_bank_id = int(getattr(item, "indicator_bank_id"))
        except Exception as e:
            logger.debug("indicator_bank_id failed: %s", e)
            indicator_bank_id = None

        ctx = {
            # fd may be transient (virtual missing row). In that case it has no primary key.
            "form_data_id": _safe_int(getattr(fd, "id", None)),
            "submission_type": submission_type,
            "submission_id": int(aes.id) if aes else (int(ps.id) if ps else None),
            "template_id": _safe_int(template_id),
            "period_name": (str(period_name).strip() if period_name else None),
            "period_year": _parse_year_from_period(period_name),
            "country_id": _safe_int(getattr(country, "id", None)),
            "country_name": (str(getattr(country, "name", "")).strip() or None) if country else None,
            "form_item_id": int(fd.form_item_id) if fd.form_item_id else None,
            "indicator_bank_id": indicator_bank_id,
            "form_item_label": (str(item_label).strip() if item_label else None),
            "form_item_type": (str(item_type).strip() if item_type else None),
            "field_type_for_js": (str(field_type_for_js).strip() if field_type_for_js else None),
            "allowed_disaggregation_modes": allowed_disagg_modes or None,
            "matrix_schema": matrix_schema,
            "suggestion_disagg_format": suggestion_disagg_format,
            "choice_options": choice_options,
            "data_status": data_status,
            "value": value_preview,
            "disagg_values": disagg_values_resolved,  # Resolved matrix values for LLM validation
        }
        return ctx

    def _retrieve_evidence(
        self,
        context: Dict[str, Any],
        *,
        top_k: int,
        sources_cfg: Optional[Dict[str, bool]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant AI document chunks from the library.

        We strongly prefer restricting by country when available (reduces false matches),
        but do not require it.
        """
        country_name = context.get("country_name") or ""
        period_name = context.get("period_name") or ""
        item_label = context.get("form_item_label") or ""
        value = context.get("value") or ""

        # For matrix data, build a more semantic query using category labels
        disagg_values = context.get("disagg_values")
        if disagg_values and isinstance(disagg_values, dict):
            # Extract unique category labels from the resolved disagg keys
            # Keys are like "IFRC Secretariat - Climate & environment"
            categories = set()
            for key in disagg_values.keys():
                if " - " in key:
                    _, category = key.rsplit(" - ", 1)
                    categories.add(category)
            # Build query with category terms for better semantic matching
            if categories:
                category_terms = " ".join(list(categories)[:4])  # Limit to 4 categories
                query_text = f"{country_name} {period_name} {item_label} funding {category_terms}".strip()
            else:
                query_text = f"{country_name} {period_name} {item_label} funding breakdown".strip()
        else:
            query_text = " ".join([str(x) for x in [country_name, period_name, item_label, "reported value", value] if x]).strip()

        if not query_text:
            query_text = f"FormData {context.get('form_data_id')}"

        base_filters: Dict[str, Any] = {}
        if context.get("country_id"):
            base_filters["country_id"] = int(context["country_id"])
        if context.get("country_name"):
            base_filters["country_name"] = str(context["country_name"])

        # Source selection:
        # - system_documents=True => allow non-API docs (system uploads + local uploads)
        # - upr_documents=True => allow API-imported docs (IFRC API/UPR)
        # When both are True (or sources_cfg is None), allow all.
        selection_filters: Dict[str, Any] = {}
        if sources_cfg is not None:
            include_system = bool(sources_cfg.get("system_documents", False))
            include_upr = bool(sources_cfg.get("upr_documents", False))
            if include_system and not include_upr:
                selection_filters["is_api_import"] = False
            elif include_upr and not include_system:
                selection_filters["is_api_import"] = True
            elif not include_system and not include_upr:
                return []

        user_id = None
        user_role = None
        try:
            # Use same access-level naming used by vector store
            from app.services.authorization_service import AuthorizationService
            from flask_login import current_user

            user_id = int(current_user.id) if getattr(current_user, "is_authenticated", False) else None
            user_role = AuthorizationService.access_level(current_user) if getattr(current_user, "is_authenticated", False) else None
        except Exception as e:
            logger.debug("user context failed: %s", e)
            user_id = None
            user_role = None

        def _score(r: Dict[str, Any]) -> float:
            try:
                return float(r.get("combined_score") or r.get("score") or r.get("similarity_score") or r.get("keyword_score") or 0.0)
            except Exception as e:
                logger.debug("_score failed: %s", e)
                return 0.0

        def _merge_and_dedup(*batches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            seen = set()
            out: List[Dict[str, Any]] = []
            for batch in batches:
                for r in batch or []:
                    try:
                        cid = r.get("chunk_id")
                        if cid is None:
                            continue
                        if cid in seen:
                            continue
                        seen.add(cid)
                        out.append(r)
                    except Exception as e:
                        logger.debug("result append failed: %s", e)
                        continue
            out.sort(key=_score, reverse=True)
            return out

        def _apply_per_doc_cap(rs: List[Dict[str, Any]], *, max_per_doc: int) -> List[Dict[str, Any]]:
            if max_per_doc <= 0:
                return rs
            counts: Dict[Any, int] = {}
            kept: List[Dict[str, Any]] = []
            for r in rs:
                did = r.get("document_id")
                if did is None:
                    continue
                n = counts.get(did, 0)
                if n >= max_per_doc:
                    continue
                counts[did] = n + 1
                kept.append(r)
            return kept

        # Multi-pass retrieval:
        # 1) General hybrid search (may strongly prefer system docs)
        # 2) If API-imported docs are missing, explicitly fetch API docs too
        # 3) If results are still narrow, broaden the query (drop period/value) for recall
        try:
            initial_k = max(10, min(20, int(top_k) * 2))
            results_general = self.vector_store.hybrid_search(
                query_text=query_text,
                top_k=initial_k,
                filters={**(base_filters or {}), **(selection_filters or {})} or None,
                user_id=user_id,
                user_role=user_role,
            )
        except Exception as e:
            logger.warning("Evidence retrieval failed for FormData %s: %s", context.get("form_data_id"), e, exc_info=True)
            results_general = []

        has_api = any(bool(r.get("is_api_import")) for r in (results_general or []))
        results_api: List[Dict[str, Any]] = []
        include_upr = True if sources_cfg is None else bool(sources_cfg.get("upr_documents", False))
        if include_upr and not has_api and selection_filters.get("is_api_import", None) is not False:
            try:
                results_api = self.vector_store.hybrid_search(
                    query_text=query_text,
                    top_k=max(6, min(12, int(top_k))),
                    filters={**(base_filters or {}), **(selection_filters or {}), "is_api_import": True},
                    user_id=user_id,
                    user_role=user_role,
                )
            except Exception as e:
                logger.debug("results_api failed: %s", e)
                results_api = []

        # Ensure system-uploaded documents are represented when available.
        # Some system docs may have incomplete country metadata; do a relaxed pass without country filters.
        include_system = True if sources_cfg is None else bool(sources_cfg.get("system_documents", False))
        has_system = any(bool(r.get("is_system_document")) for r in (results_general or []))
        results_system_relaxed: List[Dict[str, Any]] = []
        if include_system and not has_system and selection_filters.get("is_api_import", None) is not True:
            try:
                results_system_relaxed = self.vector_store.hybrid_search(
                    query_text=query_text,
                    top_k=max(6, min(12, int(top_k))),
                    filters={**(selection_filters or {}), "is_system_document": True},
                    user_id=user_id,
                    user_role=user_role,
                )
            except Exception as e:
                logger.debug("results_system_relaxed failed: %s", e)
                results_system_relaxed = []

        results_broad: List[Dict[str, Any]] = []
        try:
            merged_tmp = _merge_and_dedup(results_general or [], results_api or [])
            unique_docs_tmp = {r.get("document_id") for r in merged_tmp if r.get("document_id") is not None}
            if len(unique_docs_tmp) < 3:
                broad_query = " ".join([str(x) for x in [country_name, item_label, "definition", "reported value"] if x]).strip()
                if broad_query:
                    results_broad = self.vector_store.hybrid_search(
                        query_text=broad_query,
                        top_k=max(6, min(12, int(top_k))),
                        filters={**(base_filters or {}), **(selection_filters or {})} or None,
                        user_id=user_id,
                        user_role=user_role,
                    )
        except Exception as e:
            logger.debug("results_broad failed: %s", e)
            results_broad = []

        merged = _merge_and_dedup(results_general or [], results_api or [], results_system_relaxed or [], results_broad or [])

        # Diversity: cap chunks per document for validation prompts (keeps sources varied).
        max_per_doc = int(current_app.config.get("AI_VALIDATION_MAX_CHUNKS_PER_DOC", 2))
        merged = _apply_per_doc_cap(merged, max_per_doc=max(0, max_per_doc))

        # Finally return up to top_k chunks (bounded)
        target_k = max(1, min(int(top_k), 20))
        results = merged[:target_k]

        # Log unique documents found (helps diagnose missing documents)
        unique_docs = {}
        for r in results or []:
            doc_id = r.get("document_id")
            if doc_id and doc_id not in unique_docs:
                # Track source type for debugging
                source = "system" if r.get("is_system_document") else ("api" if r.get("is_api_import") else "local")
                unique_docs[doc_id] = {
                    "title": r.get("document_title"),
                    "source": source,
                    "chunks": 0,
                    "best_score": r.get("combined_score") or r.get("score") or r.get("similarity_score"),
                    "boost": r.get("source_boost", 0),
                }
            if doc_id:
                unique_docs[doc_id]["chunks"] += 1
        logger.info(
            "Evidence retrieval: %d chunks from %d unique documents: %s",
            len(results or []),
            len(unique_docs),
            [{"id": k, **v} for k, v in list(unique_docs.items())[:5]],  # Log top 5 docs
        )

        # Trim to a compact, stable structure for DB + UI.
        # Limit content size to avoid LLM prompt overflow (finish_reason=length errors)
        trimmed: List[Dict[str, Any]] = []
        for r in results or []:
            src = "system" if r.get("is_system_document") else ("api" if r.get("is_api_import") else "local")
            trimmed.append(
                {
                    "chunk_id": _safe_int(r.get("chunk_id")),
                    "document_id": _safe_int(r.get("document_id")),
                    "document_title": r.get("document_title"),
                    "document_filename": r.get("document_filename"),
                    "document_type": r.get("document_type"),
                    "page_number": r.get("page_number"),
                    "section_title": r.get("section_title"),
                    "score": r.get("combined_score", r.get("score", r.get("similarity_score"))),
                    "source": src,
                    "is_system_document": bool(r.get("is_system_document")),
                    "is_api_import": bool(r.get("is_api_import")),
                    "content": (r.get("content") or "")[:1000],  # Reduced from 2000 to prevent token overflow
                }
            )
        return trimmed

    def _run_llm_validation(
        self,
        *,
        context: Dict[str, Any],
        evidence_chunks: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any], str, Optional[str]]:
        """
        Returns (provider, model, parsed_json, raw_text, error_message)
        """
        prompt = self._build_prompt(context=context, evidence_chunks=evidence_chunks)

        def _payload_ok(obj: Dict[str, Any]) -> bool:
            if not isinstance(obj, dict) or not obj:
                return False
            v = (obj.get("verdict") or "").strip().lower()
            if v not in ("good", "discrepancy", "uncertain"):
                return False
            # Require an explanation
            op = (obj.get("opinion_summary") or obj.get("opinion") or "").strip()
            if len(op) < 10:
                return False
            return True

        last_error: Optional[str] = None

        # OpenAI only (no Gemini/Azure/Copilot fallbacks)
        import os
        if not (current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
            return None, None, {}, "", "OpenAI not configured (missing OPENAI_API_KEY)."

        from openai import OpenAI
        import time as _time

        model_name = current_app.config.get("OPENAI_MODEL", "gpt-5-mini")
        openai_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        timeout_sec = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60))
        client = OpenAI(api_key=openai_key, timeout=timeout_sec)

        # Diagnostics (avoid logging prompt content; only log sizing + IDs)
        prompt_len_chars = len(prompt or "")
        evidence_count = len(evidence_chunks or [])
        ctx_diag = {
            "country_id": context.get("country_id"),
            "period": context.get("period_name") or context.get("period_year"),
            "form_item_id": context.get("form_item_id"),
            "indicator_bank_id": context.get("indicator_bank_id"),
        }

        base_max_completion_tokens = int(current_app.config.get("AI_FORMDATA_VALIDATION_MAX_COMPLETION_TOKENS", 3000))
        base_max_completion_tokens = max(800, min(base_max_completion_tokens, 8000))

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict data validation assistant.\n"
                    "Return ONLY valid JSON (no markdown, no backticks, no extra text).\n"
                    "Keep fields concise: opinion_summary <= 700 chars, max 6 bullet-like points if needed.\n"
                    "If uncertain, set verdict='uncertain' and explain briefly."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        # Some reasoning-focused models reject sampling params; mirror ai_chat_engine conservative behavior.
        supports_sampling = not (str(model_name or "").strip().lower().startswith("gpt-5"))

        # Retry logic for empty/invalid responses (also handles finish_reason=length).
        max_retries = 2
        for attempt in range(max_retries + 1):
            max_out = base_max_completion_tokens + (750 * attempt)
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "max_completion_tokens": int(max_out),
            }
            if supports_sampling:
                kwargs["temperature"] = 0.2

            try:
                resp = client.chat.completions.create(**kwargs)

                if not resp or not getattr(resp, "choices", None):
                    last_error = "No choices in OpenAI response"
                    logger.warning(
                        "OpenAI validation: response missing choices (attempt=%d/%d model=%s max_completion_tokens=%s prompt_chars=%s evidence=%s ctx=%s)",
                        attempt + 1,
                        max_retries + 1,
                        model_name,
                        max_out,
                        prompt_len_chars,
                        evidence_count,
                        ctx_diag,
                    )
                    if attempt < max_retries:
                        _time.sleep(0.5 * (attempt + 1))
                        continue
                    break

                choice0 = resp.choices[0]
                msg = getattr(choice0, "message", None)
                raw_text = (getattr(msg, "content", None) or "").strip() if msg else ""
                refusal = getattr(msg, "refusal", None) if msg else None
                finish_reason = getattr(choice0, "finish_reason", None)
                tool_calls = getattr(msg, "tool_calls", None) if msg else None
                has_tool_calls = bool(tool_calls)

                usage = getattr(resp, "usage", None)
                usage_diag = None
                try:
                    usage_diag = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    } if usage else None
                except Exception as e:
                    logger.debug("usage_diag failed: %s", e)
                    usage_diag = None

                # OpenAI sometimes returns tool_calls with empty content; treat as failure for this endpoint.
                if not raw_text:
                    last_error = (
                        f"Empty OpenAI content"
                        f"{': refusal=' + str(refusal) if refusal else ''}"
                        f"{', finish_reason=' + str(finish_reason) if finish_reason else ''}"
                        f"{', tool_calls=true' if has_tool_calls else ''}"
                    )
                    logger.warning(
                        "OpenAI validation: empty content (attempt=%d/%d model=%s finish_reason=%s max_completion_tokens=%s usage=%s prompt_chars=%s evidence=%s ctx=%s)",
                        attempt + 1,
                        max_retries + 1,
                        model_name,
                        finish_reason,
                        max_out,
                        usage_diag,
                        prompt_len_chars,
                        evidence_count,
                        ctx_diag,
                    )
                    if attempt < max_retries:
                        _time.sleep(0.5 * (attempt + 1))
                        continue
                    break

                # If the model hit the output limit, retry with a larger budget.
                if str(finish_reason).lower() == "length" and attempt < max_retries:
                    logger.warning(
                        "OpenAI validation: finish_reason=length; retrying with higher max_completion_tokens (attempt=%d/%d model=%s max_completion_tokens=%s usage=%s ctx=%s)",
                        attempt + 1,
                        max_retries + 1,
                        model_name,
                        max_out,
                        usage_diag,
                        ctx_diag,
                    )
                    _time.sleep(0.5 * (attempt + 1))
                    continue

                parsed = _extract_json_object(raw_text) or {}
                if not _payload_ok(parsed):
                    last_error = f"Invalid JSON payload (missing verdict/opinion), finish_reason={finish_reason}"
                    logger.warning(
                        "OpenAI validation: invalid payload (attempt=%d/%d model=%s finish_reason=%s max_completion_tokens=%s usage=%s raw_len=%s ctx=%s)",
                        attempt + 1,
                        max_retries + 1,
                        model_name,
                        finish_reason,
                        max_out,
                        usage_diag,
                        len(raw_text or ""),
                        ctx_diag,
                    )
                    if attempt < max_retries:
                        _time.sleep(0.5 * (attempt + 1))
                        continue
                    break

                return "openai", str(model_name), parsed, raw_text, None

            except Exception as e:
                last_error = "OpenAI validation failed"
                logger.warning(
                    "OpenAI validation attempt %d/%d failed (model=%s max_completion_tokens=%s prompt_chars=%s evidence=%s ctx=%s): %s",
                    attempt + 1,
                    max_retries + 1,
                    model_name,
                    max_out,
                    prompt_len_chars,
                    evidence_count,
                    ctx_diag,
                    e,
                    exc_info=True,
                )
                if attempt < max_retries:
                    _time.sleep(0.5 * (attempt + 1))
                    continue
                break

        return None, None, {}, "", (last_error or "OpenAI validation failed")

    def _retrieve_historical_values(
        self,
        *,
        context: Dict[str, Any],
        exclude_form_data_id: Optional[int],
        limit_periods: int = 6,
    ) -> Dict[str, Any]:
        """
        Fetch historical values for the same country across other periods.

        Matching logic:
        - Prefer matching by indicator identity when available (indicator_bank_id). This is more stable than form_item_id
          across template versions, but in real data the same logical indicator can exist under multiple IndicatorBank
          records historically (duplicates / renames). When an IndicatorBank has an `fdrs_kpi_code`, we treat that as a
          stable key and include all IndicatorBank ids that share that code.
        - Include both regular `FormData` and `DynamicIndicatorData` (repeat/dynamic indicators) when applicable.

        Returns:
          {
            "series": [{period_name, period_year, value_int, status_timestamp, assignment_entity_status_id, form_data_id}],
            "summary": {count, min, max, median, latest_period_name, latest_value_int, yoy_change_ratio}
          }
        """
        country_id = context.get("country_id")
        form_item_id = context.get("form_item_id")
        indicator_bank_id = context.get("indicator_bank_id")
        if not country_id or not form_item_id:
            return {"series": [], "summary": {"count": 0}}

        # Include draft-ish statuses too. In many deployments, older periods exist in the databank
        # but the AES status is not always Submitted/Approved (e.g. Assigned/In Progress).
        # We still want a plausibility series for validation.
        # NOTE: Older imported periods are often left in "Pending" (default AES status),
        # but still represent useful historical values for plausibility checks.
        included_statuses = ["Pending", "Submitted", "Approved", "Completed", "In Progress", "Assigned"]

        try:
            # Build indicator_bank_id set (handles historical duplicates via fdrs_kpi_code when present).
            indicator_ids: Optional[List[int]] = None
            try:
                if indicator_bank_id:
                    base_id = int(indicator_bank_id)
                    indicator_ids = [base_id]
                    fdrs_code = (
                        db.session.query(IndicatorBank.fdrs_kpi_code)
                        .filter(IndicatorBank.id == base_id)
                        .scalar()
                    )
                    fdrs_code = (str(fdrs_code).strip() if fdrs_code else "") or None
                    if fdrs_code:
                        extra_ids = [
                            int(r[0])
                            for r in (
                                db.session.query(IndicatorBank.id)
                                .filter(IndicatorBank.fdrs_kpi_code == fdrs_code)
                                .limit(50)
                                .all()
                            )
                            if r and r[0] is not None
                        ]
                        # De-dupe while preserving order; cap to avoid huge IN clauses.
                        merged_ids = list(dict.fromkeys([*indicator_ids, *extra_ids]))
                        indicator_ids = merged_ids[:50]
            except Exception as e:
                logger.debug("indicator_ids merge failed: %s", e)
                indicator_ids = [int(indicator_bank_id)] if indicator_bank_id else None

            q = (
                db.session.query(
                    FormData,
                    AssignedForm.period_name,
                    AssignmentEntityStatus.status_timestamp,
                    AssignmentEntityStatus.status,
                    AssignmentEntityStatus.id.label("aes_id"),
                )
                .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
                .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .join(FormItem, FormData.form_item_id == FormItem.id)
                .filter(
                    AssignmentEntityStatus.entity_type == "country",
                    AssignmentEntityStatus.entity_id == int(country_id),
                    AssignmentEntityStatus.status.in_(included_statuses),
                )
            )
            if indicator_ids:
                q = q.filter(FormItem.indicator_bank_id.in_(indicator_ids))
            else:
                q = q.filter(FormData.form_item_id == int(form_item_id))
            if exclude_form_data_id:
                q = q.filter(FormData.id != int(exclude_form_data_id))

            # Pull a small candidate set and de-dupe per period in Python (period_name is string).
            rows_formdata = q.order_by(AssignmentEntityStatus.status_timestamp.desc()).limit(400).all()

            # Also include DynamicIndicatorData for the same indicator (if indicator identity is available).
            rows_dynamic: List[Any] = []
            if indicator_ids:
                try:
                    qd = (
                        db.session.query(
                            DynamicIndicatorData,
                            AssignedForm.period_name,
                            AssignmentEntityStatus.status_timestamp,
                            AssignmentEntityStatus.status,
                            AssignmentEntityStatus.id.label("aes_id"),
                        )
                        .join(AssignmentEntityStatus, DynamicIndicatorData.assignment_entity_status_id == AssignmentEntityStatus.id)
                        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                        .filter(
                            AssignmentEntityStatus.entity_type == "country",
                            AssignmentEntityStatus.entity_id == int(country_id),
                            AssignmentEntityStatus.status.in_(included_statuses),
                            DynamicIndicatorData.indicator_bank_id.in_(indicator_ids),
                        )
                    )
                    rows_dynamic = qd.order_by(AssignmentEntityStatus.status_timestamp.desc()).limit(400).all()
                except Exception as e:
                    logger.debug("rows_dynamic query failed: %s", e)
                    rows_dynamic = []
        except Exception as e:
            logger.warning("Historical query failed: %s", e, exc_info=True)
            return {"series": [], "summary": {"count": 0, "error": "An error occurred."}}

        # Build a latest-per-period series
        best_per_period: Dict[str, Dict[str, Any]] = {}
        # Normalize FormData rows
        for fd, period_name, status_ts, aes_status, aes_id in rows_formdata or []:
            if not period_name:
                continue
            key = str(period_name)
            if key in best_per_period:
                continue
            try:
                if fd.data_not_available or fd.not_applicable:
                    continue
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)

            # Use effective display value so history includes prefilled/imputed values too.
            raw_val = None
            try:
                raw_val = getattr(fd, "value", None)
            except Exception as e:
                logger.debug("fd.value get failed: %s", e)
                raw_val = None
            if _is_blankish_value(raw_val):
                try:
                    raw_val = getattr(fd, "prefilled_value", None)
                except Exception as e:
                    logger.debug("prefilled_value get failed: %s", e)
            if _is_blankish_value(raw_val):
                try:
                    raw_val = getattr(fd, "imputed_value", None)
                except Exception as e:
                    logger.debug("imputed_value get failed: %s", e)

            v_int = _parse_int_number(raw_val)
            if v_int is None:
                continue

            best_per_period[key] = {
                "period_name": key,
                "period_year": _parse_year_from_period(key),
                "value_int": int(v_int),
                "status_timestamp": status_ts.isoformat() if status_ts else None,
                "aes_status": str(aes_status) if aes_status is not None else None,
                "assignment_entity_status_id": int(aes_id) if aes_id is not None else None,
                "form_data_id": int(getattr(fd, "id", 0) or 0),
            }

        # Normalize DynamicIndicatorData rows (only fill periods not already covered by FormData above)
        for dd, period_name, status_ts, aes_status, aes_id in rows_dynamic or []:
            if not period_name:
                continue
            key = str(period_name)
            if key in best_per_period:
                continue
            try:
                if dd.data_not_available or dd.not_applicable:
                    continue
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)

            raw_val = None
            try:
                raw_val = getattr(dd, "value", None)
            except Exception as e:
                logger.debug("dd.value get failed: %s", e)
                raw_val = None
            if _is_blankish_value(raw_val):
                try:
                    # Dynamic indicators may store totals in disagg_data too.
                    raw_val = getattr(dd, "total_value", None)
                except Exception as e:
                    logger.debug("total_value get failed: %s", e)

            v_int = _parse_int_number(raw_val)
            if v_int is None:
                continue

            best_per_period[key] = {
                "period_name": key,
                "period_year": _parse_year_from_period(key),
                "value_int": int(v_int),
                "status_timestamp": status_ts.isoformat() if status_ts else None,
                "aes_status": str(aes_status) if aes_status is not None else None,
                "assignment_entity_status_id": int(aes_id) if aes_id is not None else None,
                # Keep shape stable; dynamic rows don't have a FormData id.
                "form_data_id": None,
            }

        series = list(best_per_period.values())
        # Sort by period_year asc when available, else by timestamp asc.
        def _sort_key(x: Dict[str, Any]):
            y = x.get("period_year")
            ts = x.get("status_timestamp") or ""
            return (y if isinstance(y, int) else 0, ts)

        series.sort(key=_sort_key)
        # Keep last N periods
        if limit_periods and len(series) > int(limit_periods):
            series = series[-int(limit_periods) :]

        values = [int(x["value_int"]) for x in series if isinstance(x.get("value_int"), int)]
        summary: Dict[str, Any] = {
            "count": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "median": _median_int(values) if values else None,
            "latest_period_name": series[-1]["period_name"] if series else None,
            "latest_value_int": values[-1] if values else None,
        }
        try:
            statuses = [str(x.get("aes_status")) for x in series if x and x.get("aes_status")]
            statuses = list(dict.fromkeys([s for s in statuses if s and s.lower() not in ("none", "null")]))
            if statuses:
                summary["statuses"] = statuses[:10]
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)
        # YoY change ratio (latest vs previous in series)
        if len(values) >= 2 and values[-2] not in (0, None):
            try:
                summary["yoy_change_ratio"] = (values[-1] - values[-2]) / float(values[-2])
            except Exception as e:
                logger.debug("yoy_change_ratio failed: %s", e)
                summary["yoy_change_ratio"] = None
        else:
            summary["yoy_change_ratio"] = None

        return {"series": series, "summary": summary}

    def _heuristic_validate(
        self,
        *,
        context: Dict[str, Any],
        evidence_chunks: List[Dict[str, Any]],
        historical: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic fallback to produce:
        - verdict
        - quality estimate (0..1)
        - opinion (why)
        """
        label = context.get("form_item_label")
        keyword = _infer_primary_keyword(label) or ""
        reported_int = _parse_int_number(context.get("value"))

        # Evidence source 1: structured UPR KPI extraction (best for UPR docs)
        upr = None
        upr_value_int: Optional[int] = None
        upr_metric = None
        try:
            upr_metric = {
                "branches": "branches",
                "staff": "staff",
                "volunteers": "volunteers",
                "local units": "local_units",
            }.get(keyword)
            if upr_metric and not _upr_kpi_applicable(label, keyword):
                upr_metric = None
            # Prefer a pre-fetched UPR KPI reference included in context (avoids extra DB work).
            if isinstance(context.get("upr_kpi"), dict) and context.get("upr_kpi", {}).get("value") is not None:
                upr = context.get("upr_kpi")
                upr_value_int = _parse_int_number((upr or {}).get("value"))
            elif upr_metric and context.get("country_id"):
                from app.services.data_retrieval_service import get_upr_kpi_value as get_upr_kpi_value_service

                upr = get_upr_kpi_value_service(
                    country_identifier=int(context["country_id"]),
                    metric=upr_metric,
                )
                if isinstance(upr, dict) and upr.get("success") and upr.get("value") is not None:
                    upr_value_int = _parse_int_number(upr.get("value"))
        except Exception as e:
            logger.debug("upr parse failed: %s", e)
            upr = None
            upr_value_int = None

        claims = _extract_keyword_number_claims(
            keyword=keyword,
            evidence_chunks=evidence_chunks,
            required_terms=_required_terms_for_claims(label, keyword),
        )
        claim_values = sorted({c.get("value") for c in claims if isinstance(c.get("value"), int)})

        matches_text = reported_int is not None and any(int(v) == int(reported_int) for v in claim_values)
        text_conflicts = reported_int is not None and any(int(v) != int(reported_int) for v in claim_values)
        matches_upr = (reported_int is not None and upr_value_int is not None and int(upr_value_int) == int(reported_int))
        upr_conflicts = (reported_int is not None and upr_value_int is not None and int(upr_value_int) != int(reported_int))

        # Historical comparison (structured data from other assignments/periods)
        hist_summary = (historical or {}).get("summary") if isinstance(historical, dict) else None
        hist_series = (historical or {}).get("series") if isinstance(historical, dict) else None
        hist_values = []
        try:
            hist_values = [int(x.get("value_int")) for x in (hist_series or []) if x and x.get("value_int") is not None]
        except Exception as e:
            logger.debug("hist_values parse failed: %s", e)
            hist_values = []
        hist_median = _median_int(hist_values) if hist_values else None

        # Split into prior vs later periods relative to current row (for data-driven conclusions)
        current_period_year = _parse_year_from_period(context.get("period_name"))
        prior_series = []
        later_series = []
        for p in hist_series or []:
            py = p.get("period_year") if p.get("period_year") is not None else _parse_year_from_period(p.get("period_name"))
            if py is None:
                prior_series.append(p)
            elif current_period_year is None:
                prior_series.append(p)
            elif py < current_period_year:
                prior_series.append(p)
            elif py > current_period_year:
                later_series.append(p)

        if reported_int is None:
            # Missing / not parseable value: try to suggest a plausible value from evidence + history.
            suggested = None
            reason = None
            if upr_value_int is not None:
                suggested = int(upr_value_int)
                reason = _upr_suggestion_reason(upr, int(upr_value_int))
            elif claim_values:
                if len(claim_values) == 1:
                    suggested = int(claim_values[0])
                    reason = f"Document evidence repeatedly mentions {_format_int(int(claim_values[0]))} for {keyword or 'this metric'}."
                else:
                    suggested = _median_int([int(v) for v in claim_values if v is not None]) or int(claim_values[0])
                    reason = f"Document evidence contains multiple values for {keyword or 'this metric'}; median/typical value is {_format_int(int(suggested))}."
            else:
                try:
                    latest_hist = (hist_summary or {}).get("latest_value_int") if isinstance(hist_summary, dict) else None
                    if latest_hist is not None:
                        suggested = int(latest_hist)
                        latest_period_name = (hist_summary or {}).get("latest_period_name") if isinstance(hist_summary, dict) else None
                        if latest_period_name:
                            reason = f"Historical submissions suggest {_format_int(int(latest_hist))} (most recent prior period: {latest_period_name})."
                        else:
                            reason = f"Historical submissions suggest {_format_int(int(latest_hist))}."
                except Exception as e:
                    logger.debug("historical suggestion failed: %s", e)
                    suggested = None
                    reason = None

            if suggested is not None:
                upr_label = _upr_document_label(upr) if upr else "documents/historical data"
                opinion = (
                    f"Quality estimate: 55%. No reported value was found for this item. "
                    f"Based on {upr_label}, a plausible value is {_format_int(int(suggested))}. "
                    f"Please verify against the source."
                )
                return {
                    "verdict": "uncertain",
                    "quality": 0.55,
                    "opinion": opinion,
                    "claims": claims[:8],
                    "upr": upr,
                    "historical_summary": hist_summary,
                    "suggested_value": int(suggested),
                    "suggestion_reason": reason,
                }

            return {
                "verdict": "uncertain",
                "quality": 0.2,
                "opinion": "Quality estimate: 20%. No reported value was found and no strong document or historical evidence could be extracted to suggest one.",
                "claims": claims[:8],
                "upr": upr,
                "historical_summary": hist_summary,
            }

        # Build a short explanation referencing top claims
        def _fmt(n: int) -> str:
            return f"{n:,}"

        # If UPR provides a value, treat it as the primary reference (structured, purpose-built).
        if upr_value_int is not None:
            if matches_upr and not text_conflicts:
                # If a later submission has a different value, suggest that one may be wrong
                later_note = ""
                if later_series:
                    later_vals = [int(p.get("value_int")) for p in later_series if p.get("value_int") is not None]
                    if later_vals and reported_int is not None and int(reported_int) not in later_vals:
                        # Current matches document; a later period reports something else
                        first_later = later_series[0]
                        pn = (first_later.get("period_name") or "").strip()
                        v = first_later.get("value_int")
                        if pn and v is not None:
                            later_note = f" A later submission ({pn}) reports {_fmt(int(v))}; that value may be incorrect and should be verified."
                upr_label = _upr_document_label(upr)
                opinion = (
                    f"Quality estimate: 85%. The reported value {_fmt(reported_int)} matches {upr_label} for {keyword or 'this metric'}, and no conflicting values were found in the top retrieved text evidence.{later_note}"
                )
                return {
                    "verdict": "good",
                    "quality": 0.85,
                    "opinion": opinion,
                    "claims": claims[:6],
                    "upr": upr,
                }
            if upr_conflicts:
                extra = ""
                if matches_text:
                    extra = " A narrative section also mentions the same number, but this conflicts with the structured KPI block."

                # Use historical series as an additional signal: which value aligns better with past submissions?
                hist_count = int((hist_summary or {}).get("count") or 0) if isinstance(hist_summary, dict) else 0
                hist_min = (hist_summary or {}).get("min") if isinstance(hist_summary, dict) else None
                hist_max = (hist_summary or {}).get("max") if isinstance(hist_summary, dict) else None
                hist_med = (hist_summary or {}).get("median") if isinstance(hist_summary, dict) else None
                try:
                    hist_min_i = int(hist_min) if hist_min is not None else None
                    hist_max_i = int(hist_max) if hist_max is not None else None
                    hist_med_i = int(hist_med) if hist_med is not None else hist_median
                except Exception as e:
                    logger.debug("hist int conversion failed: %s", e)
                    hist_min_i = None
                    hist_max_i = None
                    hist_med_i = hist_median

                def _within_range(val: int) -> Optional[bool]:
                    if hist_min_i is None or hist_max_i is None:
                        return None
                    return bool(hist_min_i <= int(val) <= hist_max_i)

                def _near_median(val: int) -> Optional[bool]:
                    if hist_med_i is None or int(hist_med_i) == 0:
                        return None
                    try:
                        return abs(int(val) - int(hist_med_i)) / float(int(hist_med_i)) <= 0.25
                    except Exception as e:
                        logger.debug("within_25pct failed: %s", e)
                        return None

                rep_in = _within_range(int(reported_int))
                upr_in = _within_range(int(upr_value_int))
                rep_near = _near_median(int(reported_int))
                upr_near = _near_median(int(upr_value_int))

                # Describe history with period names so it's clear which period has which value.
                hist_line = ""
                if hist_count and hist_series:
                    # Build "Period: value" list (e.g. "2022: 20, 2023: 27")
                    period_parts = []
                    for p in (hist_series or [])[-10:]:
                        pn = (p.get("period_name") or "").strip()
                        v = p.get("value_int")
                        if pn and v is not None:
                            try:
                                period_parts.append(f"{pn}: {_fmt(int(v))}")
                            except Exception as e:
                                logger.debug("Optional validation step failed: %s", e)
                    if period_parts:
                        if len(period_parts) == 1:
                            # e.g. "Prior period (2023): 27."
                            p0 = period_parts[0]
                            name_part = p0.split(":", 1)[0].strip() if ":" in p0 else p0
                            val_part = p0.split(":", 1)[1].strip() if ":" in p0 else p0
                            hist_line = f" Prior period ({name_part}): {val_part}."
                        elif hist_min_i is not None and hist_max_i is not None and hist_min_i == hist_max_i:
                            periods_only = ", ".join((p.get("period_name") or "").strip() for p in (hist_series or [])[-10:] if (p.get("period_name") or "").strip())
                            hist_line = f" Prior periods ({periods_only}): {_fmt(int(hist_min_i))}."
                        else:
                            hist_line = f" Prior periods: {', '.join(period_parts)}."

                # Adjust quality slightly based on historical alignment
                quality = 0.5
                if (upr_in is True or upr_near is True) and not (rep_in is True or rep_near is True):
                    quality = 0.6
                elif (rep_in is True or rep_near is True) and not (upr_in is True or upr_near is True):
                    quality = 0.45
                elif rep_in is False and upr_in is False and hist_count:
                    quality = 0.45

                # Also mention suspected trend anomaly when historical latest exists
                trend_note = ""
                latest_hist = (hist_summary or {}).get("latest_value_int") if isinstance(hist_summary, dict) else None
                latest_period_name = (hist_summary or {}).get("latest_period_name") if isinstance(hist_summary, dict) else None
                try:
                    latest_hist_i = int(latest_hist) if latest_hist is not None else None
                except Exception as e:
                    logger.debug("latest_hist_i failed: %s", e)
                    latest_hist_i = None
                if latest_hist_i not in (None, 0):
                    try:
                        delta = (int(reported_int) - int(latest_hist_i)) / float(int(latest_hist_i))
                        if abs(delta) >= 0.5:
                            period_label = f"prior period {latest_period_name} " if (latest_period_name and str(latest_period_name).strip()) else "latest prior period "
                            trend_note = f" Reported value implies a {round(delta*100):.0f}% change vs {period_label}({_fmt(int(latest_hist_i))})."
                    except Exception as e:
                        logger.debug("trend_note failed: %s", e)
                        trend_note = ""

                current_period = (context.get("period_name") or "").strip()
                period_ctx = f" Current period reports {_fmt(reported_int)}" + (f" ({current_period})." if current_period else ".")

                upr_label = _upr_document_label(upr)
                # Data-driven conclusion: when UPR and prior periods agree, suggest reported may be wrong
                prior_values = [int(p.get("value_int")) for p in prior_series if p.get("value_int") is not None]
                prior_agrees_with_upr = (
                    upr_value_int is not None
                    and prior_values
                    and all(int(v) == int(upr_value_int) for v in prior_values)
                )
                if prior_agrees_with_upr and prior_series:
                    first_prior = prior_series[-1]  # chronologically last prior (e.g. 2023)
                    pn_prior = (first_prior.get("period_name") or "").strip()
                    conclusion = f" The reported value may be incorrect; {_fmt(int(upr_value_int))} (from {upr_label} and prior period {pn_prior}) may be correct. Please verify."
                else:
                    conclusion = " Please verify."

                return {
                    "verdict": "discrepancy",
                    "quality": quality,
                    "opinion": (
                        f"Quality estimate: {int(round(quality*100))}%.{period_ctx} {upr_label} shows {_fmt(int(upr_value_int))} for {keyword or 'this metric'}.{extra}{hist_line}{trend_note}{conclusion}"
                    ),
                    "claims": claims[:8],
                    "upr": upr,
                    "historical_summary": hist_summary,
                }

        if claims and matches_text and not text_conflicts:
            opinion = f"Quality estimate: 80%. The reported value {_fmt(reported_int)} matches the most relevant document evidence for {keyword or 'this metric'}."
            if hist_median is not None:
                opinion += f" Historical median across previous periods is {_fmt(hist_median)}."
            return {
                "verdict": "good",
                "quality": 0.8,
                "opinion": opinion,
                "claims": claims[:6],
                "upr": upr,
                "historical_summary": hist_summary,
            }

        if claims and matches_text and text_conflicts:
            other = [int(v) for v in claim_values if int(v) != int(reported_int)]
            other_preview = ", ".join(_fmt(v) for v in other[:3])
            return {
                "verdict": "discrepancy",
                "quality": 0.55,
                "opinion": (
                    f"Quality estimate: 55%. Some evidence supports {_fmt(reported_int)} for {keyword or 'this metric'}, "
                    f"but other evidence suggests different value(s) ({other_preview}). Please verify against the source documents."
                ),
                "claims": claims[:8],
                "upr": upr,
                "historical_summary": hist_summary,
            }

        if claims and (not matches_text):
            other_preview = ", ".join(_fmt(int(v)) for v in claim_values[:3])
            extra_hist = ""
            if hist_median is not None:
                extra_hist = f" Historical median across previous periods is {_fmt(hist_median)}."
            return {
                "verdict": "discrepancy",
                "quality": 0.4,
                "opinion": (
                    f"Quality estimate: 40%. The reported value {_fmt(reported_int)} does not match the extracted document evidence for {keyword or 'this metric'} "
                    f"(e.g. {other_preview}). This suggests a discrepancy or that the retrieved documents describe a different period/metric.{extra_hist}"
                ),
                "claims": claims[:8],
                "upr": upr,
                "historical_summary": hist_summary,
            }

        # No document claims found — check if historical data can provide validation
        if reported_int is not None and hist_values:
            hist_count = len(hist_values)
            matches_hist_exact = reported_int in hist_values
            exact_match_count = sum(1 for v in hist_values if v == reported_int)

            # Build a readable historical series line (e.g. "2022: 29, 2024: 29")
            period_parts = []
            for p in (hist_series or []):
                pn = (p.get("period_name") or "").strip()
                v = p.get("value_int")
                if pn and v is not None:
                    try:
                        period_parts.append(f"{pn}: {_fmt(int(v))}")
                    except Exception as e:
                        logger.debug("Optional validation step failed: %s", e)
            hist_line = ", ".join(period_parts) if period_parts else ""

            current_period = (context.get("period_name") or "").strip()
            metric_label = keyword or (label or "this metric")

            # Case 1: Reported value matches ALL historical values (very stable metric)
            if matches_hist_exact and exact_match_count == hist_count and hist_count >= 2:
                quality = 0.75
                return {
                    "verdict": "good",
                    "quality": quality,
                    "opinion": (
                        f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found, "
                        f"but the reported value {_fmt(reported_int)} for '{metric_label}' is consistent with "
                        f"all {hist_count} historical submissions ({hist_line}). "
                        f"The value has remained stable across all available periods, which supports its plausibility."
                    ),
                    "claims": [],
                    "upr": upr,
                    "historical_summary": hist_summary,
                }

            # Case 2: Reported value matches at least one historical value
            if matches_hist_exact:
                quality = 0.65
                return {
                    "verdict": "good",
                    "quality": quality,
                    "opinion": (
                        f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found, "
                        f"but the reported value {_fmt(reported_int)} for '{metric_label}' matches "
                        f"{exact_match_count} of {hist_count} historical submission(s) ({hist_line}). "
                        f"Historical consistency supports the plausibility of this value."
                    ),
                    "claims": [],
                    "upr": upr,
                    "historical_summary": hist_summary,
                }

            # Case 3: Value within historical range (min–max)
            if hist_median is not None and min(hist_values) <= reported_int <= max(hist_values):
                quality = 0.55
                return {
                    "verdict": "good",
                    "quality": quality,
                    "opinion": (
                        f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found, "
                        f"but the reported value {_fmt(reported_int)} for '{metric_label}' falls within "
                        f"the historical range ({_fmt(min(hist_values))}–{_fmt(max(hist_values))}) "
                        f"across {hist_count} period(s) ({hist_line}). Historical median is {_fmt(hist_median)}."
                    ),
                    "claims": [],
                    "upr": upr,
                    "historical_summary": hist_summary,
                }

            # Case 4: Value near historical median (within ±50%)
            if hist_median is not None and hist_median > 0:
                deviation = abs(reported_int - hist_median) / float(hist_median)
                if deviation <= 0.50:
                    quality = 0.45
                    return {
                        "verdict": "uncertain",
                        "quality": quality,
                        "opinion": (
                            f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found. "
                            f"The reported value {_fmt(reported_int)} for '{metric_label}' is "
                            f"{int(round(deviation * 100))}% away from the historical median ({_fmt(hist_median)}) "
                            f"across {hist_count} period(s) ({hist_line}). "
                            f"The value is plausible but cannot be confirmed without documentation."
                        ),
                        "claims": [],
                        "upr": upr,
                        "historical_summary": hist_summary,
                    }

            # Case 5: Value significantly deviates from historical data (>50% from median)
            if hist_median is not None and hist_median > 0:
                deviation = abs(reported_int - hist_median) / float(hist_median)
                direction = "increase" if reported_int > hist_median else "decrease"
                quality = 0.35
                return {
                    "verdict": "discrepancy",
                    "quality": quality,
                    "opinion": (
                        f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found. "
                        f"The reported value {_fmt(reported_int)} for '{metric_label}' represents a "
                        f"{int(round(deviation * 100))}% {direction} from the historical median ({_fmt(hist_median)}) "
                        f"across {hist_count} period(s) ({hist_line}). "
                        f"This significant deviation warrants verification with a supporting document."
                    ),
                    "claims": [],
                    "upr": upr,
                    "historical_summary": hist_summary,
                }

            # Case 6: Only one historical value to compare
            if hist_count == 1:
                latest_val = hist_values[0]
                latest_period = (hist_series[0].get("period_name") or "").strip() if hist_series else ""
                if reported_int == latest_val:
                    quality = 0.55
                    return {
                        "verdict": "good",
                        "quality": quality,
                        "opinion": (
                            f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found, "
                            f"but the reported value {_fmt(reported_int)} for '{metric_label}' matches "
                            f"the value from {latest_period or 'a prior period'} ({_fmt(latest_val)})."
                        ),
                        "claims": [],
                        "upr": upr,
                        "historical_summary": hist_summary,
                    }
                else:
                    change_pct = abs(reported_int - latest_val) / float(latest_val) * 100 if latest_val else 0
                    quality = 0.35
                    return {
                        "verdict": "uncertain",
                        "quality": quality,
                        "opinion": (
                            f"Quality estimate: {int(round(quality * 100))}%. No supporting documents were found. "
                            f"The reported value {_fmt(reported_int)} for '{metric_label}' differs by "
                            f"{int(round(change_pct))}% from {latest_period or 'the prior period'} ({_fmt(latest_val)}). "
                            f"Please supply a supporting document to verify the change."
                        ),
                        "claims": [],
                        "upr": upr,
                        "historical_summary": hist_summary,
                    }

        # No claims and no useful historical data
        return {
            "verdict": "uncertain",
            "quality": 0.20,
            "opinion": (
                f"Quality estimate: 20%. No supporting documents or historical data were found for "
                f"'{keyword or (label or 'this item')}', so the value cannot be validated. "
                "Please supply a supporting document (e.g., statute, official roster, annual report, or meeting minutes) to enable validation."
            ),
            "claims": [],
            "upr": upr,
            "historical_summary": hist_summary,
        }

    def _compute_suggestion(
        self,
        *,
        context: Dict[str, Any],
        evidence_chunks: List[Dict[str, Any]],
        historical: Optional[Dict[str, Any]],
        llm_json: Optional[Dict[str, Any]],
        heuristic: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute a suggested value (best-effort) from LLM output, document evidence, UPR KPI blocks, and/or historical series.
        Returned object is stored under evidence['suggestion'] and optionally surfaced in the UI.
        """
        def _clean_reason(raw: Any) -> str:
            s = str(raw or "").strip()
            if not s:
                return "Suggested by AI based on documents and historical data."
            if len(s) > 400:
                s = s[:400].rstrip()
            return s

        def _normalize_llm_value(v: Any) -> Any:
            # Allow: string, number, or list (for multi-choice). Reject huge/unsafe payloads.
            if v is None:
                return None
            if isinstance(v, str):
                s = v.strip()
                if not s or s.lower() == "null":
                    return None
                # Some models double-quote strings (e.g. "\"CHF\""). Unwrap.
                if (len(s) >= 2) and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
                    try:
                        # Prefer JSON unescape for double-quoted strings
                        if s[0] == '"':
                            unq = json.loads(s)
                            if isinstance(unq, str):
                                s = unq.strip()
                        else:
                            s = s[1:-1].strip()
                    except Exception as e:
                        logger.debug("strip failed: %s", e)
                        s = s[1:-1].strip()
                if not s or s.lower() == "null":
                    return None
                return s[:120].rstrip()
            if isinstance(v, (int, float)) and v == v:
                # Do not coerce to int here (some questions may be decimals)
                return v
            if isinstance(v, list):
                out: List[str] = []
                for item in v[:50]:
                    if item is None:
                        continue
                    s = str(item).strip()
                    if not s or s.lower() == "null":
                        continue
                    if (len(s) >= 2) and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
                        try:
                            if s[0] == '"':
                                unq = json.loads(s)
                                if isinstance(unq, str):
                                    s = unq.strip()
                            else:
                                s = s[1:-1].strip()
                        except Exception as e:
                            logger.debug("list item unquote failed: %s", e)
                            s = s[1:-1].strip()
                    if not s or s.lower() == "null":
                        continue
                    out.append(s[:80].rstrip())
                return out if out else None
            # Unsupported types
            return None

        def _normalize_choice_suggestion(raw: Any) -> Any:
            """
            Normalize a suggested choice value (single/multi) to the stored option value.
            For choice questions, the saved answer must be one of the option values (often a code like 'CHF'),
            not a display label like 'Swiss francs (CHF)'.
            """
            field_type = str(context.get("field_type_for_js") or "").strip().lower()
            if field_type not in ("single_choice", "multiple_choice"):
                return raw

            opts = context.get("choice_options")
            if not isinstance(opts, list) or not opts:
                return raw

            allowed_values: List[str] = []
            label_to_value: Dict[str, str] = {}
            for o in opts[:300]:
                if not isinstance(o, dict):
                    continue
                v = o.get("value")
                lbl = o.get("label")
                if v is None:
                    continue
                vv = str(v).strip()
                if not vv:
                    continue
                allowed_values.append(vv)
                if lbl is not None:
                    ll = str(lbl).strip().lower()
                    if ll and ll not in label_to_value:
                        label_to_value[ll] = vv

            allowed_set = set(allowed_values)

            def _one(val: Any) -> Optional[str]:
                if val is None:
                    return None
                s = str(val).strip()
                if not s or s.lower() == "null":
                    return None
                # Exact match
                if s in allowed_set:
                    return s
                # Case-insensitive match
                for av in allowed_values:
                    if s.lower() == av.lower():
                        return av
                # Common pattern: "Swiss francs (CHF)" -> CHF
                m = _PAREN_CODE_RE.search(s)
                if m:
                    code = (m.group(1) or "").strip()
                    if code in allowed_set:
                        return code
                    for av in allowed_values:
                        if code.lower() == av.lower():
                            return av
                # Substring contains a valid code (e.g. "CHF - Swiss francs")
                s_lo = s.lower()
                for av in allowed_values:
                    av_lo = av.lower()
                    if av_lo and (av_lo in s_lo):
                        return av
                # Label match
                hit = label_to_value.get(s.lower())
                if hit:
                    return hit
                # Label contained in suggestion
                for ll, vv in label_to_value.items():
                    if ll and ll in s_lo:
                        return vv
                return None

            if field_type == "single_choice":
                v = _one(raw)
                return v if v is not None else None

            # multiple_choice
            if isinstance(raw, list):
                out: List[str] = []
                for it in raw[:50]:
                    vv = _one(it)
                    if vv and vv not in out:
                        out.append(vv)
                return out if out else None
            else:
                # Accept single string and try to map; if we can't, reject.
                v = _one(raw)
                return [v] if v is not None else None

        def _normalize_llm_disagg(d: Any) -> Optional[Any]:
            if d is None:
                return None
            if isinstance(d, str):
                s = d.strip()
                if not s or s.lower() == "null":
                    return None
                try:
                    d = json.loads(s)
                except Exception as e:
                    logger.debug("json.loads failed: %s", e)
                    return None
            if not isinstance(d, dict) or not d:
                return None

            fmt = (context.get("suggestion_disagg_format") or "").strip().lower()
            if fmt == "indicator_mode_values":
                mode = d.get("mode")
                values = d.get("values")
                if not mode or not isinstance(values, dict):
                    return None
                # Keep as stored by entry form: {"mode": "...", "values": {...}}
                return {"mode": str(mode), "values": values}

            if fmt == "matrix_raw":
                # Entry form saves raw dict of cell_key -> value (+ optional metadata like _table).
                # If the model accidentally wraps as {"values": {...}}, unwrap.
                if set(d.keys()) <= {"mode", "values"} and isinstance(d.get("values"), dict):
                    d = d.get("values") or {}
                return d if isinstance(d, dict) and d else None

            # Unknown; do not accept arbitrary disagg suggestions.
            return None

        # 1) Prefer explicit LLM suggestion when present.
        #
        # NOTE: suggestions are stored into FormData.imputed_value (JSON). Many FormItems are numeric,
        # but some are categorical/textual (e.g., currency codes). So we must support non-numeric
        # suggestions (strings) as well.
        try:
            if isinstance(llm_json, dict):
                llm_val = _normalize_llm_value(llm_json.get("suggested_value"))
                llm_disagg = _normalize_llm_disagg(llm_json.get("suggested_disagg_data"))
                if llm_val is not None or llm_disagg is not None:
                    out = {
                        "reason": _clean_reason(llm_json.get("suggestion_reason") or llm_json.get("suggestion")),
                        "source": "llm",
                    }
                    if llm_val is not None:
                        # Keep legacy behavior for numeric strings
                        if isinstance(llm_val, str):
                            v_int = _parse_int_number(llm_val)
                            out["value"] = int(v_int) if v_int is not None and llm_val.strip().replace(",", "").isdigit() else llm_val
                        else:
                            out["value"] = llm_val
                    if llm_disagg is not None:
                        out["disagg_data"] = llm_disagg
                    # Normalize choice suggestions to stored option values when possible.
                    if "value" in out:
                        norm_choice = _normalize_choice_suggestion(out.get("value"))
                        if norm_choice is None:
                            # Don't suggest invalid option labels for choice questions.
                            out.pop("value", None)
                        else:
                            out["value"] = norm_choice
                    # Drop disaggregation suggestions for non-disaggregation items.
                    if context.get("suggestion_disagg_format") is None:
                        out.pop("disagg_data", None)
                    # If nothing left after normalization, no suggestion.
                    if ("value" not in out) and ("disagg_data" not in out):
                        return None
                    return out
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        # 2) Heuristic suggestion (UPR -> claims -> historical)
        suggested = None
        reason = None
        source = None

        # If heuristic already produced a suggested_value, reuse it
        try:
            if isinstance(heuristic, dict) and heuristic.get("suggested_value") is not None:
                suggested = int(heuristic.get("suggested_value"))
                reason = str(heuristic.get("suggestion_reason") or "").strip() or None
                source = "heuristic"
        except Exception as e:
            logger.debug("heuristic suggested failed: %s", e)
            suggested = None

        if suggested is None:
            upr = heuristic.get("upr") if isinstance(heuristic, dict) else None
            upr_val = None
            try:
                upr_val = _parse_int_number((upr or {}).get("value")) if isinstance(upr, dict) else None
            except Exception as e:
                logger.debug("upr_val parse failed: %s", e)
                upr_val = None
            if upr_val is not None:
                suggested = int(upr_val)
                reason = _upr_suggestion_reason(upr, int(upr_val))
                source = "upr"

        if suggested is None:
            try:
                label = context.get("form_item_label")
                keyword = _infer_primary_keyword(label) or ""
                claims = _extract_keyword_number_claims(
                    keyword=keyword,
                    evidence_chunks=evidence_chunks,
                    required_terms=_required_terms_for_claims(label, keyword),
                )
                claim_values = sorted({c.get("value") for c in claims if isinstance(c.get("value"), int)})
                if claim_values:
                    if len(claim_values) == 1:
                        suggested = int(claim_values[0])
                        reason = f"Document evidence repeatedly mentions {_format_int(int(suggested))} for {keyword or 'this metric'}."
                        source = "documents"
                    else:
                        suggested = int(_median_int([int(v) for v in claim_values]) or claim_values[0])
                        reason = f"Document evidence contains multiple values for {keyword or 'this metric'}; a typical value is {_format_int(int(suggested))}."
                        source = "documents"
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)

        if suggested is None:
            try:
                hist_summary = (historical or {}).get("summary") if isinstance(historical, dict) else None
                latest_val = (hist_summary or {}).get("latest_value_int") if isinstance(hist_summary, dict) else None
                if latest_val is not None:
                    suggested = int(latest_val)
                    latest_period_name = (hist_summary or {}).get("latest_period_name") if isinstance(hist_summary, dict) else None
                    if latest_period_name:
                        reason = f"Historical submissions suggest {_format_int(int(latest_val))} (most recent prior period: {latest_period_name})."
                    else:
                        reason = f"Historical submissions suggest {_format_int(int(latest_val))}."
                    source = "historical"
            except Exception as e:
                logger.debug("Optional validation step failed: %s", e)

        if suggested is None:
            return None

        # Do not "suggest" the same as reported value
        try:
            reported_int = _parse_int_number(context.get("value"))
            if reported_int is not None and int(reported_int) == int(suggested):
                return None
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)

        out: Dict[str, Any] = {
            "value": int(suggested),
            "reason": reason,
            "source": source,
        }
        # Attach UPR source metadata so the UI can show "which document/page" produced the suggestion.
        try:
            if source == "upr":
                upr = heuristic.get("upr") if isinstance(heuristic, dict) else None
                src = upr.get("source") if isinstance(upr, dict) and isinstance(upr.get("source"), dict) else None
                if src:
                    out["upr_source"] = src
        except Exception as e:
            logger.debug("Optional validation step failed: %s", e)
        return out

    def _build_prompt(self, *, context: Dict[str, Any], evidence_chunks: List[Dict[str, Any]]) -> str:
        # Keep this stable and explicit; output MUST be JSON.
        # Limit chunks to top 8 to prevent token overflow (finish_reason=length)
        limited_chunks = evidence_chunks[:8] if evidence_chunks else []

        # Build matrix-specific guidance if disagg_values present
        matrix_guidance = ""
        if context.get("disagg_values"):
            matrix_guidance = (
                "\nMATRIX/DISAGGREGATION DATA VALIDATION:\n"
                "The 'disagg_values' field contains individual breakdown values to validate.\n"
                "Look for tables, funding breakdowns, or budget allocations in the evidence.\n"
                "Common patterns in IFRC documents:\n"
                "- Strategic priorities (SP1-SP5): Climate, Disasters, Health, Migration, Values\n"
                "- EFs = Enabling Functions\n"
                "- Funding amounts may be in CHF, USD, or local currency\n"
                "- Values like '2M CHF' = 2,000,000; '500K' = 500,000\n"
                "Validate each breakdown value against evidence tables if found.\n\n"
            )

        # Build historical data section for the prompt
        historical_section = ""
        hist = context.get("historical")
        if isinstance(hist, dict) and hist.get("count", 0) > 0:
            # hist is the summary dict from _retrieve_historical_values
            hist_count = hist.get("count", 0)
            hist_min = hist.get("min")
            hist_max = hist.get("max")
            hist_median = hist.get("median")
            latest_period = hist.get("latest_period_name")
            latest_value = hist.get("latest_value_int")
            yoy = hist.get("yoy_change_ratio")

            hist_parts = [f"  - Data points: {hist_count} prior period(s)"]
            if hist_min is not None and hist_max is not None:
                if hist_min == hist_max:
                    hist_parts.append(f"  - All prior values: {hist_min:,}")
                else:
                    hist_parts.append(f"  - Range: {hist_min:,} – {hist_max:,}")
            if hist_median is not None:
                hist_parts.append(f"  - Median: {hist_median:,}")
            if latest_period and latest_value is not None:
                hist_parts.append(f"  - Most recent prior period: {latest_period} = {latest_value:,}")
            if yoy is not None:
                hist_parts.append(f"  - Year-over-year change ratio (latest two): {yoy:+.2%}")

            historical_section = (
                "\nHISTORICAL DATA (from prior submitted/approved periods for the same country and indicator):\n"
                + "\n".join(hist_parts) + "\n\n"
                "IMPORTANT RULES FOR USING HISTORICAL DATA:\n"
                "- Historical data is a strong plausibility signal. If the reported value is consistent with "
                "historical submissions (same or similar values), this significantly supports its validity.\n"
                "- If the value matches ALL prior periods exactly, confidence should be at least 0.65.\n"
                "- If the value falls within the historical range, confidence should be at least 0.50.\n"
                "- Only flag a discrepancy from historical data if the change is large (>50%) AND unexplained.\n"
                "- Do NOT say 'no evidence' when historical data exists — historical submissions ARE evidence.\n"
                "- When no documents are available but historical data supports the value, use verdict='good' "
                "with appropriate confidence (0.5–0.75 depending on how consistent the history is).\n\n"
            )

        # Build IFRC/UPR KPI reference section (structured evidence from imported documents metadata)
        upr_section = ""
        upr = context.get("upr_kpi")
        try:
            if isinstance(upr, dict) and (upr.get("value") is not None) and str(upr.get("value")).strip() != "":
                src = upr.get("source") if isinstance(upr.get("source"), dict) else {}
                title = (src.get("document_title") or src.get("document_filename") or "").strip()
                page = src.get("page_number")
                src_year = src.get("year")
                src_rtype = (src.get("report_type") or "").strip() if isinstance(src.get("report_type"), str) else None
                conf = src.get("confidence")
                conf_txt = ""
                try:
                    if conf is not None:
                        conf_txt = f" (confidence {int(round(float(conf) * 100))}%)"
                except Exception as e:
                    logger.debug("conf_txt failed: %s", e)
                    conf_txt = ""
                page_txt = f", p. {int(page)}" if isinstance(page, (int, float)) and int(page) > 0 else ""
                metric = (upr.get("metric") or "").strip() or "upr_kpi"
                year_txt = f"{int(src_year)}" if isinstance(src_year, (int, float)) and int(src_year) > 0 else None
                rtype_txt = src_rtype if src_rtype else None
                upr_section = (
                    "\nIFRC API / UPR KPI REFERENCE (structured KPI extracted from accessible IFRC/UPR documents):\n"
                    f"- Metric: {metric}\n"
                    f"- Value: {str(upr.get('value')).strip()}{conf_txt}\n"
                    + (f"- Reference period: {', '.join([x for x in [rtype_txt, year_txt] if x])}\n" if (rtype_txt or year_txt) else "")
                    + (f"- Source: {title}{page_txt}\n" if title or page_txt else "")
                    + "\n"
                    "IMPORTANT RULES FOR USING UPR KPI REFERENCE:\n"
                    "- Treat this as strong evidence when it matches the reported value.\n"
                    "- TIME ALIGNMENT: Only treat UPR KPI as a direct conflict if it applies to the SAME reporting year/period as the row.\n"
                    "- If the UPR KPI reference period differs from the row period, treat it as context only (do NOT flag a discrepancy on that basis alone).\n"
                    "- If UPR KPI conflicts with the reported value, prefer UPR KPI ONLY when the indicator definition AND reporting period clearly match.\n"
                    "- If UPR KPI matches the reported value and historical data is consistent, do NOT flag a discrepancy based on proxy metrics.\n\n"
                )
        except Exception as e:
            logger.debug("upr_section build failed: %s", e)
            upr_section = ""

        # Concept/definition alignment rules (prevents proxy comparisons)
        alignment_rules = (
            "\nCONCEPT / DEFINITION ALIGNMENT RULES:\n"
            "- Only compare the reported value to evidence that refers to the SAME concept as the form item label.\n"
            "- Do NOT infer one metric from another unless the evidence explicitly defines them as equivalent.\n"
            "- Example: Do NOT treat 'local units' as 'branches + sub-branches' unless the source explicitly states that local units are defined that way.\n"
            "- If evidence discusses a related-but-not-equivalent metric, use verdict='uncertain' (needs review) instead of 'discrepancy'.\n\n"
            "TIME ALIGNMENT RULES:\n"
            "- Prefer evidence that matches the row's reporting year/period.\n"
            "- If a document/quote clearly refers to a different year, do NOT treat it as a direct conflict.\n"
            "- When year alignment is unclear, lower confidence and prefer verdict='uncertain'.\n\n"
        )

        return (
            "Validate the reported value against the provided evidence.\n\n"
            "IMPORTANT: Evidence documents may be in any language (French, Spanish, Portuguese, Arabic, etc.). "
            "You MUST understand the content regardless of language and ALWAYS respond in English.\n\n"
            + matrix_guidance
            + historical_section +
            upr_section +
            alignment_rules +
            "Return ONLY a JSON object with this schema:\n"
            "{\n"
            '  \"verdict\": \"good\"|\"discrepancy\"|\"uncertain\",\n'
            '  \"confidence\": number between 0 and 1,\n'
            '  \"opinion_summary\": string (in English; 1-2 sentences; include the decision),\n'
            '  \"opinion_details\": string|null (in English; short multi-line bullets; include source details),\n'
            '  \"opinion\": string|null (legacy; same as opinion_summary),\n'
            '  \"suggested_value\": string|number|array|null (optional; for multi-select questions use an array of strings),\n'
            '  \"suggested_disagg_data\": object|null (optional; ONLY when context.suggestion_disagg_format indicates a disaggregation/matrix format),\n'
            '  \"suggestion_reason\": string|null (optional; short reason for suggested_value),\n'
            '  \"citations\": [\n'
            "    {\n"
            '      \"document_id\": number|null,\n'
            '      \"page_number\": number|null,\n'
            '      \"chunk_id\": number|null,\n'
            '      \"quote\": string (keep original language)\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- If evidence AND historical data are both insufficient, use verdict=uncertain.\n"
            "- If document evidence explicitly conflicts with the value, use discrepancy.\n"
            "- Historical consistency (same value across periods) is strong supporting evidence even without documents.\n"
            "- If the reported value is missing/blank AND you can infer a plausible value from evidence or history, you SHOULD include suggested_value + suggestion_reason.\n"
            "- If context.suggestion_disagg_format='indicator_mode_values', suggested_disagg_data must be {\"mode\": <string>, \"values\": <object>}.\n"
            "- If context.suggestion_disagg_format='matrix_raw', suggested_disagg_data must be a flat object of saved matrix cell keys to values (same structure as entry form hidden field field_value[form_item_id]).\n"
            "- If context.field_type_for_js is 'single_choice', suggested_value MUST be one of the option values in context.choice_options[].value (e.g. 'CHF'), NOT a label.\n"
            "- If context.field_type_for_js is 'multiple_choice', suggested_value MUST be an array of option values from context.choice_options[].value.\n"
            "- Keep opinion_summary concise (1-2 sentences), always in English.\n"
            "- opinion_details may be longer but should remain brief (max ~10 bullets).\n"
            "- For citations, preserve quotes in their original language.\n"
            "- IMPORTANT: Include ONLY evidence chunks that directly support or contradict the value. "
            "If no evidence is relevant (wrong country, wrong indicator, or no matching concept), return citations: []\n\n"
            f"Reported record context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"Evidence chunks ({len(limited_chunks)} of {len(evidence_chunks or [])}):\n{json.dumps(limited_chunks, ensure_ascii=False)}\n"
        )
