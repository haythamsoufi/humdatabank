"""
AI Tools Registry

Defines all available tools that the AI agent can use.
Includes function signatures, parameter validation, and execution wrappers.
"""

import logging
import inspect
import re
import time
import json
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
from collections import defaultdict
from flask import current_app, g, has_request_context
from flask_login import current_user

from app.services.data_retrieval_service import (
    get_indicator_details,
    get_country_info,
    resolve_country,
    get_template_structure,
    get_value_breakdown,
    get_indicator_timeseries,
    get_assignments_for_country,
    get_assignment_indicator_values,
    get_platform_stats,
    get_user_profile,
    get_form_field_value as get_form_field_value_service,
    get_indicator_values_for_all_countries as get_indicator_values_for_all_countries_service,
)
from app.services.upr.data_retrieval import (
    get_upr_kpi_value as get_upr_kpi_value_service,
    get_upr_kpi_timeseries as get_upr_kpi_timeseries_service,
    get_upr_kpi_values_for_all_countries as get_upr_kpi_values_for_all_countries_service,
)
from app.services.upr.tool_specs import UPR_TOOL_SPECS, UPR_KPI_TOOL_NAMES, UPR_CACHEABLE_TOOLS
from app.services.data_retrieval_form import resolve_indicator_to_primary_id
from app.utils.sql_utils import safe_ilike_pattern
from app.services.ai_vector_store import AIVectorStore

from app.services.ai_tools._cache import tool_cache_get, tool_cache_set

logger = logging.getLogger(__name__)

from app.services.ai_tools._utils import (
    log_tool_usage,
    truncate_json_value,
    ToolExecutionError,
    resolve_ai_user_context,
    resolve_source_config,
    apply_document_source_filters,
)
from app.services.ai_tools._query_utils import (
    infer_country_identifier_from_query,
    rewrite_document_search_query,
    resolve_country_search_filters,
)
from app.services.upr.query_detection import query_prefers_upr_documents

def tool_wrapper(func: Callable) -> Callable:
    """Decorator to wrap tool execution with caching, source gating, error handling, and logging."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        call_kwargs = kwargs
        try:
            sig = inspect.signature(func)
            params = sig.parameters
            accepts_var_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
            if "_progress_callback" in kwargs and "_progress_callback" not in params and not accepts_var_kwargs:
                call_kwargs = dict(kwargs)
                call_kwargs.pop("_progress_callback", None)
        except Exception as exc:
            logger.debug("tool_wrapper: inspect.signature failed: %s", exc)
            if "_progress_callback" in kwargs:
                call_kwargs = dict(kwargs)
                call_kwargs.pop("_progress_callback", None)

        log_kwargs = dict(call_kwargs) if call_kwargs is not kwargs else dict(kwargs)
        log_kwargs.pop("_progress_callback", None)

        logger.info("Executing tool: %s with args=%s, kwargs=%s", tool_name, args, log_kwargs)

        start_time = time.time()
        user_id, user_role, _ = resolve_ai_user_context()
        sources_norm = resolve_source_config()

        try:
            cache_enabled = str(current_app.config.get("AI_TOOL_CACHE_ENABLED", True)).lower() == "true"
            ttl_seconds = int(current_app.config.get("AI_TOOL_CACHE_TTL_SECONDS", 300))
            try:
                max_entries = int(current_app.config.get("AI_TOOL_CACHE_MAX_ENTRIES", 2000))
            except Exception:
                max_entries = 2000

            # Enforce source selection for tools that should not run when a source is disabled.
            if sources_norm is not None:
                databank_tools = {
                    "get_indicator_value", "get_indicator_values_for_all_countries",
                    "get_indicator_timeseries", "get_indicator_metadata",
                    "get_country_information", "get_template_details",
                    "get_user_assignments", "get_assignment_indicator_values",
                    "get_form_field_value",
                }
                upr_tools = UPR_KPI_TOOL_NAMES
                if tool_name in databank_tools and not sources_norm.get("historical", False):
                    raise ToolExecutionError("Databank source is disabled for this chat request.")
                if tool_name in upr_tools and not sources_norm.get("upr_documents", False):
                    raise ToolExecutionError("UPR documents source is disabled for this chat request.")

            cacheable_tools = {
                "get_indicator_value", "get_indicator_values_for_all_countries",
                "get_indicator_timeseries", "get_country_information",
                "get_template_details", "get_user_assignments",
                "get_assignment_indicator_values", "get_system_statistics",
                "get_current_user_info", "get_indicator_metadata",
                "get_form_field_value",
                "search_documents", "search_documents_hybrid",
                "list_documents",
            } | UPR_CACHEABLE_TOOLS

            cache_key = None
            if cache_enabled and tool_name in cacheable_tools:
                try:
                    cache_kwargs = dict(log_kwargs)
                    if tool_name in {
                        "get_indicator_value", "get_indicator_values_for_all_countries",
                        "get_indicator_timeseries", "get_indicator_metadata",
                    }:
                        raw_ind = cache_kwargs.get("indicator_name")
                        if isinstance(raw_ind, str):
                            ind = raw_ind.strip()
                            if ind:
                                try:
                                    pid = resolve_indicator_to_primary_id(ind)
                                except Exception:
                                    pid = None
                                if pid is not None:
                                    cache_kwargs["indicator_name_raw"] = ind
                                    cache_kwargs["indicator_name"] = f"primary_id:{int(pid)}"
                    cache_key = json.dumps(
                        {
                            "tool": tool_name,
                            "user_id": int(user_id or 0),
                            "role": str(user_role or "public"),
                            "sources": sources_norm,
                            "kwargs": cache_kwargs,
                        },
                        sort_keys=True,
                        ensure_ascii=True,
                        default=str,
                    )
                except Exception:
                    cache_key = None

            if cache_key:
                cached = tool_cache_get(cache_key)
                if isinstance(cached, dict):
                    logger.info("Tool %s cache hit", tool_name)
                    log_tool_usage(
                        tool_name=tool_name,
                        tool_input=log_kwargs,
                        tool_output=cached,
                        success=bool(cached.get("success", True)),
                        error_message=str(cached.get("error")) if cached.get("error") else None,
                        execution_time_ms=cached.get("execution_time_ms"),
                        user_id=user_id,
                    )
                    return cached

            result = func(*args, **call_kwargs)
            execution_time = (time.time() - start_time) * 1000

            logger.info("Tool %s completed in %.0fms", tool_name, execution_time)
            payload = {
                'success': True,
                'result': result,
                'execution_time_ms': execution_time,
            }
            log_tool_usage(
                tool_name=tool_name,
                tool_input=log_kwargs,
                tool_output=payload,
                success=True,
                error_message=None,
                execution_time_ms=execution_time,
                user_id=user_id,
            )
            if cache_key:
                tool_cache_set(cache_key, payload, ttl_seconds=ttl_seconds, max_entries=max_entries)
            return payload
        except ToolExecutionError as e:
            execution_time = (time.time() - start_time) * 1000
            logger.warning("Tool %s raised ToolExecutionError: %s", tool_name, e)
            payload = {
                'success': False,
                'error': str(e),
                'error_type': 'ToolExecutionError',
                'execution_time_ms': execution_time,
            }
            log_tool_usage(
                tool_name=tool_name,
                tool_input=log_kwargs,
                tool_output=payload,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time,
                user_id=user_id,
            )
            return payload
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
            payload = {
                'success': False,
                'error': 'Tool execution failed.',
                'error_type': type(e).__name__,
            }
            log_tool_usage(
                tool_name=tool_name,
                tool_input=log_kwargs,
                tool_output=payload,
                success=False,
                error_message="Tool execution failed.",
                execution_time_ms=execution_time,
                user_id=user_id,
            )
            return payload

    return wrapper


class AIToolsRegistry:
    """
    Registry of all available tools for the AI agent.

    Tools are organized by category:
    - Database query tools: Query structured data
    - Document search tools: Search vectorized documents
    - Analysis tools: Perform calculations and comparisons
    """

    def __init__(self):
        """Initialize the tools registry."""
        self.vector_store = AIVectorStore()

    # ==================== DATABASE QUERY TOOLS ====================

    @tool_wrapper
    def get_indicator_value(
        self,
        country_identifier: str,
        indicator_name: str,
        period: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get indicator value for a country and optional period.

        Args:
            country_identifier: Country name, ISO3 code, or ID
            indicator_name: Name of the indicator
            period: Optional period filter (e.g., "2023", "FY2023")

        Returns:
            Dictionary with indicator value, breakdown, and metadata
        """
        # Resolve country WITHOUT RBAC gating; RBAC is enforced at the data layer.
        country = resolve_country(country_identifier)
        if not country or not getattr(country, "id", None):
            raise ToolExecutionError(f"Country not found: {country_identifier}")
        country_id = int(country.id)

        # Get value breakdown
        breakdown = get_value_breakdown(
            country_id=country_id,
            indicator_identifier=indicator_name,
            period=period
        )

        return breakdown

    @tool_wrapper
    def get_indicator_timeseries(
        self,
        country_identifier: str,
        indicator_name: str,
        limit_periods: int = 12,
        include_saved: bool = True,
    ) -> Dict[str, Any]:
        """
        Get an indicator time series for a country (best available value per year/period).

        Use for queries like:
        - "volunteers in Syria over time"
        - "trend of branches in Kenya by year"

        Returns one point per year so the UI can render a line chart.
        """
        country = resolve_country(country_identifier)
        if not country or not getattr(country, "id", None):
            raise ToolExecutionError(f"Country not found: {country_identifier}")
        return get_indicator_timeseries(
            country_id=int(country.id),
            indicator_identifier=indicator_name,
            limit_periods=int(limit_periods or 12),
            include_saved=bool(include_saved),
        )

    @tool_wrapper
    def get_country_information(self, country_identifier: str) -> Dict[str, Any]:
        """
        Get comprehensive information about a country.

        Args:
            country_identifier: Country name, ISO3 code, or ID

        Returns:
            Dictionary with country details, assignments, and statistics
        """
        return get_country_info(country_identifier)

    @tool_wrapper
    def get_template_details(self, template_identifier: str) -> Dict[str, Any]:
        """
        Get details about a form template structure.

        Args:
            template_identifier: Template ID or name

        Returns:
            Dictionary with template structure and metadata
        """
        return get_template_structure(template_identifier)

    @tool_wrapper
    def get_user_assignments(
        self,
        country_identifier: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get assignments for a country.

        Args:
            country_identifier: Country name, ISO3 code, or ID
            status: Optional status filter ('Pending', 'Submitted', etc.)

        Returns:
            List of assignments
        """
        country_info = get_country_info(country_identifier)
        if 'error' in country_info:
            err = str(country_info.get("error") or "").strip() or "Country lookup failed"
            if err.lower().startswith("country not found"):
                raise ToolExecutionError(f"Country not found: {country_identifier}")
            raise ToolExecutionError(err)

        country_id = country_info['country']['id']

        return get_assignments_for_country(
            country_id=country_id,
            status_filter=status
        )

    @tool_wrapper
    def get_assignment_indicator_values(
        self,
        country_identifier: str,
        template_identifier: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get reported indicator values for an assignment (country + template + period).

        Use for questions like "FDRS 2024 Syria indicators" or "what values did Syria report for FDRS 2024".
        Returns the list of indicators and their submitted (or saved) values for that assignment.
        Do NOT use search_documents for this — use this tool and get_template_details / get_user_assignments.
        """
        return get_assignment_indicator_values(
            country_identifier=country_identifier,
            template_identifier=template_identifier,
            period=period,
        )

    @tool_wrapper
    def get_system_statistics(self) -> Dict[str, Any]:
        """
        Get platform-wide statistics.

        Returns:
            Dictionary with platform statistics
        """
        return get_platform_stats(user_scoped=True)

    @tool_wrapper
    def get_current_user_info(self) -> Dict[str, Any]:
        """
        Get information about the current user.

        Returns:
            Dictionary with user profile and permissions
        """
        return get_user_profile()

    @tool_wrapper
    def get_indicator_metadata(self, indicator_name: str) -> Dict[str, Any]:
        """
        Get metadata about an indicator (definition, unit, sectors, etc.).

        Args:
            indicator_name: Name of the indicator

        Returns:
            Dictionary with indicator details
        """
        details = get_indicator_details(indicator_name)
        if not details:
            raise ToolExecutionError(f"Indicator not found: {indicator_name}")
        return details

    @tool_wrapper
    def get_form_field_value(
        self,
        country_identifier: str,
        field_label_or_name: str,
        period: Optional[str] = None,
        assignment_period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get value(s) for a form field (section or matrix) for a country.

        Use for "People to be reached by Bangladesh in 2027". Matches by SECTION name (e.g. "People to be reached")
        or ITEM label (e.g. "Longer term programmes"). period filters the MATRIX ROW (e.g. 2027), not the assignment
        period. Optionally pass assignment_period (e.g. "2025") to restrict to that assignment.

        Args:
            country_identifier: Country name (e.g. 'Bangladesh'), ISO3 (e.g. 'BGD'), or ID
            field_label_or_name: Section name or form item label (e.g. 'people to be reached', 'Longer term programmes')
            period: Matrix row/key filter (e.g. '2027') — which row of the matrix to sum, NOT assignment period
            assignment_period: Optional assignment period (e.g. '2025') to restrict which submission(s)

        Returns:
            Dict with success, field_label, section_label, country, period, total, breakdown, data_status, notes, debug
        """
        return get_form_field_value_service(
            country_identifier=country_identifier,
            field_label_or_name=field_label_or_name,
            period=period,
            assignment_period=assignment_period,
        )

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
        kwargs.pop("_progress_callback", None)  # executor may pass it; we don't use it
        return get_upr_kpi_values_for_all_countries_service(metric=metric)

    @tool_wrapper
    def get_indicator_values_for_all_countries(
        self,
        indicator_name: str,
        period: Optional[str] = None,
        min_value: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Get indicator values for ALL user-accessible countries in one call. Use for "volunteers
        for all countries", "list indicator X by country", "table of [indicator] for every country", etc.
        Returns one row per country that has a value (from the databank / Indicator Bank).

        When the user asks for countries above a threshold (e.g. "more than 10000 volunteers"),
        pass min_value so the backend returns only qualifying rows (e.g. min_value=10001 for "more than 10000").
        Then you only need to display every row in the response — no filtering in your answer.

        Prefer this over calling get_indicator_value 192 times. For single-country questions use
        get_indicator_value instead. For UPR metrics (branches, volunteers, staff, local_units)
        also use get_upr_kpi_values_for_all_countries when you need document-extracted values.
        """
        on_progress = kwargs.pop("_progress_callback", None)
        max_countries = int(current_app.config.get("AI_INDICATOR_MAX_COUNTRIES", 250))
        return get_indicator_values_for_all_countries_service(
            indicator_name=indicator_name,
            period=period,
            max_countries=max_countries,
            min_value=min_value,
            on_progress=on_progress,
        )

    # ==================== DOCUMENT SEARCH TOOLS ====================

    @tool_wrapper
    def list_documents(
        self,
        query: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        status: Optional[str] = None,
        file_type: Optional[str] = None,
        country_identifier: Optional[str] = None,
        include_metadata: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        List AI-processed documents (metadata only).

        Use this when the user is asking *which documents exist* (e.g. "Which countries have UPL-2026 PDFs?")
        rather than asking questions that require reading document text (use search_documents for that).
        """
        kwargs.pop("_progress_callback", None)  # executor may pass it; we don't use it

        from sqlalchemy import or_
        from app.models.embeddings import AIDocument

        q = (query or "").strip()
        status = (status or "").strip() or None
        file_type = (file_type or "").strip() or None
        country_hint = (country_identifier or "").strip() or None

        user_id, _, is_admin = resolve_ai_user_context()

        docs_query = AIDocument.query.filter(AIDocument.searchable == True)

        # Permission filter: non-admins can only see public docs or their own.
        if not is_admin:
            if user_id:
                docs_query = docs_query.filter(
                    or_(
                        AIDocument.is_public == True,
                        AIDocument.user_id == int(user_id),
                    )
                )
            else:
                docs_query = docs_query.filter(AIDocument.is_public == True)

        # Filters.
        if status:
            docs_query = docs_query.filter(AIDocument.processing_status == status)
        if file_type:
            docs_query = docs_query.filter(AIDocument.file_type == file_type)

        if country_hint:
            try:
                country = resolve_country(country_hint)
                if country and getattr(country, "id", None):
                    docs_query = docs_query.filter(
                        or_(
                            AIDocument.country_id == int(country.id),
                            AIDocument.country_name == str(getattr(country, "name", "")).strip(),
                        )
                    )
                else:
                    docs_query = docs_query.filter(AIDocument.country_name.ilike(safe_ilike_pattern(country_hint)))
            except Exception as e:
                logger.debug("country filter failed: %s", e)
                docs_query = docs_query.filter(AIDocument.country_name.ilike(safe_ilike_pattern(country_hint)))

        if q:
            pattern = safe_ilike_pattern(q or "")
            docs_query = docs_query.filter(
                or_(
                    AIDocument.title.ilike(pattern),
                    AIDocument.filename.ilike(pattern),
                )
            )

        # Pagination caps (avoid huge tool payloads).
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))

        total = docs_query.count()
        docs = (
            docs_query.order_by(AIDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        from app.utils.ai_utils import extract_upl_year_from_title

        rows: List[Dict[str, Any]] = []
        for d in docs or []:
            payload = d.to_dict()
            # Add consistent download URL field (mirrors search_documents).
            payload["document_url"] = f"/api/ai/documents/{int(d.id)}/download"
            # Expose plan year from UPL-style titles so the agent can build "most recent UPL year" tables/maps.
            plan_year = extract_upl_year_from_title(getattr(d, "title", None) or payload.get("title") or "")
            if plan_year is not None:
                payload["plan_year"] = plan_year
            if not include_metadata:
                payload.pop("metadata", None)
            rows.append(payload)

        return {
            "total": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "documents": rows,
        }

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

        # Phase 2: User context & document query
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

        # Phase 3: Focus area matching
        hits_by_area, detection_method, debug_info = match_focus_areas(
            doc_ids=doc_ids,
            area_keys=area_keys,
            area_seed_terms=area_seed_terms,
            compiled_area_regexes=compiled_area_regexes,
            compiled_strict_area_regexes=compiled_strict_area_regexes,
        )

        # Phase 4: Evidence extraction
        area_evidence_by_doc = extract_area_evidence(
            area_keys=area_keys,
            hits_by_area=hits_by_area,
            area_seed_terms=area_seed_terms,
            compiled_strict_area_regexes=compiled_strict_area_regexes,
            compiled_area_regexes=compiled_area_regexes,
        )

        # Phase 5: Result assembly
        plans, none_count, country_groups_map, all_countries_considered = assemble_plan_results(
            docs=docs,
            area_keys=area_keys,
            hits_by_area=hits_by_area,
            area_labels=area_labels,
            area_evidence_by_doc=area_evidence_by_doc,
        )

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

    @tool_wrapper
    def search_documents(
        self,
        query: str,
        top_k: int = 5,
        document_type: Optional[str] = None,
        country_identifier: Optional[str] = None,
        return_all_countries: bool = False,
        offset: int = 0,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Search documents using hybrid search (vector + keyword).
        Returns full chunk content so the LLM can read and decide; supports pagination via offset/limit.

        Args:
            query: Search query
            top_k: Number of results to return (1-20 normally; up to config limit when return_all_countries=True)
            document_type: Optional file type filter ('pdf', 'docx', etc.)
            country_identifier: Optional country filter (country name, ISO3, or ID). Ignored if return_all_countries=True.
            return_all_countries: If True, do NOT filter by country and allow higher top_k for list-style queries.
            offset: For pagination: skip this many chunks (use with limit to fetch all in batches).
            limit: For pagination: return at most this many chunks per call. When return_all_countries=True,
                   use limit (e.g. 100) and call again with offset=offset+limit until you have total_count.

        Returns:
            Dict with success, result (list of chunks with full content), total_count, offset, limit.
        """
        on_progress = kwargs.pop("_progress_callback", None)  # optional detail-only progress callback
        last_progress_msg: str | None = None
        def _emit_progress(msg: str) -> None:
            nonlocal last_progress_msg
            if not callable(on_progress):
                return
            s = (msg or "").strip()
            if not s:
                return
            if last_progress_msg == s:
                return
            last_progress_msg = s
            try:
                on_progress(s)
            except Exception as e:
                logger.debug("_emit_progress failed: %s", e)
                return

        max_default = 20
        max_list = int(current_app.config.get("AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST", 500))
        batch_size = int(current_app.config.get("AI_SEARCH_DOCUMENTS_BATCH_SIZE", 100))
        if return_all_countries:
            top_k = max(1, int(max_list))
            if limit is None:
                limit = batch_size  # default batching so LLM can request all pages
        else:
            top_k = max(1, min(top_k, max_default))
            if limit is None:
                limit = top_k

        filters = {}
        if document_type:
            filters['file_type'] = document_type

        sources_cfg = resolve_source_config()
        if not apply_document_source_filters(filters, sources_cfg, query=query):
            return {"success": True, "result": [], "total_count": 0, "offset": 0, "limit": limit or 100}

        if not return_all_countries:
            country_hint = (country_identifier or "").strip() or infer_country_identifier_from_query(query)
            resolve_country_search_filters(country_hint, filters)

        user_id, user_role, _ = resolve_ai_user_context()

        # Default to hybrid search for better lexical + semantic matching.
        rewritten = None
        try:
            if current_app.config.get("AI_DOCUMENT_SEARCH_SANITIZE_QUERY", True):
                rewritten = rewrite_document_search_query(query)
        except Exception as e:
            logger.debug("rewrite_document_search_query failed: %s", e)
            rewritten = None

        vector_query = (rewritten or {}).get("vector_query") if isinstance(rewritten, dict) else None
        keyword_query = (rewritten or {}).get("keyword_query") if isinstance(rewritten, dict) else None
        vector_query = (vector_query or "").strip() or query
        keyword_query = (keyword_query or "").strip() or query

        # Pagination cache: key by (query, filters) so offset>0 can reuse the same result set
        cache_key = None
        if has_request_context() and offset > 0:
            try:
                cache_key = json.dumps({"q": query, "f": sorted((k, str(v)) for k, v in filters.items())}, sort_keys=True)
                cached = getattr(g, "ai_search_documents_cache", None)
                if isinstance(cached, dict) and cached.get("key") == cache_key and isinstance(cached.get("results"), list):
                    full_results = cached["results"]
                    total_count = len(full_results)
                    chunk_slice = full_results[offset : offset + limit]
                    return {
                        "success": True,
                        "result": chunk_slice,
                        "total_count": total_count,
                        "offset": offset,
                        "limit": limit,
                        "execution_time_ms": 0,
                    }
            except Exception as e:
                logger.debug("cache lookup failed: %s", e)

        _emit_progress(f"Retrieving up to {int(top_k)} matches…")

        results = self.vector_store.hybrid_search(
            query_text=query,
            vector_query_text=vector_query,
            keyword_query_text=keyword_query,
            top_k=top_k,
            filters=filters,
            user_id=user_id,
            user_role=user_role,
        )

        results = results or []

        # Score-based filtering: drop chunks below relevance threshold.
        # Uses both a fixed floor and an adaptive cutoff relative to the top score,
        # so low-similarity noise is pruned even when the embedding model produces
        # high baseline similarities.
        if return_all_countries and results:
            floor = float(current_app.config.get("AI_DOCUMENT_SEARCH_MIN_SCORE", 0.3))
            ratio = float(current_app.config.get("AI_DOCUMENT_SEARCH_MIN_SCORE_RATIO", 0.45))
            top_score = max(r.get("combined_score", 0) for r in results)
            adaptive = top_score * ratio if top_score > 0 else 0
            threshold = max(floor, adaptive)
            before = len(results)
            results = [r for r in results if r.get("combined_score", 0) >= threshold]
            if len(results) < before:
                logger.info(
                    "Score filter (floor=%.2f, adaptive=%.2f→threshold=%.2f): %d → %d chunks",
                    floor, adaptive, threshold, before, len(results),
                )
        try:
            doc_ids = []
            for r in results:
                did = r.get("document_id")
                if did is not None and did not in doc_ids:
                    doc_ids.append(did)
            num_chunks = len(results)
            num_docs = len(doc_ids)
            logger.info(
                "Document search result: chunks=%d distinct_documents=%d top_k_requested=%s return_all_countries=%s",
                num_chunks, num_docs, top_k, return_all_countries,
            )
            _emit_progress(f"Found {num_chunks} chunks across {num_docs} document(s).")
            total_docs = len(doc_ids)
            if total_docs >= 25:
                for i in range(total_docs):
                    if i == 0 or (i + 1) % 10 == 0 or i == total_docs - 1:
                        _emit_progress(f"Processing documents: {i + 1}/{total_docs}")
        except Exception as e:
            logger.debug("document processing progress failed: %s", e)

        # Add document_url so the agent can hyperlink citations (direct download)
        for r in results:
            doc_id = r.get('document_id')
            if doc_id is not None:
                r['document_url'] = f'/api/ai/documents/{int(doc_id)}/download'
            else:
                r['document_url'] = None

        # Cache full result for pagination (same request only)
        if has_request_context() and limit is not None and len(results) > limit:
            if cache_key is None:
                try:
                    cache_key = json.dumps({"q": query, "f": sorted((k, str(v)) for k, v in filters.items())}, sort_keys=True)
                except Exception as e:
                    logger.debug("cache_key json.dumps failed: %s", e)
                    cache_key = ""
            if cache_key:
                g.ai_search_documents_cache = {"key": cache_key, "results": results}

        total_count = len(results)
        chunk_slice = results[offset : offset + limit]
        return {
            "success": True,
            "result": chunk_slice,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
        }

    @tool_wrapper
    def search_documents_hybrid(
        self,
        query: str,
        top_k: int = 5,
        document_type: Optional[str] = None,
        country_identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Search documents using hybrid search (vector + keyword).

        Better for queries with specific terms or technical vocabulary.

        Args:
            query: Search query
            top_k: Number of results to return (1-20)
            document_type: Optional file type filter
            country_identifier: Optional country filter (country name, ISO3, or ID)

        Returns:
            List of matching document chunks with combined scores
        """
        kwargs.pop("_progress_callback", None)
        top_k = max(1, min(top_k, 20))

        filters = {}
        if document_type:
            filters['file_type'] = document_type

        sources_cfg = resolve_source_config()
        if not apply_document_source_filters(filters, sources_cfg, query=query):
            return []

        country_hint = (country_identifier or "").strip() or infer_country_identifier_from_query(query)
        resolve_country_search_filters(country_hint, filters)

        user_id, user_role, _ = resolve_ai_user_context()

        rewritten = None
        try:
            if current_app.config.get("AI_DOCUMENT_SEARCH_SANITIZE_QUERY", True):
                rewritten = rewrite_document_search_query(query)
        except Exception as e:
            logger.debug("rewrite_document_search_query failed: %s", e)
            rewritten = None
        vector_query = (rewritten or {}).get("vector_query") if isinstance(rewritten, dict) else None
        keyword_query = (rewritten or {}).get("keyword_query") if isinstance(rewritten, dict) else None
        vector_query = (vector_query or "").strip() or query
        keyword_query = (keyword_query or "").strip() or query

        # Multi-step retrieval for complex/comparative queries
        multistep_enabled = current_app.config.get("AI_MULTISTEP_RETRIEVAL_ENABLED", True)
        if multistep_enabled:
            try:
                from app.services.ai_multistep_retrieval import is_decomposable_query, MultiStepRetriever
                if is_decomposable_query(query):
                    logger.debug("Multi-step retrieval activated for query: %r", query[:80])
                    _retriever = MultiStepRetriever()
                    results, _sqs = _retriever.retrieve(
                        query,
                        filters=filters,
                        user_id=user_id,
                        user_role=user_role,
                        top_k=top_k,
                    )
                else:
                    results = self.vector_store.hybrid_search(
                        query_text=query,
                        vector_query_text=vector_query,
                        keyword_query_text=keyword_query,
                        top_k=top_k,
                        filters=filters,
                        user_id=user_id,
                        user_role=user_role,
                    )
            except Exception as _msr_err:
                logger.warning("Multi-step retrieval error, falling back: %s", _msr_err)
                results = self.vector_store.hybrid_search(
                    query_text=query,
                    vector_query_text=vector_query,
                    keyword_query_text=keyword_query,
                    top_k=top_k,
                    filters=filters,
                    user_id=user_id,
                    user_role=user_role,
                )
        else:
            results = self.vector_store.hybrid_search(
                query_text=query,
                vector_query_text=vector_query,
                keyword_query_text=keyword_query,
                top_k=top_k,
                filters=filters,
                user_id=user_id,
                user_role=user_role,
            )
        doc_ids_hybrid = []
        for r in results or []:
            did = r.get("document_id")
            if did is not None and did not in doc_ids_hybrid:
                doc_ids_hybrid.append(did)
        logger.info(
            "Document search (hybrid) result: chunks=%d distinct_documents=%d top_k=%s",
            len(results or []), len(doc_ids_hybrid), top_k,
        )
        # Add document_url so the agent can hyperlink citations (direct download)
        for r in results or []:
            doc_id = r.get('document_id')
            if doc_id is not None:
                r['document_url'] = f'/api/ai/documents/{int(doc_id)}/download'
            else:
                r['document_url'] = None
        return results

    # ==================== WORKFLOW SEARCH TOOLS ====================

    @tool_wrapper
    def search_workflow_docs(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search workflow documentation for how-to guides and tutorials.

        Use this tool when users ask:
        - "How do I add a user?"
        - "How to create a template?"
        - "What are the steps for submitting data?"
        - "Guide me through [workflow]"

        Args:
            query: Search query about a workflow or process
            top_k: Number of results to return (1-10)

        Returns:
            List of matching workflow documents with steps and tour configs
        """
        from app.services.workflow_docs_service import WorkflowDocsService

        top_k = max(1, min(top_k, 10))

        # Get user access level for filtering
        from app.services.authorization_service import AuthorizationService
        user_role = AuthorizationService.access_level(current_user) if current_user.is_authenticated else 'public'

        service = WorkflowDocsService()

        # First try keyword-based search
        workflows = service.search_workflows(query, role=user_role)

        results = []
        for workflow in workflows[:top_k]:
            results.append({
                'workflow_id': workflow.id,
                'title': workflow.title,
                'description': workflow.description,
                'category': workflow.category,
                'roles': workflow.roles,
                'steps': [
                    {
                        'step_number': s.step_number,
                        'title': s.title,
                        'page': s.page,
                        'selector': s.selector,
                        'help': s.help_text,
                        'actionText': s.action_text
                    }
                    for s in workflow.steps
                ],
                'tour_config': workflow.to_tour_config(),
                'summary': service.get_workflow_summary(workflow.id)
            })

        return results

    @tool_wrapper
    def get_workflow_guide(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Get detailed workflow guide by ID.

        Use this when you know the specific workflow ID.

        Args:
            workflow_id: The workflow identifier (e.g., 'add-user', 'submit-data')

        Returns:
            Complete workflow with steps, tour config, and formatted summary
        """
        from app.services.workflow_docs_service import WorkflowDocsService

        service = WorkflowDocsService()
        workflow = service.get_workflow_by_id(workflow_id)

        if not workflow:
            raise ToolExecutionError(f"Workflow not found: {workflow_id}")

        # Check access level
        from app.services.authorization_service import AuthorizationService
        user_role = AuthorizationService.access_level(current_user) if current_user.is_authenticated else 'public'
        if user_role not in ['admin', 'system_manager']:
            if user_role not in workflow.roles and 'all' not in workflow.roles:
                raise ToolExecutionError(f"Access denied to workflow: {workflow_id}")

        return {
            'workflow_id': workflow.id,
            'title': workflow.title,
            'description': workflow.description,
            'category': workflow.category,
            'roles': workflow.roles,
            'prerequisites': workflow.prerequisites,
            'steps': [
                {
                    'step_number': s.step_number,
                    'title': s.title,
                    'page': s.page,
                    'selector': s.selector,
                    'help': s.help_text,
                    'action': s.action,
                    'actionText': s.action_text,
                    'fields': s.fields
                }
                for s in workflow.steps
            ],
            'tips': workflow.tips,
            'tour_config': workflow.to_tour_config(),
            'formatted_summary': service.get_workflow_summary(workflow.id),
            'llm_context': service.format_workflow_for_llm(workflow)
        }

    # ==================== ANALYSIS TOOLS ====================

    @tool_wrapper
    def compare_countries(
        self,
        country_identifiers: List[str],
        indicator_name: str,
        period: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare indicator values across multiple countries.

        Args:
            country_identifiers: List of country names/ISO3 codes
            indicator_name: Name of the indicator to compare
            period: Optional period filter

        Returns:
            Dictionary with comparison results
        """
        if len(country_identifiers) > 10:
            raise ToolExecutionError("Cannot compare more than 10 countries at once")

        comparisons = []

        for country_id in country_identifiers:
            try:
                result = self.get_indicator_value(
                    country_identifier=country_id,
                    indicator_name=indicator_name,
                    period=period
                )

                if result.get('success'):
                    data = result.get('result') or {}
                    comparisons.append({
                        'country': country_id,
                        'value': data.get('total', 0),
                        'records_count': data.get('records_count', 0),
                        'period': period
                    })
            except Exception as e:
                logger.warning("Failed to get data for %s: %s", country_id, e)
                comparisons.append({
                    'country': country_id,
                    'error': 'An error occurred.'
                })

        return {
            'indicator': indicator_name,
            'period': period,
            'countries': comparisons,
            'comparison_count': len(comparisons)
        }

    @tool_wrapper
    def validate_against_guidelines(
        self,
        country_identifier: str,
        indicator_name: str,
        guideline_query: str,
        period: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare indicator value against guidelines found in documents.

        Args:
            country_identifier: Country to check
            indicator_name: Indicator to validate
            guideline_query: Query to find relevant guidelines
            period: Optional period

        Returns:
            Dictionary with actual value, guidelines, and comparison
        """
        # Get actual value
        value_result = self.get_indicator_value(
            country_identifier=country_identifier,
            indicator_name=indicator_name,
            period=period
        )

        if not value_result.get('success'):
            raise ToolExecutionError(f"Failed to get indicator value: {value_result.get('error')}")

        value_data = value_result.get('result') or {}
        actual_value = value_data.get('total', 0)

        # Search for guidelines
        guideline_results = self.search_documents(
            query=guideline_query,
            top_k=3
        )

        if not guideline_results.get('success'):
            raise ToolExecutionError(f"Failed to search guidelines: {guideline_results.get('error')}")

        raw_guidelines = guideline_results.get('result')
        guidelines = raw_guidelines if isinstance(raw_guidelines, list) else []

        return {
            'country': country_identifier,
            'indicator': indicator_name,
            'period': period,
            'actual_value': actual_value,
            'guidelines_found': len(guidelines),
            'guidelines': [
                {
                    'source': chunk.get('document_filename', ''),
                    'page': chunk.get('page_number'),
                    'content': (chunk.get('content') or '')[:500],
                    'similarity': chunk.get('similarity_score', 0)
                }
                for chunk in guidelines
            ]
        }

    # ==================== TOOL DEFINITIONS FOR LLM ====================

    def get_tool_definitions_openai(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions in OpenAI function calling format.

        Returns:
            List of tool definitions
        """
        tool_defs: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "get_indicator_value",
                    "description": "Get the value of a specific INDICATOR from the Indicator Bank for a country (databank). Use for indicator names like 'Number of volunteers', 'Volunteers'. period is optional (e.g. 2024, FY2024 — matched by substring). For listing all indicators IN A FORM ASSIGNMENT use get_assignment_indicator_values; for a specific section/matrix field (e.g. people to be reached) use get_form_field_value. Only cite as SOURCE when records_count > 0 and total is meaningful.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name (e.g., 'Kenya'), ISO3 code (e.g., 'KEN'), or country ID"
                            },
                            "indicator_name": {
                                "type": "string",
                                "description": "Name of the indicator (e.g., 'volunteers', 'blood donations')"
                            },
                            "period": {
                                "type": "string",
                                "description": "Optional period filter (e.g., '2023', 'FY2023', 'Q1 2023')"
                            }
                        },
                        "required": ["country_identifier", "indicator_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_indicator_timeseries",
                    "description": "Get an indicator time series (best available value per year/period) for ONE country from the databank. Use when the user asks for 'over time', 'trend', 'by year', 'time series'. Returns points with year + value, suitable for rendering a line chart. include_saved=true includes draft/saved values when a country hasn't submitted the latest cycle yet (flagged via data_status).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name (e.g., 'Syria'), ISO3 code (e.g., 'SYR'), or country ID"
                            },
                            "indicator_name": {
                                "type": "string",
                                "description": "Name of the indicator (e.g., 'volunteers', 'Number of people volunteering')"
                            },
                            "limit_periods": {
                                "type": "integer",
                                "description": "Max number of year points to return (default 12, max 50).",
                                "default": 12
                            },
                            "include_saved": {
                                "type": "boolean",
                                "description": "If true, include saved/draft values when no submitted value exists for that year (default true).",
                                "default": True
                            }
                        },
                        "required": ["country_identifier", "indicator_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_form_field_value",
                    "description": "Get value(s) for a specific form SECTION or matrix FIELD (e.g. people to be reached, longer term programmes). Use when the user asks for a named section/field; for listing ALL indicators in an assignment use get_assignment_indicator_values. Handles indicators (with disaggregation), questions (numeric or text), and matrix tables. period = matrix ROW/key filter (e.g. 2027); assignment_period = which assignment (e.g. 2025, 2023-2024, FY2024 — any format, matched by substring). Returns total, breakdown, optional text_values. Only cite as SOURCE when records_count > 0 and data is meaningful.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name (e.g., 'Bangladesh'), ISO3 code (e.g., 'BGD'), or country ID"
                            },
                            "field_label_or_name": {
                                "type": "string",
                                "description": "Section name or form item label (e.g., 'people to be reached', 'Longer term programmes')"
                            },
                            "period": {
                                "type": "string",
                                "description": "Matrix row/key filter (e.g., '2027') — which row in the table to sum; NOT the assignment period"
                            },
                            "assignment_period": {
                                "type": "string",
                                "description": "Optional assignment period (e.g. 2025, 2023-2024, FY2024, Jan 2024) — matched by substring"
                            }
                        },
                        "required": ["country_identifier", "field_label_or_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_country_information",
                    "description": "Get comprehensive information about ONE country (assignments, deadlines, recent activity). Use when the user asks about a specific country. Do NOT call this once per country to build a map or list of countries in a region (e.g. 'UPR countries in MENA') — use get_upr_kpi_values_for_all_countries, get_indicator_values_for_all_countries, or list_documents and filter by region instead.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name, ISO3 code, or ID"
                            }
                        },
                        "required": ["country_identifier"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_indicator_values_for_all_countries",
                    "description": "Get indicator values from the databank (Indicator Bank / FDRS) for ALL countries in one call. PRIMARY source for volunteers, staff, branches, local units: call this FIRST for those metrics. Use for list/table across countries. When the user asks for countries above a threshold (e.g. 'more than 10000 volunteers'), pass min_value so the tool returns only those countries — then display every row. After this, use get_upr_kpi_values_for_all_countries only to fill gaps (countries with no FDRS value) unless the user explicitly asked for 'from UPR' or 'from documents'. Do NOT use if the user asked for 'documents only' or 'from reports only'. Each row includes a 'region' field (operational region: Asia Pacific, MENA, Europe & CA, Africa, Americas). When the user asks for 'continent', that means operational region — use this field only; do not add a separate continent column or use geographic continents from model knowledge.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indicator_name": {
                                "type": "string",
                                "description": "Name of the indicator (e.g. 'Number of volunteers', 'Volunteers')"
                            },
                            "period": {
                                "type": "string",
                                "description": "Optional period filter (e.g. '2023', 'FY2023')"
                            },
                            "min_value": {
                                "type": "number",
                                "description": "Optional. Return only rows where value >= min_value. Use for threshold queries: e.g. 10001 for 'more than 10000', 10000 for 'at least 10000'. The backend filters; you display every row returned."
                            }
                        },
                        "required": ["indicator_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_documents",
                    "description": "List AI-processed documents by metadata (title/filename/country). Use when the user asks which documents exist (e.g. 'which countries have UPL-2026 PDFs?'). The 'query' parameter is matched as a single substring (contains) on title and filename — do NOT use 'OR' or multiple terms; use one term e.g. 'UPL-' or 'Unified Plan'. For Unified Plan documents use 'UPL-' or 'Unified Plan' (not 'UPR'). This is cheaper and more reliable than chunk search for inventory. Do NOT use when you need to read document text (use search_documents for that). When presenting results, ALWAYS include total count (result.total) and a numbered list (1., 2., 3., …). If total > limit, say you're showing a subset (e.g. 'Showing 200 of 374').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Optional text to match in document title/filename (e.g. 'UPL-2026', 'Unified Plan 2026')."
                            },
                            "country_identifier": {
                                "type": "string",
                                "description": "Optional country filter (country name, ISO3, or ID)."
                            },
                            "status": {
                                "type": "string",
                                "description": "Optional processing status filter: pending, processing, completed, failed."
                            },
                            "file_type": {
                                "type": "string",
                                "description": "Optional file type filter: pdf, docx, xlsx, txt, md."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results to return (1-500).",
                                "default": 200
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Pagination offset.",
                                "default": 0
                            },
                            "include_metadata": {
                                "type": "boolean",
                                "description": "If true, include document metadata JSON. Default false to keep payload small.",
                                "default": False
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": "Search through uploaded documents (PDFs, reports, plans) by retrieving relevant chunks with FULL text content. The LLM must read all chunk content and decide the answer; this tool only fetches data. Use for factual questions and when user wants document evidence. For inventory/listing tasks (which documents exist), prefer list_documents instead. Do NOT use if the user asked for 'databank only'. IMPORTANT: For questions that ask which countries or which National Societies (e.g. 'which National Societies prioritise X', 'which countries mention Y in their plans'), you MUST set return_all_countries=True and fetch all batches (offset=0, then offset=limit, etc.) so results span many countries; otherwise you may get only one country's document. When return_all_countries=True you receive batches: call with offset=0 first, then offset=limit, offset=2*limit, ... until you have read all total_count chunks. Each chunk has full 'content'; you must read it to decide which countries/sources apply.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Short, focused search phrase only (e.g. 'social protection', 'PGI minimum standards', 'volunteers Syria'). Do NOT paste the full user message or concatenate unrelated terms."
                            },
                            "country_identifier": {
                                "type": "string",
                                "description": "Optional: filter by country. Ignored if return_all_countries is True."
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results (1-20 normally; when return_all_countries=True the backend uses a larger list).",
                                "default": 5
                            },
                            "return_all_countries": {
                                "type": "boolean",
                                "description": "If true, search across all countries and return results in batches. You MUST call repeatedly with offset=0, then offset=limit, etc. until you have received all total_count chunks and read their content.",
                                "default": False
                            },
                            "offset": {
                                "type": "integer",
                                "description": "For pagination: skip this many chunks. Use 0 for first batch, then offset+limit for next, until offset >= total_count.",
                                "default": 0
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max chunks per call (default set by backend). When return_all_countries=True, use limit from the previous response and keep calling with offset += limit until done."
                            },
                            "document_type": {
                                "type": "string",
                                "description": "Optional filter by file type (pdf, docx, xlsx, etc.)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_countries",
                    "description": "Compare indicator values across multiple countries for the same indicator and period.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifiers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of country names or ISO3 codes to compare"
                            },
                            "indicator_name": {
                                "type": "string",
                                "description": "Name of the indicator to compare"
                            },
                            "period": {
                                "type": "string",
                                "description": "Optional period filter"
                            }
                        },
                        "required": ["country_identifiers", "indicator_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_against_guidelines",
                    "description": "Compare an indicator value against guidelines or standards found in policy documents.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country to validate"
                            },
                            "indicator_name": {
                                "type": "string",
                                "description": "Indicator to check"
                            },
                            "guideline_query": {
                                "type": "string",
                                "description": "Query to find relevant guidelines (e.g., 'WHO volunteer standards', 'blood donation safety requirements')"
                            },
                            "period": {
                                "type": "string",
                                "description": "Optional period"
                            }
                        },
                        "required": ["country_identifier", "indicator_name", "guideline_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_assignments",
                    "description": "Get form assignments for a country, optionally filtered by status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name or ISO3 code"
                            },
                            "status": {
                                "type": "string",
                                "description": "Optional status filter: 'Pending', 'Submitted', 'Approved', etc."
                            }
                        },
                        "required": ["country_identifier"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_assignment_indicator_values",
                    "description": "List ALL indicator values reported in a form assignment (country + template + period). Use for 'FDRS 2024 Syria indicators', 'what did Syria report for FDRS 2024', 'list indicators in Unified Plan 2025'. period matches any assignment period containing the string: single year (2024), year range (2023-2024), fiscal (FY2024), month range (Jan 2024). For a SPECIFIC section or matrix field name (e.g. people to be reached) use get_form_field_value instead. Do NOT use search_documents for assignment/form data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_identifier": {
                                "type": "string",
                                "description": "Country name (e.g. 'Syria'), ISO3 (e.g. 'SYR'), or ID"
                            },
                            "template_identifier": {
                                "type": "string",
                                "description": "Template name (e.g. 'FDRS', 'Unified Plan') or ID"
                            },
                            "period": {
                                "type": "string",
                                "description": "Optional period (e.g. 2024, 2023-2024, FY2024) — matched by substring in assignment period_name"
                            }
                        },
                        "required": ["country_identifier", "template_identifier"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_indicator_metadata",
                    "description": "Get detailed metadata about an indicator including definition, unit of measurement, and related sectors.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indicator_name": {
                                "type": "string",
                                "description": "Name of the indicator"
                            }
                        },
                        "required": ["indicator_name"]
                    }
                }
            }
        ]
        tool_defs.extend(UPR_TOOL_SPECS)

        sources_norm = resolve_source_config()

        if sources_norm is None:
            return tool_defs

        docs_enabled = bool(sources_norm.get("system_documents") or sources_norm.get("upr_documents"))
        allowed: set[str] = set()

        if sources_norm.get("historical"):
            allowed.update(
                {
                    "get_indicator_value",
                    "get_indicator_timeseries",
                    "get_form_field_value",
                    "get_country_information",
                    "get_indicator_values_for_all_countries",
                    "compare_countries",
                    "get_user_assignments",
                    "get_assignment_indicator_values",
                    "get_indicator_metadata",
                }
            )

        if docs_enabled:
            allowed.update({"list_documents", "search_documents", "analyze_unified_plans_focus_areas"})

        if sources_norm.get("upr_documents"):
            allowed.update(UPR_KPI_TOOL_NAMES)

        # This tool requires both sources (it reads structured values and guideline documents).
        if sources_norm.get("historical") and docs_enabled:
            allowed.add("validate_against_guidelines")

        def _tool_name(td: Dict[str, Any]) -> Optional[str]:
            try:
                fn = td.get("function") if isinstance(td, dict) else None
                if isinstance(fn, dict):
                    return str(fn.get("name") or "").strip() or None
            except Exception as e:
                logger.debug("_fn_name fallback failed: %s", e)
                return None
            return None

        filtered = [td for td in tool_defs if (_tool_name(td) in allowed)]
        if not filtered:
            logger.warning(
                "SECURITY: Source filtering produced empty tool list (allowed=%s). "
                "Returning empty list instead of exposing all tools.",
                allowed,
            )
        return filtered

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool by name with given parameters.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        # Get the tool method
        if not hasattr(self, tool_name):
            raise ToolExecutionError(f"Unknown tool: {tool_name}")

        tool_method = getattr(self, tool_name)

        # Execute the tool
        return tool_method(**kwargs)
