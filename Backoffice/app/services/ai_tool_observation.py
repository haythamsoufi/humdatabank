"""
Tool observation compaction helpers for agent loops.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from flask import current_app

logger = logging.getLogger(__name__)

_TOOL_OBSERVATION_MAX_CHARS_DEFAULT = 20000
# Default cap for document search observations to control LLM input cost (~30k tokens).
# Override with AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH (min 50k, max 500k).
_DOCUMENT_SEARCH_MAX_CHARS_DEFAULT = 120000
# When truncating, max chars per chunk's content so we keep more chunks, less content each.
_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK = 500
OBSERVATION_PREVIEW_GENERIC_LIST = 50
# Max rows to send in indicator/UPR "all countries" tool results. Higher values support full country tables.
_ROWS_RESULT_MAX_ROWS_DEFAULT = 250
_ROWS_RESULT_MAX_ROWS_CAP = 2000

# Fields to keep when sending search chunks to the LLM (reduces payload size).
# Dropped: chunk_id, chunk_index, document_country_id, document_geographic_scope (use document_country_name
# for global/primary scope), document_type, document_filename (kept document_title), is_api_import,
# is_system_document, metadata, section_title, similarity_score, vector_score, keyword_score, source_boost, token_count.
# document_countries added back only for multi-country docs (slimmed to iso3+name per country).
_SEARCH_CHUNK_KEYS_FOR_LLM = (
    "content",
    "document_country_iso3",
    "document_country_name",
    "document_title",
    "document_url",
    "page_number",
    "score",
)

_SENTENCE_END_RE = __import__("re").compile(r"[.!?]\s")


def _truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
    """Truncate text to approximately max_chars, preferring to cut at sentence boundaries."""
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    last_match = None
    for m in _SENTENCE_END_RE.finditer(window):
        last_match = m
    if last_match and last_match.end() > max_chars * 0.5:
        return window[:last_match.end()].rstrip()
    return window


def _slim_search_chunk(r: Dict[str, Any]) -> Dict[str, Any]:
    """Return a minimal chunk dict for the LLM: content + citation fields + one score."""
    if not isinstance(r, dict):
        return r
    score = r.get("combined_score") if r.get("combined_score") is not None else r.get("similarity_score") or r.get("keyword_score")
    slim = {k: r.get(k) for k in _SEARCH_CHUNK_KEYS_FOR_LLM if k != "score"}
    slim["score"] = score
    # Prefer document_title; fall back to document_filename for citation
    if slim.get("document_title") is None and r.get("document_filename"):
        slim["document_title"] = r.get("document_filename")
    # Multi-country docs: include document_countries so the LLM can cite "covers Syria, Lebanon, ..."
    # Slim to iso3+name only (no id). Omit when single country (document_country_* already have it).
    countries = r.get("document_countries")
    if isinstance(countries, list) and len(countries) > 1:
        slim["document_countries"] = [
            {"iso3": c.get("iso3"), "name": c.get("name")}
            for c in countries
            if isinstance(c, dict)
        ]
    return slim


def compact_tool_observation_for_llm(
    *,
    tool_name: str,
    tool_result: Any,
    max_chars: Optional[int] = None,
) -> str:
    """
    Convert a tool_result into a compact JSON string suitable for the next LLM prompt.
    """
    limit = int(max_chars or current_app.config.get("AI_TOOL_OBSERVATION_MAX_CHARS", _TOOL_OBSERVATION_MAX_CHARS_DEFAULT))
    limit = max(2000, min(limit, 200000))

    def _dumps(obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
        except Exception as e:
            logger.debug("Tool observation JSON serialization failed: %s", e)
            return json.dumps({"_unserializable": True, "repr": str(obj)[:2000]}, ensure_ascii=False)

    if isinstance(tool_result, dict):
        payload = tool_result
    else:
        payload = {"result": tool_result}

    try:
        if tool_name in ("search_documents", "search_documents_hybrid"):
            raw = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(raw, dict) and "result" in raw:
                results = raw.get("result") if isinstance(raw.get("result"), list) else []
                total_count = int(raw.get("total_count", len(results)))
                offset = int(raw.get("offset", 0))
                limit = int(raw.get("limit", len(results)))
                inner_success = raw.get("success", True)
            else:
                results = raw if isinstance(raw, list) else []
                total_count = int(payload.get("total_count", len(results))) if isinstance(payload, dict) else len(results)
                offset = int(payload.get("offset", 0)) if isinstance(payload, dict) else 0
                limit = int(payload.get("limit", len(results))) if isinstance(payload, dict) else len(results)
                inner_success = True
            doc_search_limit = int(
                current_app.config.get("AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH", _DOCUMENT_SEARCH_MAX_CHARS_DEFAULT)
            )
            doc_search_limit = max(50_000, min(doc_search_limit, 500_000))

            # Always send slim chunks to the LLM (content + citation fields + score only).
            slim_results = [_slim_search_chunk(r) for r in results]

            full_observation = {
                "success": bool(payload.get("success", True)) and inner_success if isinstance(payload, dict) else inner_success,
                "result": slim_results,
                "total_count": total_count,
                "offset": offset,
                "limit": limit,
            }
            s = _dumps(full_observation)
            if len(s) <= doc_search_limit:
                return s
            # Over limit: truncate each chunk's content so we keep more chunks, fewer chars each.
            max_content = int(
                current_app.config.get("AI_TOOL_OBSERVATION_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK", _DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK)
            )
            max_content = max(200, min(max_content, 2000))
            compact_results = []
            for r in slim_results:
                if not isinstance(r, dict):
                    compact_results.append(r)
                    continue
                cp = dict(r)
                content = (cp.get("content") or "")
                if len(content) > max_content:
                    cp["content"] = _truncate_at_sentence_boundary(content, max_content) + "…"
                    cp["content_truncated"] = True
                compact_results.append(cp)
            compact_observation = {
                "success": full_observation["success"],
                "result": compact_results,
                "total_count": total_count,
                "offset": offset,
                "limit": limit,
                "note": "Chunk content was truncated for length; use document_country_iso3, document_country_name, document_title, document_url to identify sources.",
            }
            return _dumps(compact_observation)

        if tool_name == "list_documents" and isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict) and isinstance(result.get("documents"), list):
                docs = result.get("documents", [])
                total = result.get("total", len(docs))
                by_iso3: Dict[str, Dict[str, Any]] = {}
                regions_seen: set = set()
                for doc in docs:
                    if not isinstance(doc, dict):
                        continue
                    primary_iso3 = str(doc.get("country_iso3") or "").strip().upper()
                    if len(primary_iso3) != 3 or not primary_iso3.isalpha():
                        continue
                    primary_name = (doc.get("country_name") or "").strip()
                    region = ""
                    countries_list = doc.get("countries") or []
                    for c in countries_list:
                        if isinstance(c, dict) and str(c.get("iso3") or "").strip().upper() == primary_iso3:
                            region = (c.get("region") or "").strip()
                            break
                    if region:
                        regions_seen.add(region)
                    plan_year = doc.get("plan_year")
                    if isinstance(plan_year, int) and 2000 <= plan_year <= 2100:
                        iso3s_to_update = {primary_iso3}
                        for c in countries_list:
                            if isinstance(c, dict):
                                iso3 = str(c.get("iso3") or "").strip().upper()
                                if len(iso3) == 3 and iso3.isalpha():
                                    iso3s_to_update.add(iso3)
                        for iso3 in iso3s_to_update:
                            name = primary_name if iso3 == primary_iso3 else next((c.get("name") or iso3 for c in countries_list if isinstance(c, dict) and str(c.get("iso3") or "").strip().upper() == iso3), iso3)
                            r = region if iso3 == primary_iso3 else next((str(c.get("region") or "").strip() for c in countries_list if isinstance(c, dict) and str(c.get("iso3") or "").strip().upper() == iso3), "")
                            if r:
                                regions_seen.add(r)
                            if iso3 not in by_iso3:
                                by_iso3[iso3] = {"iso3": iso3, "name": name or iso3, "region": r, "latest_plan_year": plan_year}
                            else:
                                existing = by_iso3[iso3].get("latest_plan_year")
                                if existing is None or plan_year > existing:
                                    by_iso3[iso3]["latest_plan_year"] = plan_year
                                    by_iso3[iso3]["name"] = name or by_iso3[iso3].get("name") or iso3
                                    if r:
                                        by_iso3[iso3]["region"] = r
                    elif primary_iso3 not in by_iso3:
                        by_iso3[primary_iso3] = {"iso3": primary_iso3, "name": primary_name or primary_iso3, "region": region}
                regions_present = sorted(regions_seen)
                countries_by_region: Dict[str, Any] = {}
                for iso3, info in by_iso3.items():
                    r = info.get("region") or "(no region)"
                    if r not in countries_by_region:
                        countries_by_region[r] = []
                    entry: Dict[str, Any] = {"iso3": iso3, "name": info.get("name") or iso3}
                    if info.get("latest_plan_year") is not None:
                        entry["latest_plan_year"] = info["latest_plan_year"]
                    countries_by_region[r].append(entry)
                compact_ld = {
                    "success": bool(payload.get("success", True)),
                    "total": total,
                    "regions_present": regions_present,
                    "countries_by_region": countries_by_region,
                    "unique_countries_count": len(by_iso3),
                    "note": "Use regions_present and countries_by_region to filter by region (e.g. MENA). Each country may include latest_plan_year (most recent UPL year). Do not call list_documents again; produce your answer and map from this summary.",
                }
                s_ld = _dumps(compact_ld)
                if len(s_ld) <= limit:
                    return s_ld
                compact_ld["countries_by_region"] = {r: len(cs) for r, cs in countries_by_region.items()}
                compact_ld["note"] = "Regions and country counts above. Filter by the user's region (e.g. MENA); the backend will build the map from the full result."
                return _dumps(compact_ld)[:limit]

        # Focus-area analysis: slim to one row per country (most recent plan) so the
        # full country list survives compaction.  The platform renders a complete table.
        result = payload.get("result") if isinstance(payload, dict) else None
        if tool_name == "analyze_unified_plans_focus_areas" and isinstance(result, dict):
            countries_grouped = result.get("countries_grouped") or []
            _fa_row_count = len(countries_grouped)
            slim_countries = []
            for cg in countries_grouped:
                if not isinstance(cg, dict):
                    continue
                plans = cg.get("plans") or []
                latest = plans[0] if plans else {}
                area_details = latest.get("area_details") or {}
                terms: list[str] = []
                evidence = 0
                for ad in area_details.values():
                    if isinstance(ad, dict):
                        terms.extend(ad.get("matched_terms") or [])
                        evidence += int(ad.get("evidence_chunks") or 0)
                seen_lower: dict[str, str] = {}
                for t in terms:
                    key = t.strip().lower()
                    if key and key not in seen_lower:
                        seen_lower[key] = t.strip()
                slim_countries.append({
                    "name": cg.get("country_name"),
                    "iso3": cg.get("country_iso3"),
                    "year": latest.get("plan_year"),
                    "doc": latest.get("document_title"),
                    "url": latest.get("document_url"),
                    "terms": ", ".join(seen_lower.values()),
                    "evidence": evidence,
                    "plans_count": len(plans),
                })
            _fa_platform_note = (
                f"CRITICAL INSTRUCTION — NO MARKDOWN TABLE and NO FURTHER TOOL CALLS: "
                f"The platform ALREADY renders a complete, sortable, interactive table with "
                f"ALL {_fa_row_count} countries and their plan details (country, plan year, "
                f"document link, matched terms, evidence strength). You MUST NOT output any "
                f"markdown table. Do NOT call search_documents after this — the analysis "
                f"already covers all Unified Plans and is sufficient. FINISH NOW. "
                f"Your ONLY job is to output: (1) a brief textual summary (total countries, "
                f"common themes/terms, regional patterns, caveats about lexical matching), "
                f"then (2) end with '## Sources' on its own line followed by a bullet list."
            )
            compact_fa = {
                "success": True,
                "total_plans": result.get("total_plans"),
                "plans_analyzed": result.get("plans_analyzed"),
                "countries_with_matches": _fa_row_count,
                "areas_queried": list((result.get("counts_by_area") or {}).keys()),
                "counts_by_area": result.get("counts_by_area"),
                "countries": slim_countries,
                "note": _fa_platform_note,
            }
            return _dumps(compact_fa)

        # Indicator / UPR "all countries" results: always handle these tools to avoid
        # aggressive generic truncation that would cut rows mid-JSON and cause the LLM
        # to see an incomplete dataset (leading to inconsistent country counts between runs).
        result = payload.get("result") if isinstance(payload, dict) else None
        if (
            isinstance(result, dict)
            and "rows" in result
            and isinstance(result.get("rows"), list)
            and tool_name in (
                "get_indicator_values_for_all_countries",
                "get_upr_kpi_values_for_all_countries",
            )
        ):
            rows = result["rows"]
            max_rows = int(
                current_app.config.get("AI_TOOL_OBSERVATION_MAX_ROWS_TABLE_RESULT", _ROWS_RESULT_MAX_ROWS_DEFAULT)
            )
            max_rows = max(50, min(max_rows, _ROWS_RESULT_MAX_ROWS_CAP))

            # Slim each row: remove per-row fields that are constant across all rows
            # (indicator_id, indicator_name_resolved) to reduce payload size.
            _INDICATOR_ROW_DROP_KEYS = {"indicator_id", "indicator_name_resolved"}
            slim_rows = [
                {k: v for k, v in r.items() if k not in _INDICATOR_ROW_DROP_KEYS}
                for r in rows
            ] if isinstance(rows[0], dict) else rows

            compact_result = dict(result)
            _row_count = len(slim_rows)
            _platform_note = (
                f"CRITICAL INSTRUCTION — NO MARKDOWN TABLE: The platform ALREADY renders a "
                f"complete, sortable, interactive table with ALL {_row_count} rows and all "
                f"requested columns (operational region from platform data, estimated income group, "
                f"population, and proportion when the user asked for them). "
                f"You MUST NOT output any markdown table — not a full table, not a partial "
                f"table, not even the first 10 rows. Any markdown table you output will be "
                f"stripped by the system and wasted. "
                f"Your ONLY job is to output: (1) a brief textual summary (top 5 countries "
                f"with values, bottom 5, total/sum, regional patterns, caveats about estimated "
                f"data — all in prose, NOT in a table), then (2) end with '## Sources' on its "
                f"own line followed by a bullet list of sources. Nothing else."
            )
            if len(slim_rows) > max_rows:
                compact_result["rows"] = slim_rows[:max_rows]
                compact_result["rows_truncated"] = True
                compact_result["total_rows"] = len(slim_rows)
                compact_result["note"] = (
                    f"Showing first {max_rows} of {len(slim_rows)} rows (full data rendered by platform). "
                    + _platform_note
                )
            else:
                compact_result["rows"] = slim_rows
                compact_result["note"] = (
                    f"All {_row_count} rows included. " + _platform_note
                )

            # Strip verbose alternative_indicators from the result to save tokens.
            if "alternative_indicators" in compact_result and isinstance(compact_result.get("alternative_indicators"), list):
                compact_result["alternative_indicators"] = [
                    {"id": a.get("id"), "name": a.get("name"), "records_count": a.get("records_count")}
                    for a in compact_result["alternative_indicators"]
                    if isinstance(a, dict)
                ][:5]

            compact_payload = {**payload, "result": compact_result} if isinstance(payload, dict) else {"result": compact_result}
            return _dumps(compact_payload)

        s0 = _dumps(payload)
        if len(s0) <= limit:
            return s0

        result = payload.get("result") if isinstance(payload, dict) else None
        compact: Dict[str, Any] = {"success": payload.get("success", True)} if isinstance(payload, dict) else {}

        if isinstance(result, list):
            preview_n = OBSERVATION_PREVIEW_GENERIC_LIST
            compact["result_count"] = len(result)
            compact["result_preview"] = result[:preview_n]
            compact["truncated"] = len(result) > preview_n
        elif isinstance(result, dict):
            compact["result_keys"] = list(result.keys())[:50]
            compact["result_preview"] = {k: result.get(k) for k in list(result.keys())[:15]}
            compact["truncated"] = True
        else:
            compact["preview"] = str(payload)[:4000]
            compact["truncated"] = True

        s1 = _dumps(compact)
        if len(s1) <= limit:
            return s1
        return _dumps({"truncated": True, "preview": s1[: max(1000, limit - 200)], "original_length": len(s0)})
    except Exception as e:
        logger.warning("Tool observation compaction failed for %s: %s", tool_name, e, exc_info=True)
        text = str(tool_result)
        return _dumps({"truncated": True, "preview": text[: max(1000, limit - 200)], "original_length": len(text)})
