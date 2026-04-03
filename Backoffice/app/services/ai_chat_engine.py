from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import current_app
from flask_babel import force_locale, gettext as _

from app.utils.ai_utils import openai_model_supports_sampling_params
from app.routes.chatbot import (
    build_lightweight_system_prompt,
    format_ai_response_for_html,
    integrate_openai_with_telemetry,
)

logger = logging.getLogger(__name__)

def _ai_debug_enabled() -> bool:
    try:
        v = current_app.config.get("AI_CHAT_DEBUG_LOGS", None)
        if v is not None:
            return bool(v)
    except Exception as e:
        logger.debug("AI_CHAT_DEBUG_LOGS config check failed: %s", e)
    raw = (os.getenv("AI_CHAT_DEBUG_LOGS") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _coerce_history_messages(
    conversation_history: Optional[List[Dict[str, Any]]],
    *,
    limit: int,
) -> List[Dict[str, str]]:
    """
    Convert stored history entries to provider-agnostic chat messages.

    Accepts both shapes (best-effort):
    - {"isUser": bool, "message": str}  (Backoffice DB / legacy)
    - {"role": "user"|"assistant", "content": str}  (Website / OpenAI-style)
    """
    history = conversation_history or []
    out: List[Dict[str, str]] = []
    if not history:
        return out

    for entry in history[-int(limit) :]:
        content = (entry.get("message") or entry.get("content") or "").strip()
        if not content:
            continue
        # Normalize role: isUser -> user, or explicit role
        is_user = entry.get("isUser")
        if is_user is None:
            role = (entry.get("role") or "").strip().lower()
            is_user = role == "user"
        # Privacy: scrub obvious PII from any stored history before sending to providers.
        try:
            from app.services.ai_providers import scrub_pii_text
            content = scrub_pii_text(content)
        except Exception as e:
            logger.debug("PII scrubbing failed: %s", e)
        if is_user:
            out.append({"role": "user", "content": content})
        else:
            out.append({"role": "assistant", "content": content})
    return out


_WORLDMAP_TRIGGER_RE = re.compile(
    r"\b("
    r"generate\s+world\s*map\s+queries?|"
    r"generate\s+worldmap\s+queries?|"
    r"heat\s*map|heatmap|"
    r"world\s*map|worldmap|"
    r"choropleth|map\s+visual(?:ization)?|"
    r"map\s+of|"
    r"(?:show|give|get|display|generate|want|need)\s+(?:me\s+)?(?:a\s+)?map\b"
    r")\b",
    re.IGNORECASE,
)
# Region + UPL/documents: "MENA countries with UPL", "which countries in Europe have Unified Plan" -> treat as map request so first reply gets a map
_WORLDMAP_IMPLICIT_RE = re.compile(
    r"(?=.*(?:MENA|Europe|Africa|Americas|Asia\s+Pacific))"
    r"(?=.*(?:countries?|list|which))"
    r"(?=.*(?:UPL|Unified\s+Plan))",
    re.IGNORECASE | re.DOTALL,
)
_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)

_TIMESERIES_TRIGGER_RE = re.compile(
    r"\b("
    r"over\s*time|over\s+the\s+years|"
    r"time\s*series|timeseries|"
    r"trend|trends|"
    r"by\s+year|year\s+over\s+year|yoy|"
    r"overtime"
    r")\b",
    re.IGNORECASE,
)


def _wants_worldmap_payload(text: Optional[str]) -> bool:
    if not text:
        return False
    s = str(text).strip()
    if _WORLDMAP_TRIGGER_RE.search(s):
        return True
    # Region + UPL/documents list -> treat as map request so first reply includes map
    if _WORLDMAP_IMPLICIT_RE.search(s):
        return True
    return False

def _wants_timeseries_chart(text: Optional[str]) -> bool:
    return bool(text and _TIMESERIES_TRIGGER_RE.search(str(text)))

_WORLDMAP_PAYLOAD_INSTRUCTION = (
    "If the user asks for world map queries or a world map visual, include a JSON code block "
    "that contains map payload data using this exact shape:\n"
    "```json\n"
    '{"map_payload":{"type":"worldmap","title":"<short title>","metric":"<metric label>",'
    '"countries":[{"iso3":"KEN","value":123,"label":"Kenya","year":2024}]}}\n'
    "```\n"
    "Rules: ISO3 must be 3-letter uppercase country codes, value must be numeric, "
    "year should be a 4-digit year when known, and include only countries with numeric values."
)


def _coerce_map_payload(raw_payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return None
    payload = raw_payload.get("map_payload") if isinstance(raw_payload.get("map_payload"), dict) else raw_payload
    if not isinstance(payload, dict):
        return None

    map_type = str(payload.get("type") or payload.get("map_type") or "").strip().lower()
    if map_type and map_type not in {"worldmap", "world_map", "choropleth"}:
        return None

    rows = payload.get("countries")
    if not isinstance(rows, list):
        rows = payload.get("locations")
    if not isinstance(rows, list):
        rows = payload.get("data")
    if not isinstance(rows, list):
        # Accept feature_values: [{"iso3": "DZA", "value": 1}, ...]
        rows = payload.get("feature_values")
    if not isinstance(rows, list):
        return None

    def _extract_year(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            if isinstance(value, int) and 1900 <= value <= 2100:
                return int(value)
            if isinstance(value, float) and 1900.0 <= value <= 2100.0:
                return int(value)
            s = str(value)
        except Exception as e:
            logger.debug("_extract_year parse failed: %s", e)
            return None
        if not s:
            return None
        try:
            import re
            years = re.findall(r"\b(19\d{2}|20\d{2})\b", s)
            if not years:
                return None
            return max(int(y) for y in years)
        except Exception as e:
            logger.debug("_extract_year years parse failed: %s", e)
            return None

    countries: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        iso3 = str(row.get("iso3") or row.get("country_iso3") or row.get("code") or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        try:
            value = float(row.get("value"))
        except Exception as e:
            logger.debug("row value float failed: %s", e)
            continue
        label = str(row.get("label") or row.get("name") or row.get("country_name") or iso3).strip()[:120]
        year = _extract_year(row.get("year")) or _extract_year(row.get("period_used")) or _extract_year(payload.get("period"))
        region = str(row.get("region") or "").strip() or None
        obj: Dict[str, Any] = {"iso3": iso3, "value": value, "label": label}
        if year is not None:
            obj["year"] = int(year)
        if region:
            obj["region"] = region
        countries.append(obj)

    if not countries:
        return None

    return {
        "type": "worldmap",
        "title": str(payload.get("title") or "World map").strip()[:160],
        "metric": str(payload.get("metric") or payload.get("value_field") or "value").strip()[:120],
        "countries": countries,
    }


def _coerce_chart_payload(raw_payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return None
    payload = raw_payload.get("chart_payload") if isinstance(raw_payload.get("chart_payload"), dict) else raw_payload
    if not isinstance(payload, dict):
        return None
    chart_type = str(payload.get("type") or payload.get("chart_type") or "").strip().lower()
    if chart_type and chart_type not in {"line", "linechart", "timeseries"}:
        return None
    rows = payload.get("series") or payload.get("data") or payload.get("points")
    if not isinstance(rows, list):
        return None
    pts: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        x = r.get("x", r.get("year"))
        y = r.get("y", r.get("value"))
        try:
            xx = int(float(x))
            yy = float(y)
        except Exception as e:
            logger.debug("xy parse failed: %s", e)
            continue
        if xx < 1900 or xx > 2100:
            continue
        obj: Dict[str, Any] = {"x": int(xx), "y": float(yy)}
        if r.get("data_status") is not None:
            obj["data_status"] = str(r.get("data_status"))
        if r.get("period_name") is not None:
            obj["period_name"] = str(r.get("period_name"))
        pts.append(obj)
    if not pts:
        return None
    pts.sort(key=lambda p: int(p.get("x") or 0))
    metric = str(payload.get("metric") or payload.get("y_label") or "Value").strip()[:120] or "Value"
    title = str(payload.get("title") or f"{metric} over time").strip()[:180] or f"{metric} over time"
    country = str(payload.get("country") or "").strip()[:160] or None
    return {
        "type": "line",
        "title": title,
        "metric": metric,
        "country": country,
        "x": "year",
        "y_label": metric,
        "series": pts,
    }


def _map_payload_from_answer_content(answer_content: Any, output_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Best-effort map payload builder from normalized answer content."""
    if str(output_hint or "").strip().lower() not in {"map", "worldmap", "choropleth", ""}:
        return None
    if not isinstance(answer_content, dict):
        return None
    kind = str(answer_content.get("kind") or "").strip().lower()
    rows = answer_content.get("rows")
    if kind == "per_country_values" and isinstance(rows, list):
        countries = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            iso3 = str(row.get("iso3") or "").strip().upper()
            if len(iso3) != 3 or not iso3.isalpha():
                continue
            try:
                value = float(row.get("value"))
            except Exception as e:
                logger.debug("table row value float failed: %s", e)
                continue
            item: Dict[str, Any] = {
                "iso3": iso3,
                "value": value,
                "label": str(row.get("label") or iso3).strip()[:120],
            }
            try:
                y = int(row.get("year")) if row.get("year") is not None else None
                if y and 1900 <= y <= 2100:
                    item["year"] = y
            except Exception as e:
                logger.debug("Row year parse failed: %s", e)
            countries.append(item)
        if countries:
            return {
                "type": "worldmap",
                "title": "World map",
                "metric": str(answer_content.get("metric") or "Value")[:120],
                "countries": countries,
            }
    return None


def _chart_payload_from_answer_content(answer_content: Any, output_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Best-effort chart payload builder from normalized answer content."""
    if str(output_hint or "").strip().lower() not in {"chart", "line", "timeseries", ""}:
        return None
    if not isinstance(answer_content, dict):
        return None
    kind = str(answer_content.get("kind") or "").strip().lower()
    if kind != "time_series":
        return None
    series = answer_content.get("series")
    if not isinstance(series, list):
        return None
    pts = []
    for p in series:
        if not isinstance(p, dict):
            continue
        try:
            x = int(float(p.get("x", p.get("year"))))
            y = float(p.get("y", p.get("value")))
        except Exception as e:
            logger.debug("point xy parse failed: %s", e)
            continue
        if 1900 <= x <= 2100:
            pts.append({"x": x, "y": y})
    if not pts:
        return None
    pts.sort(key=lambda i: int(i.get("x") or 0))
    metric = str(answer_content.get("metric") or "Value").strip()[:120] or "Value"
    country = str(answer_content.get("country") or "").strip()[:160] or None
    title = f"{metric} over time" if not country else f"{metric} in {country} over time"
    return {
        "type": "line",
        "title": title[:180],
        "metric": metric,
        "country": country,
        "x": "year",
        "y_label": metric,
        "series": pts,
    }


def _extract_chart_payload_and_clean_text(response_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    text = str(response_text or "")
    if not text.strip():
        return text, None
    for match in _JSON_FENCE_RE.finditer(text):
        block = (match.group(1) or "").strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
        except Exception as e:
            logger.debug("chart block json parse failed: %s", e)
            continue
        payload = _coerce_chart_payload(parsed)
        if payload:
            cleaned = (text[: match.start()] + text[match.end() :]).strip()
            return (cleaned or text.strip()), payload
    try:
        parsed_full = json.loads(text.strip())
        payload = _coerce_chart_payload(parsed_full)
        if payload:
            return "", payload
    except Exception as e:
        logger.debug("Chart payload JSON parse failed: %s", e)
    return text, None


def _strip_map_payload_block_from_text(text: str) -> str:
    """Remove any ```json {... map_payload ...} ``` block and optional preceding line so we don't show raw JSON."""
    s = str(text or "").strip()
    if not s:
        return text or ""
    for match in _JSON_FENCE_RE.finditer(s):
        block = (match.group(1) or "").strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
        except Exception as e:
            logger.debug("map block json parse failed: %s", e)
            continue
        if _coerce_map_payload(parsed):
            cleaned = (s[: match.start()] + s[match.end() :]).strip()
            # Remove common preceding line like "JSON map (use this to render...):" or "JSON map:"
            for prefix in (
                r"(?m)^JSON\s+map\s*\([^)]*\)\s*:\s*\n",
                r"(?m)^JSON\s+map\s*:\s*\n",
                r"(?m)^.*map\s+payload\s*:\s*\n",
            ):
                cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()
            return cleaned
    return text


def _extract_map_payload_and_clean_text(response_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    text = str(response_text or "")
    if not text.strip():
        return text, None

    for match in _JSON_FENCE_RE.finditer(text):
        block = (match.group(1) or "").strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
        except Exception as e:
            logger.debug("map block json parse (2) failed: %s", e)
            continue
        payload = _coerce_map_payload(parsed)
        if payload:
            cleaned = (text[: match.start()] + text[match.end() :]).strip()
            return (cleaned or text.strip()), payload

    try:
        parsed_full = json.loads(text.strip())
        payload = _coerce_map_payload(parsed_full)
        if payload:
            return "", payload
    except Exception as e:
        logger.debug("parse_map_payload: JSON parse failed: %s", e)

    return text, None


def _revise_response_with_llm(
    text: str,
    *,
    user_query: str,
    language: str,
) -> str:
    """
    Run the given response text through an LLM for revision (clarity, tone, consistency).
    Returns revised text, or the original on failure/empty/skip.
    """
    text = str(text or "").strip()
    if not text:
        return text
    try:
        if not current_app.config.get("AI_RESPONSE_REVISION_ENABLED", False):
            return text
        api_key = current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return text
        model = (
            current_app.config.get("AI_RESPONSE_REVISION_MODEL")
            or current_app.config.get("OPENAI_MODEL")
            or "gpt-5-mini"
        )
        max_tokens = int(current_app.config.get("AI_RESPONSE_REVISION_MAX_TOKENS", 1500))
        timeout_sec = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60))
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=timeout_sec)
        lang = (language or "en").split("-")[0]
        system = (
            "You are an editor. Revise the assistant response for clarity, consistency, and tone. "
            f"Keep the same facts and meaning. Respond in {lang}. "
            "If the response includes a markdown table, list, or structured data, keep that structure in your revision. "
            "Output only the revised response—no preamble, no 'Revised:' label."
        )
        user_content = f"User question: {user_query[:800]}\n\nCurrent response:\n{text}"
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": max(200, min(max_tokens, 4000)),
        }
        if openai_model_supports_sampling_params(str(model)):
            kwargs["temperature"] = 0.3
        resp = client.chat.completions.create(**kwargs)
        revised = (resp.choices[0].message.content or "").strip()
        return revised if revised else text
    except Exception as e:
        logger.warning("Response revision failed, using original: %s", e)
        return text


@dataclass
class ChatResult:
    success: bool
    response_html: str
    provider: str
    model: Optional[str] = None
    function_calls_used: List[str] = field(default_factory=list)
    used_agent: bool = False
    streamed: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    map_payload: Optional[Dict[str, Any]] = None
    chart_payload: Optional[Dict[str, Any]] = None
    table_payload: Optional[Dict[str, Any]] = None
    trace_id: Optional[int] = None
    # Quality / grounding metadata
    confidence: Optional[str] = None   # 'high' | 'medium' | 'low'
    grounding_score: Optional[float] = None
    sources: Optional[List[Dict[str, Any]]] = None


def _record_fallback_trace(
    *,
    query: str,
    final_answer: Optional[str],
    model_name: str,
    execution_path: str,
    status: str = "fallback",
    error_message: Optional[str] = None,
) -> Optional[int]:
    """Best-effort: create a reasoning trace for a fallback (non-agent) response."""
    try:
        from app.services.ai_reasoning_trace import AIReasoningTraceService
        from flask import g, has_request_context
        from flask_login import current_user

        user_id = None
        conversation_id = None
        if has_request_context():
            if getattr(current_user, "is_authenticated", False):
                user_id = int(getattr(current_user, "id", 0) or 0) or None
            if user_id is None:
                try:
                    user_id = int(getattr(g, "ai_user_id", None) or 0) or None
                except Exception:
                    pass
            conversation_id = getattr(g, "ai_conversation_id", None)

        svc = AIReasoningTraceService()
        trace_id = svc.create_trace(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            llm_provider="openai",
            llm_model=model_name,
            agent_mode="fallback",
        )
        svc.finalize_trace(
            trace_id=trace_id,
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            steps=[],
            final_answer=final_answer,
            status=status,
            total_cost=0.0,
            llm_provider="openai",
            llm_model=model_name,
            agent_mode="fallback",
            execution_path=execution_path,
            error_message=error_message,
        )
        return trace_id
    except Exception as e:
        logger.debug("_record_fallback_trace failed: %s", e)
        return None


class AIChatEngine:
    """
    Centralized chat execution engine used by WS + SSE + HTTP JSON.

    Routes are responsible for:
    - auth / identity
    - rate limiting
    - persistence + telemetry
    - transport specifics (ws.send / SSE formatting)
    """

    def run(
        self,
        *,
        message: str,
        platform_context: Dict[str, Any],
        page_context: Dict[str, Any],
        preferred_language: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        enable_agent: bool = True,
        on_step: Optional[Callable[[str], None]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        cancelled: Optional[Any] = None,  # threading.Event-like, optional
        chunk_size: int = 8,
        chunk_delay_seconds: float = 0.01,
    ) -> ChatResult:
        """
        Execute the provider chain. If `on_delta` is provided, stream the HTML response
        using `delta` chunks (WS/SSE). Otherwise return a single HTML response.

        Streaming behavior: When the agent is used, the response is produced in full
        then sent in chunks via _stream_html (buffered streaming). Only the non-agent
        OpenAI path does true token-level streaming from the API.
        """
        conversation_history = conversation_history or []

        # Privacy: minimize obvious PII before sending to third-party LLMs.
        # (DB persistence still stores the original user message for authenticated users.)
        from app.services.ai_providers import scrub_pii_text, scrub_pii_context

        safe_message = scrub_pii_text((message or "").strip())
        safe_page_context = scrub_pii_context(page_context or {})

        # Rewrite user message with LLM before passing to agent or any fallback (when enabled)
        import time as _time
        _rewrite_wall_start = _time.time()
        from app.services.ai_query_rewriter import rewrite_user_message
        query_used = rewrite_user_message(
            message,
            conversation_history=conversation_history,
            preferred_language=preferred_language,
            page_context=safe_page_context,
        )
        logger.info("AIChatEngine: rewrite_user_message returned in %dms",
                     int((_time.time() - _rewrite_wall_start) * 1000))
        if not (query_used and query_used.strip()):
            query_used = (message or "").strip() or ""
        safe_query_used = scrub_pii_text((query_used or "").strip())
        worldmap_requested = _wants_worldmap_payload(message) or _wants_worldmap_payload(query_used)
        chart_requested = _wants_timeseries_chart(message) or _wants_timeseries_chart(query_used)
        safe_query_for_model = safe_query_used or safe_message

        if _ai_debug_enabled():
            try:
                # Don't log raw content; use scrubbed values.
                logger.debug(
                    "AIChatEngine.run debug: hist_items=%s msg=%r rewritten=%r worldmap=%s chart=%s agent_enabled=%s",
                    len(conversation_history or []),
                    safe_message[:200] + ("…" if len(safe_message) > 200 else ""),
                    safe_query_used[:200] + ("…" if len(safe_query_used) > 200 else ""),
                    bool(worldmap_requested),
                    bool(chart_requested),
                    bool(enable_agent and current_app.config.get("AI_AGENT_ENABLED", True)),
                )
            except Exception as e:
                logger.debug("AIChatEngine.run: debug log failed: %s", e)

        system_prompt = build_lightweight_system_prompt(platform_context, safe_page_context, preferred_language)
        if worldmap_requested:
            # IMPORTANT: keep the user query clean. Output-shape rules belong in system instructions,
            # not appended to the rewritten query (which is logged/traced and used for tool selection).
            system_prompt = f"{system_prompt}\n\n{_WORLDMAP_PAYLOAD_INSTRUCTION}"
        locale_code = (preferred_language or "en").split("-")[0]

        # Helper: allow early exit for cancelled transports
        def _is_cancelled() -> bool:
            try:
                return bool(cancelled and cancelled.is_set())
            except Exception as e:
                logger.debug("_is_cancelled failed: %s", e)
                return False

        # Helper: safe callback (detail is optional, e.g. rewritten query or tool args summary)
        def _emit_step(step_msg: str, detail: Optional[str] = None) -> None:
            if not on_step or _is_cancelled():
                return
            try:
                logger.debug("AIChatEngine emitting step: %s", step_msg)
                try:
                    on_step(step_msg, detail)
                except TypeError:
                    on_step(step_msg)
            except Exception as e:
                logger.debug("_emit_step failed: %s", e)

        def _emit_delta(delta_html: str) -> None:
            if not on_delta or _is_cancelled():
                return
            try:
                on_delta(delta_html)
            except Exception as e:
                logger.debug("_emit_delta failed: %s", e)

        def _stream_html(full_html: str) -> None:
            if not on_delta:
                return
            for i in range(0, len(full_html or ""), int(chunk_size)):
                if _is_cancelled():
                    break
                _emit_delta((full_html or "")[i : i + int(chunk_size)])
                if chunk_delay_seconds:
                    time.sleep(float(chunk_delay_seconds))

        # 1) Agent (tools + reasoning traces)
        if enable_agent and current_app.config.get("AI_AGENT_ENABLED", True) and not _is_cancelled():
            try:
                from app.services.ai_chat_integration import AIChatIntegration

                with force_locale(locale_code):
                    if safe_query_used and safe_query_used != safe_message:
                        _emit_step(
                            _("Preparing query…"),
                            detail=safe_query_used[:500] + ("…" if len(safe_query_used) > 500 else ""),
                        )
                    # "Planning approach…" step (with plan detail) is emitted by the executor after plan_simple()
                    ai = AIChatIntegration()
                    response_text, model_name, function_calls_used, meta = ai.process_query(
                        message=safe_query_for_model,
                        conversation_history=conversation_history,
                        page_context=safe_page_context,
                        platform_context=platform_context,
                        preferred_language=preferred_language,
                        on_step=on_step,
                        map_requested=worldmap_requested,
                        chart_requested=chart_requested,
                        original_message=(message or "").strip() or None,
                    )
                map_payload = None
                chart_payload = None
                table_payload = None
                answer_content = meta.get("answer_content") if isinstance(meta, dict) else None
                output_hint = meta.get("output_hint") if isinstance(meta, dict) else None
                # Always honor explicit structured payload from agent metadata when present,
                # even if the user phrasing didn't match worldmap trigger heuristics.
                if isinstance(meta, dict) and isinstance(meta.get("map_payload"), dict):
                    _raw_mp = meta.get("map_payload")
                    _mp_countries = _raw_mp.get("countries") if isinstance(_raw_mp, dict) else []
                    _mp_sample = (_mp_countries or [])[:2]
                    logger.debug(
                        "ai_chat_engine: coercing map_payload — %d countries, sample regions: %s",
                        len(_mp_countries or []),
                        [c.get("region") for c in _mp_sample],
                    )
                    map_payload = _coerce_map_payload(_raw_mp)
                    _cp_countries = map_payload.get("countries") if isinstance(map_payload, dict) else []
                    logger.debug(
                        "ai_chat_engine: after _coerce_map_payload — %d countries, sample regions: %s",
                        len(_cp_countries or []),
                        [c.get("region") for c in (_cp_countries or [])[:2]],
                    )
                if isinstance(meta, dict) and isinstance(meta.get("chart_payload"), dict):
                    chart_payload = _coerce_chart_payload(meta.get("chart_payload"))
                # table_payload is passed through as-is (already structured by the executor).
                if isinstance(meta, dict) and isinstance(meta.get("table_payload"), dict):
                    table_payload = meta.get("table_payload")
                # Generic output-type layer: infer map/chart from normalized answer content
                # when the agent did not explicitly provide payloads.
                if not map_payload:
                    map_payload = _map_payload_from_answer_content(answer_content, output_hint=output_hint)
                if not chart_payload:
                    chart_payload = _chart_payload_from_answer_content(answer_content, output_hint=output_hint)
                if worldmap_requested and not map_payload and response_text:
                    response_text, map_payload = _extract_map_payload_and_clean_text(response_text)
                if chart_requested and not chart_payload and response_text:
                    response_text, chart_payload = _extract_chart_payload_and_clean_text(response_text)
                # When we have a map, strip the map payload JSON block from the response so we don't show raw JSON
                if map_payload and response_text:
                    response_text = _strip_map_payload_block_from_text(response_text)

                # Accept map-only successful responses (no textual bubble needed).
                if response_text or map_payload or chart_payload or table_payload:
                    cleaned_response_text = response_text or ""
                    if cleaned_response_text:
                        cleaned_response_text = _revise_response_with_llm(
                            cleaned_response_text,
                            user_query=safe_query_used or safe_message,
                            language=preferred_language or "en",
                        )
                    html = format_ai_response_for_html(cleaned_response_text) if cleaned_response_text else ""
                    if html:
                        _stream_html(html)
                    return ChatResult(
                        success=True,
                        response_html=html,
                        provider=(meta.get("provider") or "agent"),
                        model=model_name,
                        function_calls_used=function_calls_used or [],
                        used_agent=bool(meta.get("used_agent", True)),
                        streamed=bool(on_delta),
                        input_tokens=meta.get("input_tokens"),
                        output_tokens=meta.get("output_tokens"),
                        map_payload=map_payload,
                        chart_payload=chart_payload,
                        table_payload=table_payload,
                        trace_id=meta.get("trace_id"),
                        confidence=meta.get("confidence"),
                        grounding_score=meta.get("grounding_score"),
                        sources=meta.get("sources"),
                    )
            except Exception as e:
                logger.warning("AIChatEngine: agent failed, falling back: %s", e)

        # 2) OpenAI (streaming or non-streaming)
        if current_app.config.get("OPENAI_API_KEY") and not _is_cancelled():
            try:
                model_name = current_app.config.get("OPENAI_MODEL", "gpt-5-mini")
                if on_delta:
                    with force_locale(locale_code):
                        _emit_step(_("Drafting answer…"))
                    from openai import OpenAI
                    import os

                    openai_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
                    timeout_sec = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60))
                    client = OpenAI(api_key=openai_key, timeout=timeout_sec)

                    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
                    # Include conversation history for context (last 5 exchanges, same as non-streaming).
                    messages.extend(_coerce_history_messages(conversation_history, limit=5))
                    messages.append({"role": "user", "content": safe_query_for_model or safe_message})

                    kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "stream": True,
                        "max_completion_tokens": int(current_app.config.get("AI_CHAT_MAX_COMPLETION_TOKENS", 1200)),
                    }
                    if openai_model_supports_sampling_params(str(model_name)):
                        kwargs["temperature"] = 0.7

                    stream = client.chat.completions.create(**kwargs)
                    accumulated = ""
                    for chunk in stream:
                        if _is_cancelled():
                            break
                        if chunk.choices and chunk.choices[0].delta.content:
                            accumulated += chunk.choices[0].delta.content
                    # Revise then stream the revised response so the user sees one consistent answer.
                    final_response_text = accumulated
                    map_payload = None
                    if worldmap_requested:
                        final_response_text, map_payload = _extract_map_payload_and_clean_text(accumulated)
                    chart_payload = None
                    if chart_requested:
                        final_response_text, chart_payload = _extract_chart_payload_and_clean_text(final_response_text)
                    if final_response_text:
                        final_response_text = _revise_response_with_llm(
                            final_response_text,
                            user_query=safe_query_used or safe_message,
                            language=preferred_language or "en",
                        )
                    html = format_ai_response_for_html(final_response_text)
                    if html:
                        _stream_html(html)
                    logger.debug("Direct LLM fallback used (streaming); no verification/grounding performed")
                    fallback_trace_id = _record_fallback_trace(
                        query=safe_query_for_model or safe_message,
                        final_answer=final_response_text,
                        model_name=str(model_name),
                        execution_path="streaming_fallback",
                    )
                    return ChatResult(
                        success=True,
                        response_html=html,
                        provider="openai",
                        model=str(model_name),
                        function_calls_used=[],
                        used_agent=False,
                        streamed=True,
                        map_payload=map_payload,
                        chart_payload=chart_payload,
                        confidence="unverified",
                        trace_id=fallback_trace_id,
                    )

                # non-streaming
                response_text, model_name_used, function_calls_used = integrate_openai_with_telemetry(
                    safe_query_for_model or safe_message, platform_context, conversation_history, safe_page_context, preferred_language
                )
                if response_text:
                    cleaned_response_text = response_text
                    map_payload = None
                    if worldmap_requested:
                        cleaned_response_text, map_payload = _extract_map_payload_and_clean_text(response_text)
                    chart_payload = None
                    if chart_requested:
                        cleaned_response_text, chart_payload = _extract_chart_payload_and_clean_text(cleaned_response_text)
                    if cleaned_response_text:
                        cleaned_response_text = _revise_response_with_llm(
                            cleaned_response_text,
                            user_query=safe_query_used or safe_message,
                            language=preferred_language or "en",
                        )
                    html = format_ai_response_for_html(cleaned_response_text)
                    logger.info("Direct LLM fallback used (non-streaming); no verification/grounding performed")
                    fallback_trace_id = _record_fallback_trace(
                        query=safe_query_for_model or safe_message,
                        final_answer=cleaned_response_text,
                        model_name=str(model_name_used or model_name),
                        execution_path="non_streaming_fallback",
                    )
                    return ChatResult(
                        success=True,
                        response_html=html,
                        provider="openai",
                        model=model_name_used,
                        function_calls_used=function_calls_used or [],
                        used_agent=False,
                        streamed=False,
                        map_payload=map_payload,
                        chart_payload=chart_payload,
                        confidence="unverified",
                        trace_id=fallback_trace_id,
                    )
                _record_fallback_trace(
                    query=safe_query_for_model or safe_message,
                    final_answer=None,
                    model_name=str(model_name_used or model_name),
                    execution_path="non_streaming_fallback",
                    status="error",
                    error_message="OpenAI returned an empty response",
                )
                return ChatResult(
                    success=False,
                    response_html="",
                    provider="openai",
                    model=str(model_name_used or model_name),
                    function_calls_used=function_calls_used or [],
                    used_agent=False,
                    streamed=False,
                    error_type="OpenAIEmptyResponse",
                    error_message="OpenAI returned an empty response",
                )
            except Exception as e:
                logger.warning("AIChatEngine: OpenAI failed: %s", e)
                _record_fallback_trace(
                    query=safe_query_for_model or safe_message,
                    final_answer=None,
                    model_name=str(current_app.config.get("OPENAI_MODEL", "gpt-5-mini")),
                    execution_path="streaming_fallback" if on_delta else "non_streaming_fallback",
                    status="error",
                    error_message=f'{type(e).__name__}: {e}',
                )
                return ChatResult(
                    success=False,
                    response_html="",
                    provider="openai",
                    model=str(current_app.config.get("OPENAI_MODEL", "gpt-5-mini")),
                    function_calls_used=[],
                    used_agent=False,
                    streamed=bool(on_delta),
                    error_type=type(e).__name__,
                    error_message="Chat request failed.",
                )

        # OpenAI not configured (no fallbacks)
        return ChatResult(
            success=False,
            response_html="",
            provider="openai",
            model=str(current_app.config.get("OPENAI_MODEL", "gpt-5-mini")),
            function_calls_used=[],
            used_agent=False,
            streamed=bool(on_delta),
            error_type="OpenAINotConfigured",
            error_message="OPENAI_API_KEY is not configured",
        )
