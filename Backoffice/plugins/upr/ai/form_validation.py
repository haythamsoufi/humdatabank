"""UPR-specific helpers for AI form-data validation.

Keeps Unified Plan/Report knowledge out of the core validation service:
item-kind detection, evidence-query hints, structured visual-block retrieval,
and comment short-circuit opinions.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from plugins.upr.ai.prompts import (
    get_upr_formdata_validation_prompt,
    is_upr_form_template,
)
from plugins.upr.ai.matrix_reading import (
    compare_upr_matrix_to_history,
    format_upr_historical_matrices_for_prompt,
    format_upr_matrix_reading_for_prompt,
    interpret_upr_matrix,
    people_history_magnitude_reason,
)
from plugins.upr.ai.assignment_review import (
    build_upr_assignment_review_pack,
    format_upr_assignment_review_for_prompt,
)

logger = logging.getLogger(__name__)

_BLANK_LABEL_RE = re.compile(r"^[\s\-–—_]*$")

_KIND_PEOPLE_TO_BE_REACHED = "people_to_be_reached"
_KIND_PEOPLE_REACHED = "people_reached"
_KIND_BILATERAL = "bilateral_support"
_KIND_FUNDING = "funding"
_KIND_COMMENTS = "comments"
_KIND_NS_KPIS = "ns_kpis"
_KIND_OTHER = "other"

_PLAN_TEMPLATE_IDS = frozenset({22, 24})
_REPORT_TEMPLATE_IDS = frozenset({23, 33})
_UPR_TEMPLATE_IDS = _PLAN_TEMPLATE_IDS | _REPORT_TEMPLATE_IDS


def upr_template_ids() -> frozenset:
    return _UPR_TEMPLATE_IDS


def _hay(context: Dict[str, Any]) -> str:
    parts = [
        context.get("form_item_label"),
        context.get("section_name"),
        context.get("subsection_name"),
        context.get("template_name"),
        context.get("upr_effective_label"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _template_id(context: Dict[str, Any]) -> Optional[int]:
    try:
        tid = context.get("template_id")
        return int(tid) if tid is not None and tid != "" else None
    except (TypeError, ValueError):
        return None


def is_blank_form_label(label: Optional[str]) -> bool:
    return not label or bool(_BLANK_LABEL_RE.match(str(label)))


def effective_upr_item_label(context: Dict[str, Any]) -> str:
    """Human label for retrieval/prompts when the form item is blank ('-')."""
    label = str(context.get("form_item_label") or "").strip()
    if not is_blank_form_label(label):
        return label
    parts = [
        str(context.get("subsection_name") or "").strip(),
        str(context.get("section_name") or "").strip(),
    ]
    joined = " / ".join(p for p in parts if p and not is_blank_form_label(p))
    return joined or "UPR form field"


def infer_upr_item_kind(context: Dict[str, Any]) -> str:
    """Classify a UPR form field so prompts and retrieval can special-case it."""
    if not is_upr_form_template(_template_id(context)):
        return _KIND_OTHER
    text = _hay(context)
    item_type = str(context.get("form_item_type") or "").strip().lower()
    field_js = str(context.get("field_type_for_js") or "").strip().lower()

    if "comment" in text:
        return _KIND_COMMENTS
    if item_type == "question" and field_js in ("textarea", "text", "long_text", "rich_text") and not context.get(
        "disagg_values"
    ):
        if "comment" in text or "please include" in text:
            return _KIND_COMMENTS

    if "supporting bilaterally" in text or "bilateral" in text or "participating national" in text:
        return _KIND_BILATERAL
    if "people to be reached" in text or "to be reached" in text or "longer term programme" in text:
        return _KIND_PEOPLE_TO_BE_REACHED
    if "people reached" in text:
        return _KIND_PEOPLE_REACHED
    if "emergency appeal" in text and _template_id(context) in _PLAN_TEMPLATE_IDS:
        return _KIND_PEOPLE_TO_BE_REACHED
    if any(k in text for k in ("funding", "expenditure", "budget", "chf")):
        return _KIND_FUNDING
    if any(k in text for k in ("volunteer", "staff", "branch", "local unit")):
        return _KIND_NS_KPIS
    # Funding matrices on Unified Country Plan often have a blank item label ("-")
    # under a "Funding Requirements for …" subsection.
    if context.get("disagg_values") and (
        "funding" in (context.get("section_name") or "").lower()
        or "funding" in (context.get("subsection_name") or "").lower()
    ):
        return _KIND_FUNDING
    return _KIND_OTHER


def is_upr_comment_field(context: Dict[str, Any]) -> bool:
    return infer_upr_item_kind(context) == _KIND_COMMENTS


def upr_comment_heuristic(context: Dict[str, Any]) -> Dict[str, Any]:
    """Stable opinion for UPR comment fields — not numeric validation."""
    raw = context.get("value")
    text = str(raw or "").strip()
    extra_keys = {
        "claims": [],
        "upr": None,
        "historical_summary": {"count": 0},
    }
    if not text or text.lower() in ("none", "null", "-", "n/a"):
        return {
            "verdict": "uncertain",
            "quality": 0.6,
            "opinion": (
                "This is a free-text comments field, not a numeric UPR indicator. "
                "No comment was entered, so there is nothing to validate against documents."
            ),
            **extra_keys,
        }
    preview = text if len(text) <= 180 else (text[:177] + "...")
    return {
        "verdict": "good",
        "quality": 0.8,
        "opinion": (
            "This is a free-text comment for validators, not a numeric indicator. "
            "It is not checked against documents or historical numbers. "
            f"Comment: {preview}"
        ),
        **extra_keys,
    }


def visual_block_types_for_kind(kind: str, *, template_id: Optional[int] = None) -> List[str]:
    """Which UPR visual-block types to fetch for this field."""
    if kind == _KIND_PEOPLE_TO_BE_REACHED:
        return ["people_to_be_reached", "people_reached"]
    if kind == _KIND_PEOPLE_REACHED:
        return ["people_reached", "people_to_be_reached"]
    if kind == _KIND_BILATERAL:
        return ["pns_bilateral_support", "funding_requirements"]
    if kind == _KIND_FUNDING:
        return ["funding_requirements", "financial_overview"]
    if kind == _KIND_NS_KPIS:
        return ["in_support_kpis"]
    if kind == _KIND_COMMENTS:
        return []
    if template_id in _PLAN_TEMPLATE_IDS:
        return ["people_to_be_reached", "funding_requirements", "pns_bilateral_support"]
    if template_id in _REPORT_TEMPLATE_IDS:
        return ["people_reached", "financial_overview", "pns_bilateral_support"]
    return []


def upr_evidence_query_hint(context: Dict[str, Any]) -> str:
    """Extra query terms so vector search prefers Unified Plan/Report evidence."""
    kind = infer_upr_item_kind(context)
    label = effective_upr_item_label(context)
    bits = ["Unified Plan", "UPL", "INP"]
    if kind == _KIND_PEOPLE_TO_BE_REACHED:
        bits.extend(["people to be reached", label])
    elif kind == _KIND_PEOPLE_REACHED:
        bits.extend(["people reached", label])
    elif kind == _KIND_BILATERAL:
        bits.extend(["bilateral support", "participating national societies", label])
    elif kind == _KIND_FUNDING:
        bits.extend(["funding requirements CHF", label])
    elif kind == _KIND_NS_KPIS:
        bits.extend(["volunteers staff branches", "in support of", label])
    elif kind != _KIND_COMMENTS:
        bits.append(label)
    # Dedup while preserving order
    seen = set()
    out: List[str] = []
    for b in bits:
        s = str(b or "").strip()
        key = s.lower()
        if not s or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return " ".join(out)


def retrieve_upr_visual_reference(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetch structured UPR visual blocks relevant to this form field."""
    if not is_upr_form_template(_template_id(context)):
        return None
    if not context.get("country_id"):
        return None
    kind = infer_upr_item_kind(context)
    block_types = visual_block_types_for_kind(kind, template_id=_template_id(context))
    if not block_types:
        return None
    try:
        from plugins.upr.ai.data_retrieval import get_upr_visual_blocks

        prefer_year = None
        try:
            if context.get("period_year") is not None:
                prefer_year = int(context["period_year"])
        except (TypeError, ValueError):
            prefer_year = None
        result = get_upr_visual_blocks(
            country_identifier=int(context["country_id"]),
            block_types=block_types,
            prefer_year=prefer_year,
        )
        if not isinstance(result, dict) or not result.get("success"):
            return None
        blocks = result.get("blocks") or []
        if not blocks:
            return None
        return {"blocks": blocks, "count": len(blocks)}
    except Exception as e:
        logger.debug("retrieve_upr_visual_reference failed: %s", e)
        return None


def upr_visuals_as_evidence_chunks(upr_visuals: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn structured visual blocks into evidence-chunk dicts for the LLM."""
    if not isinstance(upr_visuals, dict):
        return []
    chunks: List[Dict[str, Any]] = []
    for block in upr_visuals.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        src = block.get("source") if isinstance(block.get("source"), dict) else {}
        payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
        renderable = {"block": block.get("block"), **payload}
        if block.get("year") and not isinstance(renderable.get("upr_context"), dict):
            renderable["upr_context"] = {"year": block.get("year")}
        try:
            from plugins.upr.ai.visual_chunking import block_to_embedding_text
            content = block_to_embedding_text(renderable) or ""
        except Exception:
            try:
                content = json.dumps(renderable, ensure_ascii=False)
            except (TypeError, ValueError):
                content = str(payload)
        chunks.append(
            {
                "chunk_id": src.get("chunk_id"),
                "document_id": src.get("document_id"),
                "document_title": src.get("document_title"),
                "document_filename": src.get("document_filename"),
                "page_number": src.get("page_number"),
                "section_title": f"UPR visual: {block.get('block')}",
                "score": 1.0,
                "source": "api",
                "is_system_document": False,
                "is_api_import": True,
                "content": (content or "")[:1500],
            }
        )
    return chunks


def apply_upr_validation_context(
    context: Dict[str, Any],
    *,
    sources_cfg: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Enrich validation context when the assignment is a UPR form.

    Always adds kind/label/prompt metadata. Structured visual-block retrieval
    runs when UPR documents are in the source selection (or sources are unset).
    """
    if not isinstance(context, dict):
        return context
    if not is_upr_form_template(context.get("template_id")):
        return context

    out = dict(context)
    out["upr_form"] = True
    out["upr_effective_label"] = effective_upr_item_label(out)
    out["upr_item_kind"] = infer_upr_item_kind(out)
    if is_upr_comment_field(out):
        out["upr_skip_historical"] = True

    include_upr_docs = sources_cfg is None or bool(sources_cfg.get("upr_documents", False))
    if include_upr_docs:
        visuals = retrieve_upr_visual_reference(out)
        if visuals:
            out["upr_visuals"] = visuals
    reading = interpret_upr_matrix(out)
    if reading:
        out["upr_matrix_reading"] = reading
        preview = reading.get("value_preview")
        if preview:
            out["upr_value_preview"] = preview
        # Flags / PNS ticks are not comparable as a single historical *total*,
        # but cell-level history must still be retrieved and compared.
    return out


def attach_upr_assignment_review_context(
    context: Dict[str, Any],
    aes: Any = None,
) -> Dict[str, Any]:
    """Attach the assignment-level UPR review pack (comment, emergencies, IFRC completeness)."""
    if not isinstance(context, dict) or not context.get("upr_form"):
        return context
    if isinstance(context.get("upr_assignment_review"), dict):
        return context
    pack = None
    cache_key = f"upr_assignment_review_{getattr(aes, 'id', None) or context.get('submission_id')}"
    try:
        from flask import g, has_request_context
        if has_request_context():
            pack = getattr(g, cache_key, None)
    except Exception:
        pack = None
    if pack is None and aes is not None:
        try:
            pack = build_upr_assignment_review_pack(aes)
        except Exception:
            logger.debug("upr assignment review pack failed", exc_info=True)
            pack = None
        try:
            from flask import g, has_request_context
            if pack is not None and has_request_context():
                setattr(g, cache_key, pack)
        except Exception:
            pass
    if pack:
        context["upr_assignment_review"] = pack
        comment = str(pack.get("comment_text") or "").strip()
        if comment and not context.get("upr_assignment_comment"):
            context["upr_assignment_comment"] = comment[:1500]
    return context


def attach_upr_historical_matrix_context(
    context: Dict[str, Any],
    historical: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Interpret prior-assignment matrices and attach a like-for-like comparison."""
    if not isinstance(context, dict) or not context.get("upr_form"):
        return historical
    if not isinstance(historical, dict):
        return historical
    kind = context.get("upr_item_kind")
    current = context.get("upr_matrix_reading") if isinstance(context.get("upr_matrix_reading"), dict) else None
    series = historical.get("series") if isinstance(historical.get("series"), list) else []
    hist_entries: List[Dict[str, Any]] = []
    compact: List[Dict[str, Any]] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        disagg = row.get("disagg_values")
        if not isinstance(disagg, dict) or not disagg:
            continue
        reading = interpret_upr_matrix({
            "upr_item_kind": kind,
            "period_year": row.get("period_year"),
            "period_name": row.get("period_name"),
            "section_name": context.get("section_name"),
            "subsection_name": context.get("subsection_name"),
            "disagg_values": disagg,
        })
        if not reading:
            continue
        row["upr_matrix_reading"] = reading
        hist_entries.append({
            "period_name": row.get("period_name"),
            "period_year": row.get("period_year"),
            "reading": reading,
        })
        compact.append({
            "period_name": row.get("period_name"),
            "value_role": reading.get("value_role"),
            "value_preview": reading.get("value_preview"),
            "grand_total": reading.get("grand_total"),
            "by_sp": reading.get("by_sp"),
            "by_programme": reading.get("by_programme"),
            "by_actor": reading.get("by_actor"),
            "nonzero_cells": (reading.get("nonzero_cells") or [])[:15],
        })
        row.pop("disagg_values", None)
    if compact:
        context["upr_historical_matrices"] = compact
    if current and hist_entries:
        context["upr_historical_comparison"] = compare_upr_matrix_to_history(current, hist_entries)
    return historical


def _upr_scale_change_reason(
    context: Dict[str, Any],
    historical: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    comparison = context.get("upr_historical_comparison")
    if isinstance(comparison, dict) and comparison.get("unit_or_scale_change"):
        for note in comparison.get("notes") or []:
            if isinstance(note, dict) and note.get("reason"):
                return str(note["reason"])
        return (
            "A prior assignment stored people or CHF quantities while the current grid "
            "collapsed to tiny cells (or the reverse)."
        )
    return people_history_magnitude_reason(context, historical)


def upr_matrix_history_heuristic(
    context: Dict[str, Any],
    historical: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Flag a discrepancy when this matrix's units/scale flipped versus a prior assignment."""
    reason = _upr_scale_change_reason(context, historical)
    if not reason:
        return None
    hist_summary = None
    hist_obj = historical if isinstance(historical, dict) else context.get("historical")
    if isinstance(hist_obj, dict):
        hist_summary = hist_obj.get("summary") if isinstance(hist_obj.get("summary"), dict) else hist_obj
    return {
        "verdict": "discrepancy",
        "quality": 0.78,
        "opinion": (
            f"Quality estimate: 78%. Unit/scale change versus a prior matrix: {reason} "
            "This is a discrepancy unless a comment on this assignment explains a form redesign. "
            "Do not treat internal consistency of the current grid as confirmation."
        ),
        "claims": [],
        "upr": None,
        "historical_summary": hist_summary,
    }


def apply_upr_matrix_history_guardrail(
    verdict: Optional[str],
    confidence: Any,
    opinion_text: Optional[str],
    context: Dict[str, Any],
    historical: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Any, Optional[str]]:
    """Override an LLM 'good' when people/CHF history collapsed to tiny current cells."""
    reason = _upr_scale_change_reason(context, historical)
    if not reason:
        return verdict, confidence, opinion_text
    if str(verdict or "").strip().lower() != "good":
        return verdict, confidence, opinion_text
    combined = str(opinion_text or "").lower()
    if any(token in combined for token in ("redesign", "form change", "template change", "now stores flags")):
        return verdict, confidence, opinion_text
    try:
        conf = max(float(confidence or 0.0), 0.75)
    except (TypeError, ValueError):
        conf = 0.75
    opinion = (
        f"Decision: Discrepancy. {reason} "
        "Do not accept the entry only because the current grid is internally consistent "
        "or matches the matrix decode. Confirm whether people/CHF figures were omitted."
    )
    return "discrepancy", conf, opinion


def upr_validation_prompt_section(context: Dict[str, Any]) -> str:
    if not context.get("upr_form") and not is_upr_form_template(context.get("template_id")):
        return ""
    return get_upr_formdata_validation_prompt(context)


def format_upr_visuals_for_prompt(context: Dict[str, Any]) -> str:
    visuals = context.get("upr_visuals")
    if not isinstance(visuals, dict):
        return ""
    blocks = visuals.get("blocks") or []
    if not blocks:
        return ""
    lines = [
        "\nSTRUCTURED UPR VISUAL BLOCKS (extracted from Unified Plan/Report PDFs; prefer these over Annual Report narrative):\n"
    ]
    for block in blocks[:6]:
        if not isinstance(block, dict):
            continue
        src = block.get("source") if isinstance(block.get("source"), dict) else {}
        title = (src.get("document_title") or src.get("document_filename") or "UPR document").strip()
        page = src.get("page_number")
        page_txt = f", p. {int(page)}" if isinstance(page, (int, float)) and int(page) > 0 else ""
        year = block.get("year")
        year_txt = f" year={int(year)}" if isinstance(year, (int, float)) and year else ""
        conf = block.get("confidence")
        conf_txt = ""
        try:
            if conf is not None:
                conf_txt = f" confidence={int(round(float(conf) * 100))}%"
        except (TypeError, ValueError):
            conf_txt = ""
        payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
        renderable = {"block": block.get("block"), **payload}
        if block.get("year") and not isinstance(renderable.get("upr_context"), dict):
            renderable["upr_context"] = {"year": block.get("year")}
        try:
            from plugins.upr.ai.visual_chunking import block_to_embedding_text
            payload_txt = block_to_embedding_text(renderable) or json.dumps(payload, ensure_ascii=False)
        except Exception:
            try:
                payload_txt = json.dumps(payload, ensure_ascii=False)
            except (TypeError, ValueError):
                payload_txt = str(payload)
        if len(payload_txt) > 1500:
            payload_txt = payload_txt[:1497] + "..."
        lines.append(
            f"- block={block.get('block')}{year_txt}{conf_txt} source={title}{page_txt}\n{payload_txt}\n"
        )
    lines.append(
        "If a visual block year differs from the row period, use it as context only (not a direct conflict).\n"
    )
    return "".join(lines)


__all__ = [
    "apply_upr_validation_context",
    "apply_upr_matrix_history_guardrail",
    "attach_upr_assignment_review_context",
    "attach_upr_historical_matrix_context",
    "effective_upr_item_label",
    "format_upr_assignment_review_for_prompt",
    "format_upr_historical_matrices_for_prompt",
    "format_upr_matrix_reading_for_prompt",
    "format_upr_visuals_for_prompt",
    "infer_upr_item_kind",
    "is_upr_comment_field",
    "is_upr_form_template",
    "retrieve_upr_visual_reference",
    "upr_comment_heuristic",
    "upr_evidence_query_hint",
    "upr_matrix_history_heuristic",
    "upr_template_ids",
    "upr_validation_prompt_section",
    "upr_visuals_as_evidence_chunks",
    "visual_block_types_for_kind",
]
