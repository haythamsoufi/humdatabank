"""UI payload builders for AI validation opinions and suggestions."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from flask import current_app

from app.services.ai.validation.parsers import (
    _PAREN_CODE_RE,
    _YEAR_RE,
    _extract_keyword_number_claims,
    _format_int,
    _infer_primary_keyword,
    _is_blankish_value,
    _median_int,
    _parse_int_number,
    _parse_year_from_period,
)
from app.services.ai.validation.upr_rules import (
    _required_terms_for_claims,
    _upr_document_label,
    _upr_suggestion_reason,
)

logger = logging.getLogger(__name__)

def build_opinion_ui(
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


def compute_suggestion(
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
    # NOTE: scalar suggestions are stored into FormData.imputed_value. Many FormItems are numeric,
    # but some are categorical/textual (e.g., currency codes). So we must support non-numeric
    # suggestions (strings) as well. Matrix/disaggregation suggestions use imputed_disagg_data.
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
