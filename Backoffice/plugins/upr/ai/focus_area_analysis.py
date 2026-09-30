"""
Deterministic fast path for Unified Plans focus-area review prompts.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from flask import current_app
from flask_babel import gettext as _

from app.utils.api_helpers import service_error
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


_UNIFIED_PLAN_FOCUS_REVIEW_RE = re.compile(
    r"\b("
    r"unified\s+plans?|"
    r"review\s+all\s+unified\s+plans?|"
    r"upl[-\s]?\d{4}|"
    r"\binp\b"
    r")\b",
    re.IGNORECASE,
)


def _is_unified_plan_focus_review_query(query: str) -> bool:
    """
    Detect broad, inventory-style Unified Plan review prompts that ask for
    area tagging + gaps + simple counts/patterns across many plans.
    """
    if not query or not isinstance(query, str):
        return False
    q = str(query).strip().lower()
    if not q:
        return False
    if not _UNIFIED_PLAN_FOCUS_REVIEW_RE.search(q):
        return False
    focus_terms = ("cash", "cea", "livelihood", "social protection")
    has_focus = sum(1 for t in focus_terms if t in q) >= 2
    asks_for_aggregate = any(
        p in q for p in ("review all", "identify which", "simple counts", "key gaps", "patterns", "trends", "none of these")
    )
    return bool(has_focus and asks_for_aggregate)


def run_unified_plans_focus_fastpath(
    *,
    query: str,
    language: str = "en",
    on_step_callback: Optional[Callable[[str], None]] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    force_run: bool = False,
    tools_registry: Any,
    client: Any,
    model: str,
    provider: str,
) -> Optional[Dict[str, Any]]:
    """
    Deterministic fast path for "review all Unified Plans by focus areas" prompts.
    Runs one aggregated tool call and returns a concise markdown answer.
    """
    if not force_run and not _is_unified_plan_focus_review_query(query):
        return None
    try:
        tool_defs = tools_registry.get_tool_definitions_openai() or []
        tool_names = {
            str((t.get("function") or {}).get("name") or "").strip()
            for t in tool_defs
            if isinstance(t, dict)
        }
        if "analyze_unified_plans_focus_areas" not in tool_names:
            return None
    except Exception as e:
        logger.debug("Unified plans fastpath: tool check failed: %s", e)
        return None

    if callable(on_step_callback):
        try:
            on_step_callback(_("Reviewing Unified Plans…"))
        except Exception as e:
            logger.debug("Unified plans fastpath: on_step_callback failed: %s", e)

    requested_areas = ["cash", "cea", "livelihoods", "social_protection"]
    requested_limit = int(current_app.config.get("AI_UNIFIED_PLANS_REVIEW_LIMIT", 500))
    if isinstance(tool_args, dict):
        raw_areas = tool_args.get("areas")
        if isinstance(raw_areas, list):
            normalized_areas = [str(a).strip() for a in raw_areas if str(a).strip()]
            if normalized_areas:
                requested_areas = normalized_areas
        raw_limit = tool_args.get("limit")
        try:
            if raw_limit is not None:
                requested_limit = max(1, int(raw_limit))
        except (TypeError, ValueError):
            pass

    try:
        tool_result = tools_registry.execute_tool(
            "analyze_unified_plans_focus_areas",
            areas=requested_areas,
            limit=requested_limit,
        )
    except Exception as e:
        tool_result = service_error('An error occurred.', result={})

    if not isinstance(tool_result, dict) or not tool_result.get("success"):
        return None
    result = tool_result.get("result") if isinstance(tool_result, dict) else None
    if not isinstance(result, dict):
        return None

    plans = result.get("plans") if isinstance(result.get("plans"), list) else []
    countries_grouped = result.get("countries_grouped") if isinstance(result.get("countries_grouped"), list) else []
    latest_by_country = result.get("most_recent_plan_per_country") if isinstance(result.get("most_recent_plan_per_country"), list) else []
    counts = result.get("counts_by_area") if isinstance(result.get("counts_by_area"), dict) else {}
    analyzed = int(result.get("plans_analyzed") or len(plans))
    total = int(result.get("total_plans") or analyzed)
    countries_matched = int(result.get("countries_with_matches") or len(countries_grouped))
    countries_total = int(result.get("total_countries_considered") or countries_matched)
    excluded_no_mentions = int(result.get("plans_excluded_no_target_areas") or result.get("plans_with_no_target_areas") or max(0, total - analyzed))

    _AREA_LABELS: Dict[str, str] = {
        "cash": "Cash",
        "cea": "CEA",
        "livelihoods": "Livelihoods",
        "social_protection": "Social Protection",
    }

    def _area_key_to_label(key: str) -> str:
        return _AREA_LABELS.get(key, key.replace("_", " ").title())

    def _compact_plan_for_llm(p: Dict[str, Any]) -> Dict[str, Any]:
        area_details = p.get("area_details") if isinstance(p.get("area_details"), dict) else {}
        compact_area_details: Dict[str, Any] = {}
        for k, v in area_details.items():
            if not isinstance(v, dict):
                continue
            compact_area_details[_area_key_to_label(k)] = {
                "matched_terms": (v.get("matched_terms") or [])[:4],
                "activity_examples": (v.get("activity_examples") or [])[:2],
                "evidence_chunks": v.get("evidence_chunks"),
            }
        raw_areas = (p.get("areas_mentioned") or [])[:6]
        return {
            "country": p.get("document_country_name") or p.get("document_country_iso3"),
            "plan_year": p.get("plan_year"),
            "plan_title": p.get("document_title") or p.get("document_filename"),
            "document_url": p.get("document_url"),
            "areas_mentioned": [_area_key_to_label(a) for a in raw_areas],
            "area_details": compact_area_details,
        }

    # Use most-recent plan per country for the table to avoid duplicating
    # countries across multiple years (each country shown once with its latest plan).
    table_source = latest_by_country if latest_by_country else plans
    det_table_lines = [
        "| Country | Plan Year | Plan | Areas Mentioned | Example Activities |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in table_source:
        if not isinstance(p, dict):
            continue
        country = str(
            p.get("country_name")
            or p.get("document_country_name")
            or p.get("document_country_iso3")
            or "Unknown"
        ).strip()
        year = str(p.get("plan_year") or "-")
        title = str(p.get("document_title") or p.get("document_filename") or "Untitled").strip()
        url = str(p.get("document_url") or "").strip()
        areas = p.get("areas_mentioned") if isinstance(p.get("areas_mentioned"), list) else []
        details = p.get("area_details") if isinstance(p.get("area_details"), dict) else {}
        examples: List[str] = []
        for a in areas[:2]:
            d = details.get(a) if isinstance(details, dict) else {}
            ex = d.get("activity_examples") if isinstance(d, dict) and isinstance(d.get("activity_examples"), list) else []
            if ex:
                examples.append(str(ex[0])[:80])
        areas_txt = ", ".join([_area_key_to_label(str(x)) for x in areas]) if areas else "-"
        examples_txt = " | ".join(examples) if examples else "-"
        link_title = f"[{title}]({url})" if url else title
        det_table_lines.append(f"| {country} | {year} | {link_title} | {areas_txt} | {examples_txt} |")
    deterministic_table = "\n".join(det_table_lines)

    compact_country_groups: List[Dict[str, Any]] = []
    for c in countries_grouped[:40]:
        if not isinstance(c, dict):
            continue
        c_plans = c.get("plans") if isinstance(c.get("plans"), list) else []
        grp_counts_raw = c.get("counts_by_area") if isinstance(c.get("counts_by_area"), dict) else {}
        compact_country_groups.append(
            {
                "country_name": c.get("country_name"),
                "country_iso3": c.get("country_iso3"),
                "plans_count": c.get("plans_count"),
                "counts_by_area": {_area_key_to_label(k): v for k, v in grp_counts_raw.items()},
                "plans": [_compact_plan_for_llm(p) for p in c_plans[:4] if isinstance(p, dict)],
            }
        )
    labeled_counts = {_area_key_to_label(k): v for k, v in (counts or {}).items()}
    synthesis_payload: Dict[str, Any] = {
        "query": query,
        "summary": result.get("summary"),
        "counts_by_area": labeled_counts,
        "plans_analyzed_with_mentions": analyzed,
        "total_plans_considered": total,
        "countries_grouped": compact_country_groups,
        "most_recent_plan_per_country": latest_by_country[:40],
        "recommended_follow_up_actions": result.get("recommended_follow_up_actions") or [],
        "excluded_no_target_areas": int(result.get("plans_excluded_no_target_areas") or result.get("plans_with_no_target_areas") or 0),
        "countries_with_matches": int(countries_matched),
        "total_countries_considered": int(countries_total),
    }

    answer: str = ""
    llm_synthesis_used = False
    llm_synthesis_error: Optional[str] = None
    llm_synthesis_started_at = time.time()
    llm_prompt_chars = 0
    llm_input_tokens: Optional[int] = None
    llm_output_tokens: Optional[int] = None
    llm_finish_reason: Optional[str] = None
    llm_attempts: List[Dict[str, Any]] = []

    def _build_synthesis_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    f"You are an IFRC analysis assistant. Respond in {language}. "
                    "A complete markdown table of ALL matched plans has already been generated. "
                    "Your task is to produce ONLY the analysis section - do NOT generate a table. "
                    "Use country-first framing and compare plan years when multiple years exist. "
                    "Do NOT include a Sources or References section. "
                    "Do not mention tool names, internal metadata, or implementation details."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Based on these Unified Plan focus-area results, write an analysis section. "
                    "The complete plans table is already shown to the user - do NOT produce a table. "
                    "Include: (1) overall patterns across areas, (2) country-grouped insights with "
                    "notable examples, (3) key gaps and areas for attention, "
                    "(4) practical recommended follow-up queries. "
                    "Keep the analysis concise but insightful (under 400 words).\n\n"
                    + json.dumps(payload, ensure_ascii=False, default=str)
                ),
            },
        ]

    def _reduced_payload_for_retry() -> Dict[str, Any]:
        return {
            "query": query,
            "summary": result.get("summary"),
            "counts_by_area": labeled_counts,
            "plans_analyzed_with_mentions": analyzed,
            "total_plans_considered": total,
            "recommended_follow_up_actions": (result.get("recommended_follow_up_actions") or [])[:4],
            "excluded_no_target_areas": int(result.get("plans_excluded_no_target_areas") or result.get("plans_with_no_target_areas") or 0),
            "countries_with_matches": int(countries_matched),
            "total_countries_considered": int(countries_total),
        }

    payload_attempts = [synthesis_payload, _reduced_payload_for_retry()]
    max_tokens_attempt1 = int(current_app.config.get("AI_UNIFIED_FASTPATH_MAX_COMPLETION_TOKENS", 4000))
    max_tokens_attempt2 = int(current_app.config.get("AI_UNIFIED_FASTPATH_RETRY_MAX_COMPLETION_TOKENS", 3000))
    for idx, payload in enumerate(payload_attempts, start=1):
        try:
            synth_messages = _build_synthesis_messages(payload)
            prompt_chars = sum(len(str(m.get("content") or "")) for m in synth_messages)
            resp = client.chat.completions.create(
                model=model,
                messages=synth_messages,
                max_completion_tokens=max_tokens_attempt1 if idx == 1 else max_tokens_attempt2,
            )
            local_answer = str((resp.choices[0].message.content or "")).strip()
            local_finish_reason = str((resp.choices[0].finish_reason or "")).strip() or None
            usage = getattr(resp, "usage", None)
            local_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else None
            local_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else None
            llm_attempts.append(
                {
                    "attempt": idx,
                    "prompt_chars": int(prompt_chars),
                    "prompt_tokens": local_in,
                    "completion_tokens": local_out,
                    "finish_reason": local_finish_reason,
                    "answer_chars": int(len(local_answer or "")),
                }
            )
            llm_prompt_chars = int(prompt_chars)
            llm_input_tokens = local_in
            llm_output_tokens = local_out
            llm_finish_reason = local_finish_reason

            if local_answer:
                answer = local_answer
                llm_synthesis_used = True
                break
            llm_synthesis_error = "empty_content"
            logger.warning("Unified plans fastpath LLM synthesis attempt %s returned empty content.", idx)
        except Exception as e:
            llm_synthesis_error = str(e)
            llm_attempts.append({"attempt": idx, "error": "Synthesis failed."})
            logger.warning("Unified plans fastpath LLM synthesis attempt %s failed: %s", idx, e)
            continue

    table_count = len([p for p in table_source if isinstance(p, dict)])
    coverage_header = (
        f"Coverage: **{analyzed}/{total} plans** matched, "
        f"**{countries_matched}/{countries_total} countries** with at least one match; "
        f"**{excluded_no_mentions}** plans excluded for no target-area mentions."
        + (f"  Table shows most recent plan per country ({table_count} rows)." if latest_by_country else "")
    )
    # Built dynamically (not hardcoded to the 4 built-in areas): "areas" can be any
    # free-text theme (see tool_specs.py), so counts must reflect whatever was actually
    # requested/analyzed, otherwise a custom-area query (e.g. "migration", "climate")
    # would show a meaningless "Cash: 0 | CEA: 0 | ..." line instead of its own counts.
    if counts:
        counts_parts = " | ".join(f"{_area_key_to_label(k)}: {int(v or 0)}" for k, v in counts.items())
        area_counts_line = f"\n\nCounts - {counts_parts} ({analyzed} plans analysed)"
    else:
        area_counts_line = ""

    quality_warnings: List[str] = []
    if total > 0 and analyzed < total * 0.25:
        quality_warnings.append(
            f"Low match rate ({analyzed}/{total} plans). "
            "The semantic similarity thresholds may be too strict, or the documents may use different terminology."
        )
    zero_areas = [k for k in (counts or {}) if int(counts.get(k) or 0) == 0]
    if zero_areas:
        labels = ", ".join(_area_key_to_label(k) for k in zero_areas)
        quality_warnings.append(
            f"Zero matches for: {labels}. "
            "These areas may be described using alternative terminology not yet covered by the detection patterns."
        )
    warning_block = ""
    if quality_warnings:
        warning_block = "\n\n> **Detection notes:** " + " ".join(quality_warnings)

    if not plans:
        if total > 0:
            answer = (
                f"{coverage_header}{warning_block}\n\n"
                f"I analyzed **{total}** Unified Plan document(s), but none contained the requested focus-area mentions."
            )
        else:
            answer = "I could not find Unified Plan documents to analyze with the current source settings."
    elif answer:
        try:
            answer = re.sub(
                r"(?is)(?:^|\n)\s*(?:#{1,6}\s*)?(?:Sources|References)\s*:?\s*\n(?:[-*]\s+.*(?:\n|$)|\d+\.\s+.*(?:\n|$))*\s*$",
                "",
                answer,
            ).rstrip()
        except Exception as e:
            logger.debug("Unified plans fastpath: Sources regex strip failed: %s", e)
        answer = (
            f"{coverage_header}{area_counts_line}{warning_block}\n\n"
            f"{deterministic_table}\n\n"
            f"{answer.strip()}"
        ).strip()
    else:
        try:
            logger.error(
                "Unified plans fastpath synthesis fallback used. context=%s",
                json.dumps(
                    {
                        "query_preview": str(query or "")[:180],
                        "plans_analyzed": analyzed,
                        "total_plans_considered": total,
                        "llm_error": llm_synthesis_error,
                        "llm_attempts": llm_attempts,
                    },
                    ensure_ascii=False,
                    default=str,
                    )[:6000],
            )
        except Exception as e:
            logger.debug("Unified plans fastpath: fallback error log failed: %s", e)
        answer = (
            f"{coverage_header}{area_counts_line}{warning_block}\n\n"
            f"{deterministic_table}"
        ).strip()

    llm_synthesis_debug: Dict[str, Any] = {
        "used": bool(llm_synthesis_used),
        "model": model,
        "provider": provider,
        "finish_reason": llm_finish_reason,
        "elapsed_ms": int((time.time() - llm_synthesis_started_at) * 1000),
        "prompt_chars": int(llm_prompt_chars),
        "prompt_tokens": llm_input_tokens,
        "completion_tokens": llm_output_tokens,
        "payload": {
            "countries_grouped_in_payload": int(len(synthesis_payload.get("countries_grouped") or [])),
            "latest_per_country_in_payload": int(len(synthesis_payload.get("most_recent_plan_per_country") or [])),
            "total_plans_in_deterministic_table": int(len(plans)),
        },
        "attempts": llm_attempts,
        "error": llm_synthesis_error,
    }

    return {
        "success": True,
        "answer": answer,
        "status": "completed",
        "steps": [
            {
                "step": 0,
                "thought": "Used deterministic Unified Plan focus-area analyzer to avoid iterative document-search loops.",
                "action": "analyze_unified_plans_focus_areas",
                "observation": tool_result,
                "timestamp": utcnow().isoformat(),
            },
            {
                "step": 0,
                "thought": (
                    "Prepared final summarized review via LLM synthesis."
                    if llm_synthesis_used
                    else "Prepared fallback summarized review after LLM synthesis was unavailable."
                ),
                "action": "finish",
                "observation": {
                    "answer": answer,
                    "analysis_mode": "tool_plus_llm_synthesis" if llm_synthesis_used else "tool_plus_fallback_summary",
                    "llm_synthesis_debug": llm_synthesis_debug,
                },
                "timestamp": utcnow().isoformat(),
            },
        ],
        "tool_calls": 1,
        "iterations": 1,
        "analysis_mode": "tool_plus_llm_synthesis" if llm_synthesis_used else "tool_plus_fallback_summary",
        "llm_synthesis_used": bool(llm_synthesis_used),
        "llm_model_used": model if llm_synthesis_used else None,
        "llm_synthesis_debug": llm_synthesis_debug,
    }


UNIFIED_PLAN_THEME_PATTERNS = (
    "included in unified plan",
    "included in their unified plan",
    "include in unified plan",
    "in their unified plan",
    "in their 20",
    "unified plans that include",
    "unified plans that mention",
    "unified plans include",
    "unified plans mention",
    "unified plans cover",
    "which unified plans",
    "ns include",
    "national societies that include",
    "national societies that mention",
    "national societies that priorit",
    "national societies with ",
    "how many national societies",
    "unified plan",
    "(upl",
    "upl)",
    "whose unified",
    "upl-",
)

UNIFIED_PLAN_FORCE_LLM_RE = re.compile(
    r"(?:"
    r"details?\s+on\s+(?:the\s+)?(?:activity|activities|plan|plans|programme|program)"
    r"|activity\s+(?:detail|plans?|description)"
    r"|table\s+with\s+columns?"
    r"|create\s+a\s+table"
    r"|columns?\s+on\s+detail"
    r"|specific\s+activit"
    r"|what\s+(?:specific|concrete)\s+(?:activit|plan|programme)"
    r"|descri(?:be|ption)\s+(?:of\s+)?(?:the\s+)?(?:migration|activit)"
    r"|budget|timeframe|partner|implementing\s+partner"
    r"|target\s+population|geographic\s+focus"
    r"|how\s+(?:do|are)\s+(?:they|these|the\s+ns)"
    r"|compare\s+(?:the\s+)?(?:activit|plan|approach)"
    r"|breakdown\s+(?:of|by)"
    r")",
    re.IGNORECASE,
)

_THEME_MAP = [
    (["migration", "displacement", "migrant", "refugee", "idp", "asylum", "forced migration", "mixed migration"], "migration_displacement"),
    (["climate change", "climate adaptation", "climate risk", "climate resilience", "climate"], "climate"),
    (["mhpss", "mental health", "psychosocial"], "mhpss"),
    (["pgi", "protection gender inclusion", "gender-based violence", "gbv", "gender equality", "disability inclusion"], "pgi"),
    (["livelihood", "livelihoods", "food security", "economic security"], "livelihoods"),
    (["cash assistance", "cash transfer", "cash and voucher", "cva", "cash-based"], "cash"),
    (["community engagement", "accountability", "cea", "aap"], "cea"),
    (["social protection", "social assistance", "social safety net"], "social_protection"),
    (["health", "primary health care", "community health", "epidemic", "pandemic"], "health"),
    (["disaster risk reduction", "drr", "disaster preparedness", "early warning"], "disaster_risk_reduction"),
]


def extract_theme_areas_from_query(query: str) -> List[str]:
    """Return snake_case focus-area keys mentioned in a Unified Plans query."""
    q = (query or "").lower()
    scores: Dict[str, int] = {}
    for keywords, area_key in _THEME_MAP:
        hit_count = sum(1 for kw in keywords if kw in q)
        if hit_count:
            scores[area_key] = scores.get(area_key, 0) + hit_count
    if not scores:
        return []
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [area for area, _ in ranked]


def match_unified_plans_focus_plan(query: str, tool_names) -> Optional[Dict[str, Any]]:
    """Return a rule-based Unified Plans focus plan, or None to defer."""
    from plugins.upr.ai import is_upr_active

    if not is_upr_active():
        return None
    names = set(tool_names or [])
    if "analyze_unified_plans_focus_areas" not in names:
        return None
    q = (query or "").strip().lower()
    if not q or not any(p in q for p in UNIFIED_PLAN_THEME_PATTERNS):
        return None
    if UNIFIED_PLAN_FORCE_LLM_RE.search(q):
        logger.info(
            "Query planner: unified_plans_focus theme matched but query "
            "requests activity details / custom table — deferring to LLM path."
        )
        return None
    areas = extract_theme_areas_from_query(query)
    if not areas:
        logger.info(
            "Query planner: unified_plans_focus theme matched but no focus areas inferred — deferring to LLM planner.",
        )
        return None
    logger.info("Query planner: rule-based unified_plans_focus plan (skip LLM), areas=%s", areas)
    return {
        "kind": "unified_plans_focus",
        "tool_name": "analyze_unified_plans_focus_areas",
        "tool_args": {"areas": areas, "limit": 500},
        "output_hint": "table",
    }


def unified_plans_focus_wants_reference_enrichment(combined_text: str) -> bool:
    """True when the user (or answer) clearly asks for external reference columns."""
    q = (combined_text or "").lower()
    needles = (
        "population",
        "inform ",
        "inform risk",
        "inform severity",
        "hdi",
        "human development",
        "gdp",
        "gni",
        "income group",
        "per capita",
        "climate risk",
        "world bank",
        "urbanization rate",
        "literacy",
        "life expectancy",
        "median age",
        "fertility rate",
        "infant mortality",
        "poverty rate",
        "multidimensional poverty",
    )
    return any(n in q for n in needles)


def run_analyze_unified_plans_focus_areas(
    *,
    areas: Optional[List[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """Classify which Unified Plan documents mention the requested focus areas."""
    from sqlalchemy import or_, not_

    from app.models.embeddings import AIDocument
    from app.services.ai.documents.access import apply_document_read_filter
    from app.services.ai.policies.access_policy import resolve_ai_access_policy
    from app.services.ai.tools._utils import resolve_source_config
    from plugins.upr.ai.focus_area_tools import (
        assemble_plan_results,
        compile_area_regexes,
        extract_area_evidence,
        match_focus_areas,
        normalized_plan_key,
        resolve_area_config,
    )

    run_started_at = time.time()

    area_keys, area_seed_terms, area_regex_patterns, strict_patterns, area_labels = (
        resolve_area_config(areas)
    )
    compiled_area_regexes, compiled_strict_area_regexes = compile_area_regexes(
        area_keys, area_seed_terms, area_regex_patterns, strict_patterns,
    )

    docs_query = apply_document_read_filter(
        AIDocument.query.filter(
            AIDocument.searchable == True,  # noqa: E712
            AIDocument.processing_status == "completed",
        ),
        resolve_ai_access_policy().documents,
    )

    sources_norm = resolve_source_config()
    if isinstance(sources_norm, dict):
        include_system = bool(sources_norm.get("system_documents", False))
        include_upr = bool(sources_norm.get("upr_documents", False))
        if include_system and not include_upr:
            docs_query = docs_query.filter(AIDocument.source_url.is_(None))
        elif include_upr and not include_system:
            docs_query = docs_query.filter(AIDocument.source_url.isnot(None))
        elif not include_system and not include_upr:
            return {
                "total_plans": 0, "plans_analyzed": 0,
                "counts_by_area": {k: 0 for k in area_keys},
                "plans_with_no_target_areas": 0, "plans": [],
                "quality_debug": {
                    "detection_method": "not_run",
                    "reason": "document_sources_disabled",
                    "filters": {"area_keys": area_keys, "limit": int(limit)},
                },
                "summary": "Document sources are disabled for this chat request.",
            }
        elif include_system and include_upr:
            docs_query = docs_query.filter(AIDocument.source_url.isnot(None))

    docs_query = docs_query.filter(
        or_(
            AIDocument.title.ilike("%unified plan%"),
            AIDocument.title.ilike("%upl-%"),
            AIDocument.title.ilike("%upl_%"),
            AIDocument.title.ilike("%unified country plan%"),
            AIDocument.filename.ilike("%upl-%"),
            AIDocument.filename.ilike("%upl_%"),
        )
    )
    docs_query = docs_query.filter(
        not_(AIDocument.filename.ilike("%_AR_%")),
        not_(AIDocument.filename.ilike("%_MYR_%")),
        not_(AIDocument.title.ilike("%annual report%")),
        not_(AIDocument.title.ilike("%mid-year%")),
        not_(AIDocument.title.ilike("%mid year%")),
    )

    total_documents_matching_filter = int(docs_query.count())
    limit = max(1, min(int(limit), 1000))
    raw_fetch_limit = min(max(limit * 3, 1000), 4000)
    docs_raw = docs_query.order_by(AIDocument.created_at.desc()).limit(raw_fetch_limit).all()

    docs: List[Any] = []
    seen_keys: set = set()
    for d in docs_raw or []:
        key = normalized_plan_key(d)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        docs.append(d)
        if len(docs) >= limit:
            break

    total_plans = len(docs)
    doc_ids = [int(d.id) for d in docs]

    hits_by_area, detection_method, debug_info = match_focus_areas(
        doc_ids=doc_ids,
        area_keys=area_keys,
        area_seed_terms=area_seed_terms,
        compiled_area_regexes=compiled_area_regexes,
        compiled_strict_area_regexes=compiled_strict_area_regexes,
    )

    area_evidence_by_doc = extract_area_evidence(
        area_keys=area_keys,
        hits_by_area=hits_by_area,
        area_seed_terms=area_seed_terms,
        compiled_strict_area_regexes=compiled_strict_area_regexes,
        compiled_area_regexes=compiled_area_regexes,
    )

    plans, none_count, country_groups_map, all_countries_considered = assemble_plan_results(
        docs=docs,
        area_keys=area_keys,
        hits_by_area=hits_by_area,
        area_labels=area_labels,
        area_evidence_by_doc=area_evidence_by_doc,
    )

    countries_grouped: List[Dict[str, Any]] = []
    most_recent_plan_per_country: List[Dict[str, Any]] = []
    for grp in country_groups_map.values():
        grp_plans = list(grp.get("plans") or [])
        grp_plans.sort(
            key=lambda p: (
                int(p.get("plan_year") or 0),
                str(p.get("document_title") or p.get("document_filename") or ""),
            ),
            reverse=True,
        )
        grp_counts = {k: 0 for k in area_keys}
        for p in grp_plans:
            for k in (p.get("areas_mentioned") or []):
                if k in grp_counts:
                    grp_counts[k] += 1
        latest = grp_plans[0] if grp_plans else None
        if isinstance(latest, dict):
            most_recent_plan_per_country.append({
                "country_name": grp.get("country_name"),
                "country_iso3": grp.get("country_iso3"),
                "plan_year": latest.get("plan_year"),
                "document_id": latest.get("document_id"),
                "document_title": latest.get("document_title"),
                "document_url": latest.get("document_url"),
                "areas_mentioned": latest.get("areas_mentioned") or [],
                "no_target_areas": bool(latest.get("no_target_areas")),
            })
        countries_grouped.append({
            "country_name": grp.get("country_name"),
            "country_iso3": grp.get("country_iso3"),
            "plans_count": len(grp_plans),
            "counts_by_area": grp_counts,
            "plans": grp_plans,
        })
    countries_grouped.sort(key=lambda c: str(c.get("country_name") or ""))
    most_recent_plan_per_country.sort(key=lambda c: str(c.get("country_name") or ""))

    counts_by_area = {k: len(hits_by_area.get(k, set())) for k in area_keys}
    plans_with_any = len(plans)
    countries_with_matches = len(countries_grouped)
    total_countries_considered = len(all_countries_considered)
    top_area = max(counts_by_area.items(), key=lambda kv: kv[1])[0] if counts_by_area else None
    bottom_area = min(counts_by_area.items(), key=lambda kv: kv[1])[0] if counts_by_area else None
    summary = (
        f"Analyzed {total_plans} Unified Plan document(s)."
        f" {plans_with_any} mention at least one target area."
        f" {countries_with_matches} countries with mentions out of {total_countries_considered} considered."
        + (f" Most-mentioned area: {top_area}." if top_area is not None else "")
        + (f" Least-mentioned area: {bottom_area}." if bottom_area is not None else "")
    )

    quality_debug: Dict[str, Any] = {
        "run_started_at_unix": float(run_started_at),
        "run_elapsed_ms": int((time.time() - run_started_at) * 1000),
        "filters": {
            "area_keys": area_keys,
            "limit": int(limit),
            "raw_fetch_limit": int(raw_fetch_limit),
            "total_documents_matching_filter": int(total_documents_matching_filter),
            "total_plans_after_dedup": int(total_plans),
            "excluded_no_target_areas": int(none_count),
        },
        "detection_method": detection_method,
        **debug_info,
        "lexical_debug": {
            "regex_patterns_per_area": {k: len(compiled_area_regexes.get(k) or []) for k in area_keys},
            "strict_regex_patterns_per_area": {k: len(compiled_strict_area_regexes.get(k) or []) for k in area_keys},
        },
    }

    return {
        "total_plans": int(total_plans),
        "total_documents_matching_filter": int(total_documents_matching_filter),
        "plans_analyzed": len(plans),
        "countries_with_matches": int(countries_with_matches),
        "total_countries_considered": int(total_countries_considered),
        "detection_method": detection_method,
        "counts_by_area": counts_by_area,
        "plans_with_no_target_areas": int(none_count),
        "plans_excluded_no_target_areas": int(none_count),
        "plans": plans,
        "countries_grouped": countries_grouped,
        "most_recent_plan_per_country": most_recent_plan_per_country,
        "recommended_follow_up_actions": [
            "Run the same analysis on only the most recent Unified Plan per country to avoid over-weighting countries with many historical plans.",
            "Filter to countries where the latest plan has no target-area mentions, then inspect those plans for alternative terminology or data gaps.",
            "Compare each country's latest plan vs previous plan year to identify newly added or dropped focus areas.",
            "If results look too broad, increase semantic strictness thresholds and re-run with lexical confirmation emphasis.",
        ],
        "quality_debug": quality_debug,
        "summary": summary,
    }
