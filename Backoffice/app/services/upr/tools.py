"""
upr.tools – AI tool wrapper implementations for UPR-specific tools.

Standalone functions that are bound as instance methods on AIToolsRegistry
via ``register_upr_tools(registry)``.  Each function keeps the same
``@tool_wrapper`` semantics (caching, logging, source gating) as the
original inline methods they replace.

Public API
──────────
register_upr_tools(registry)
    Bind the four UPR tool methods onto *registry* so they appear as
    regular instance methods (``registry.get_upr_kpi_value(...)`` etc.).
"""

from __future__ import annotations

import logging
import time
import types
from typing import Any, Dict, List, Optional

from app.services.data_retrieval_service import (
    get_upr_kpi_value as get_upr_kpi_value_service,
    get_upr_kpi_timeseries as get_upr_kpi_timeseries_service,
    get_upr_kpi_values_for_all_countries as get_upr_kpi_values_for_all_countries_service,
)
from app.services.ai_tools._utils import (
    resolve_ai_user_context,
    resolve_source_config,
    tool_wrapper,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UPR KPI tool implementations
# ---------------------------------------------------------------------------

@tool_wrapper
def get_upr_kpi_value(
    self,
    country_identifier: str,
    metric: str,
) -> Dict[str, Any]:
    """
    Get UPR-extracted KPI values (branches/local units/volunteers/staff) from document chunk metadata.

    This is a deterministic metadata lookup (does not require vector search).
    Use it for questions like:
    - "Number of branches in Syria"
    - "How many volunteers does Afghanistan have?"
    """
    return get_upr_kpi_value_service(country_identifier=country_identifier, metric=metric)


@tool_wrapper
def get_upr_kpi_timeseries(
    self,
    country_identifier: str,
    metric: str,
) -> Dict[str, Any]:
    """
    Get UPR KPI time series (best value per document-year) for ONE country from document metadata.

    Use for queries like:
    - "volunteers in Syria over time (from documents)"
    - "trend of branches in Kenya by year"
    when UPR/document sources are enabled and the user asks for a trend or time series.

    Returns one point per document-year so the UI can render a line chart.
    """
    return get_upr_kpi_timeseries_service(country_identifier=country_identifier, metric=metric)


@tool_wrapper
def get_upr_kpi_values_for_all_countries(self, metric: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Get UPR KPI values (branches, local_units, volunteers, staff) for ALL user-accessible
    countries in one call. Use for "volunteers for all countries", "list branches by country",
    "table of staff by country", etc. Returns one row per country that has data.

    Prefer this over calling get_upr_kpi_value 192 times. For single-country questions use
    get_upr_kpi_value instead.
    """
    kwargs.pop("_progress_callback", None)
    return get_upr_kpi_values_for_all_countries_service(metric=metric)


# ---------------------------------------------------------------------------
# Unified Plans focus-area analysis
# ---------------------------------------------------------------------------

@tool_wrapper
def analyze_unified_plans_focus_areas(
    self,
    areas: Optional[List[str]] = None,
    limit: int = 500,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Analyze Unified Plan documents and classify which plans mention focus areas.

    Returns per-plan flags, counts by area, and summary metadata in one deterministic pass.
    """
    kwargs.pop("_progress_callback", None)

    from sqlalchemy import or_, not_
    from app.models.embeddings import AIDocument
    from app.services.ai_tools._focus_area_analysis import (
        resolve_area_config,
        compile_area_regexes,
        match_focus_areas,
        extract_area_evidence,
        assemble_plan_results,
        normalized_plan_key,
    )

    run_started_at = time.time()

    # Phase 1: Area configuration
    area_keys, area_seed_terms, area_regex_patterns, strict_patterns, area_labels = \
        resolve_area_config(areas)
    compiled_area_regexes, compiled_strict_area_regexes = compile_area_regexes(
        area_keys, area_seed_terms, area_regex_patterns, strict_patterns,
    )

    logger.info("Focus-area tool: phase 1 (area config) done in %dms, areas=%s",
                int((time.time() - run_started_at) * 1000), area_keys)

    # Phase 2: User context & document query
    phase2_start = time.time()
    user_id, _, is_admin = resolve_ai_user_context()

    docs_query = AIDocument.query.filter(
        AIDocument.searchable == True,
        AIDocument.processing_status == "completed",
    )

    if not is_admin:
        if user_id:
            docs_query = docs_query.filter(
                or_(AIDocument.is_public == True, AIDocument.user_id == int(user_id))
            )
        else:
            docs_query = docs_query.filter(AIDocument.is_public == True)

    # Source selection
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

    # Unified Plan inventory filter
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

    # Deduplicate by normalized plan key
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

    logger.info("Focus-area tool: phase 2 (document query) done in %dms, total_plans=%d, docs_raw=%d",
                int((time.time() - phase2_start) * 1000), total_plans, len(docs_raw or []))

    # Phase 3: Focus area matching
    phase3_start = time.time()
    hits_by_area, detection_method, debug_info = match_focus_areas(
        doc_ids=doc_ids,
        area_keys=area_keys,
        area_seed_terms=area_seed_terms,
        compiled_area_regexes=compiled_area_regexes,
        compiled_strict_area_regexes=compiled_strict_area_regexes,
    )

    logger.info("Focus-area tool: phase 3 (matching) done in %dms, method=%s, hits=%s",
                int((time.time() - phase3_start) * 1000), detection_method,
                {k: len(v) for k, v in hits_by_area.items()})

    # Phase 4: Evidence extraction
    phase4_start = time.time()
    area_evidence_by_doc = extract_area_evidence(
        area_keys=area_keys,
        hits_by_area=hits_by_area,
        area_seed_terms=area_seed_terms,
        compiled_strict_area_regexes=compiled_strict_area_regexes,
        compiled_area_regexes=compiled_area_regexes,
    )

    logger.info("Focus-area tool: phase 4 (evidence) done in %dms",
                int((time.time() - phase4_start) * 1000))

    # Phase 5: Result assembly
    phase5_start = time.time()
    plans, none_count, country_groups_map, all_countries_considered = assemble_plan_results(
        docs=docs,
        area_keys=area_keys,
        hits_by_area=hits_by_area,
        area_labels=area_labels,
        area_evidence_by_doc=area_evidence_by_doc,
    )

    logger.info("Focus-area tool: phase 5 (assembly) done in %dms",
                int((time.time() - phase5_start) * 1000))

    # Build country-grouped output
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
                "document_filename": latest.get("document_filename"),
                "document_url": latest.get("document_url"),
                "document_country_name": latest.get("document_country_name") or grp.get("country_name"),
                "document_country_iso3": latest.get("document_country_iso3") or grp.get("country_iso3"),
                "areas_mentioned": latest.get("areas_mentioned") or [],
                "area_details": latest.get("area_details") or {},
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


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

_UPR_TOOLS = [
    get_upr_kpi_value,
    get_upr_kpi_timeseries,
    get_upr_kpi_values_for_all_countries,
    analyze_unified_plans_focus_areas,
]


def register_upr_tools(registry) -> None:
    """Bind UPR tool functions as bound methods on *registry*.

    After this call ``registry.get_upr_kpi_value(...)`` etc. behave exactly
    like the original inline ``@tool_wrapper`` methods.
    """
    for fn in _UPR_TOOLS:
        setattr(registry, fn.__name__, types.MethodType(fn, registry))
