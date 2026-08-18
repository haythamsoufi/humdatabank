"""
LLM fallback for AI document country / geographic-scope detection.

Keyword matching is fast but brittle across languages and HQ address mentions.
When keyword confidence is low, a small JSON classifier decides scope + ISO3 codes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.models import Country

from .country_detection import (
    SCOPE_CLUSTER,
    SCOPE_GLOBAL,
    SCOPE_REGIONAL,
    CountryDetectionResult,
)

logger = logging.getLogger(__name__)

_ALLOWED_SCOPES = {SCOPE_GLOBAL, SCOPE_REGIONAL, SCOPE_CLUSTER, None}
_LLM_TEXT_CHARS = 4000


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    if value is None:
        return default
    return bool(value)


def llm_fallback_enabled() -> bool:
    try:
        from flask import current_app
        if not current_app.config.get("OPENAI_API_KEY"):
            return False
        return _coerce_bool(current_app.config.get("AI_DOC_COUNTRY_LLM_ENABLED", True), True)
    except Exception:
        return False


def llm_min_confidence() -> float:
    try:
        from flask import current_app
        raw = current_app.config.get("AI_DOC_COUNTRY_LLM_MIN_CONFIDENCE", 0.7)
        n = float(raw)
        if n < 0 or n > 1:
            return 0.7
        return n
    except Exception:
        return 0.7


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        logger.debug("country_detection_llm: json parse failed: %s", e)
        return None


def _resolve_iso3_list(iso3_list: list) -> list[tuple[int, str]]:
    codes: list[str] = []
    seen: set[str] = set()
    for raw in iso3_list or []:
        code = str(raw or "").strip().upper()
        if len(code) != 3 or not code.isalpha() or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    if not codes:
        return []
    rows = Country.query.filter(Country.iso3.in_(codes)).all()
    by_iso = {str(c.iso3).upper(): c for c in rows if getattr(c, "iso3", None)}
    out: list[tuple[int, str]] = []
    for code in codes:
        c = by_iso.get(code)
        if c and getattr(c, "id", None) and getattr(c, "name", None):
            out.append((int(c.id), str(c.name)))
    return out


def _normalize_llm_scope(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in {"", "null", "none", "country", "country-specific", "national"}:
        return None
    if s in _ALLOWED_SCOPES:
        return s
    return None


def _build_prompt(*, filename: str | None, title: str | None, text: str | None, hint: CountryDetectionResult) -> str:
    snippet = (text or "").strip()[:_LLM_TEXT_CHARS]
    hint_countries = ", ".join(name for _cid, name in (hint.countries or [])[:12]) or "none"
    return (
        "Classify the geographic coverage of this IFRC / Red Cross / humanitarian document.\n"
        "Return JSON only with keys: scope, country_iso3, reason.\n"
        "scope must be one of: global, regional, cluster, country.\n"
        "country_iso3 must be an array of ISO 3166-1 alpha-3 codes (empty when global/regional "
        "with no specific National Society set).\n\n"
        "Rules:\n"
        "- global: federation-wide strategy, policy, or framework not about one country.\n"
        "- regional: an IFRC statutory region (Africa, MENA, Americas, Asia Pacific, Europe).\n"
        "- cluster: a specific set of countries that is not a statutory region.\n"
        "- country: one country / National Society. Use scope=country and one ISO3.\n"
        "- Publisher or HQ address (Geneva, Switzerland, Budapest) is NOT the document country "
        "unless the document is actually about that country.\n"
        "- Language editions of the same publication share the same geography.\n\n"
        f"Keyword hint (may be wrong): scope={hint.scope or 'none'}; countries={hint_countries}; "
        f"confidence={hint.confidence:.2f}; reason={hint.reason or 'n/a'}\n\n"
        f"Filename: {filename or ''}\n"
        f"Title: {title or ''}\n"
        f"Excerpt:\n{snippet or '(no extracted text)'}\n"
    )


def classify_geography_with_llm(
    *,
    filename: str | None,
    title: str | None,
    text: str | None,
    keyword_result: CountryDetectionResult,
) -> Optional[CountryDetectionResult]:
    """Call a cheap LLM classifier. Returns None if unavailable or invalid."""
    try:
        from flask import current_app
        from openai import OpenAI

        from app.utils.ai_utils import openai_model_supports_sampling_params

        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            return None
        model = (
            current_app.config.get("AI_DOC_COUNTRY_LLM_MODEL")
            or current_app.config.get("AI_QUERY_REWRITE_MODEL")
            or "gpt-4o-mini"
        )
        client = OpenAI(api_key=api_key, timeout=20, max_retries=0)
        prompt = _build_prompt(
            filename=filename, title=title, text=text, hint=keyword_result
        )
        kwargs: dict[str, Any] = {
            "model": str(model),
            "messages": [
                {
                    "role": "system",
                    "content": "You classify humanitarian document geography. Reply with JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if openai_model_supports_sampling_params(str(model)):
            kwargs["temperature"] = 0
            kwargs["max_tokens"] = 250
        else:
            kwargs["max_completion_tokens"] = 250

        resp = client.chat.completions.create(**kwargs)
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        payload = _extract_json_object(content)
        if not payload:
            logger.info("country_detection_llm: empty/invalid JSON from model=%s", model)
            return None

        scope = _normalize_llm_scope(payload.get("scope"))
        raw_iso = payload.get("country_iso3") or payload.get("countries") or []
        if isinstance(raw_iso, str):
            raw_iso = [raw_iso]
        if not isinstance(raw_iso, list):
            raw_iso = []
        if scope in (SCOPE_GLOBAL, SCOPE_REGIONAL) and not raw_iso:
            countries: list[tuple[int, str]] = []
        else:
            countries = _resolve_iso3_list(raw_iso)
            if scope == SCOPE_GLOBAL:
                countries = []

        reason = str(payload.get("reason") or "llm").strip()[:240]
        logger.info(
            "country_detection_llm: model=%s scope=%r countries=%s reason=%r",
            model,
            scope,
            [name for _cid, name in countries],
            reason,
        )
        return CountryDetectionResult(
            countries=countries,
            scope=scope,
            confidence=0.86,
            source="llm",
            reason=reason or "llm",
        )
    except Exception as e:
        logger.info("country_detection_llm: failed, keeping keyword result: %s", e)
        return None


def refine_if_needed(
    keyword_result: CountryDetectionResult,
    *,
    filename: str | None,
    title: str | None,
    text: str | None,
    use_llm: bool | None = None,
) -> CountryDetectionResult:
    """Keep the keyword result when confident; otherwise try the LLM."""
    enabled = llm_fallback_enabled() if use_llm is None else bool(use_llm)
    if not enabled:
        return keyword_result
    if not (text and str(text).strip()):
        return keyword_result
    if keyword_result.confidence >= llm_min_confidence():
        return keyword_result
    llm_result = classify_geography_with_llm(
        filename=filename,
        title=title,
        text=text,
        keyword_result=keyword_result,
    )
    return llm_result or keyword_result
