"""
Shape-based payload inference pipeline.

Scans agent steps, detects data shapes, and builds visualization payloads
(line chart, bar chart, pie/donut chart, world map, data table) without
coupling to specific tool names.  Any tool that returns a recognised data
shape gets automatic visualisation support.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask_babel import gettext as _

from app.services.upr.ux import UPR_SOURCE_QUALIFIER

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

_TABLE_MIN_ROWS = 10
_ENRICHMENT_BATCH_SIZE = 50
_ENRICHMENT_MAX_WORKERS = 4
_ENRICHMENT_TIMEOUT = 300
_ENRICHMENT_CACHE_TTL = 3600
_REASONING_MODEL_MIN_COMPLETION_TOKENS = 4096
_REGIONS = ("MENA", "EUROPE", "AFRICA", "ASIA PACIFIC", "AMERICAS")
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_STAT_LINE_PLANS_RE = re.compile(r"\b\d+\s*/\s*\d+\s+plans?\b", re.IGNORECASE)


# ── Observation parsing ──────────────────────────────────────────────────


def _parse_obs(raw: Any) -> Optional[Dict[str, Any]]:
    """Parse a step observation (dict, JSON string, or None)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _inner(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap ``obs["result"]`` nesting when present."""
    result = obs.get("result")
    if isinstance(result, dict):
        return result
    return obs


# ── Value parsing helpers ────────────────────────────────────────────────


def _parse_numeric(v: Any) -> Optional[float]:
    """Coerce *v* to a float, returning ``None`` on failure."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").replace("\u00a0", "").strip())
        except (ValueError, TypeError):
            return None
    return None


def _valid_iso3(s: str) -> bool:
    return len(s) == 3 and s.isalpha()


_RAW_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM output — handles fences, preamble text, etc."""
    text = (text or "").strip()
    if not text:
        return None

    m = _JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    m2 = _RAW_JSON_RE.search(text)
    if m2:
        try:
            return json.loads(m2.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ── Region helpers ───────────────────────────────────────────────────────


def _detect_region(query: str) -> Optional[str]:
    if not query:
        return None
    q = query.upper().replace(" ", "")
    for r in _REGIONS:
        if r.replace(" ", "") in q:
            return r
    return None


def _matches_region(candidate: str, target: str) -> bool:
    if not target:
        return True
    cr = (candidate or "").strip().upper()
    if not cr:
        return True
    return target.upper() in cr or cr in target.upper()


# ── Shape detectors ──────────────────────────────────────────────────────
# Pure predicates that inspect the *inner* data dict.  They never look at
# tool names – only at structural properties of the data.


def _is_timeseries(d: dict) -> bool:
    """Series of ``{year, value}`` data points (≥2)."""
    series = d.get("series")
    if not isinstance(series, list) or len(series) < 2:
        return False
    sample = next((p for p in series if isinstance(p, dict)), None)
    if not sample:
        return False
    has_x = "year" in sample or "x" in sample
    has_y = "value" in sample or "y" in sample
    return has_x and has_y


def _is_country_rows(d: dict) -> bool:
    """Rows with ``iso3`` and ``value`` fields (≥ ``_TABLE_MIN_ROWS``)."""
    rows = d.get("rows")
    if not isinstance(rows, list) or len(rows) < _TABLE_MIN_ROWS:
        return False
    sample = next((r for r in rows if isinstance(r, dict)), None)
    if not sample:
        return False
    return bool(sample.get("iso3") or sample.get("country_iso3")) and "value" in sample


def _is_comparison(d: dict) -> bool:
    """Small ``countries`` list with ``country`` + ``value`` (≤15 items)."""
    countries = d.get("countries")
    if not isinstance(countries, list) or not 2 <= len(countries) <= 15:
        return False
    sample = next((c for c in countries if isinstance(c, dict)), None)
    if not sample:
        return False
    return "country" in sample and "value" in sample and bool(d.get("indicator"))


def _is_categorical_counts(d: dict) -> bool:
    """Dict of category → numeric count (≥2 categories)."""
    counts = d.get("counts_by_area")
    if not isinstance(counts, dict) or len(counts) < 2:
        return False
    return all(isinstance(v, (int, float)) for v in counts.values())


def _is_country_docs(d: dict) -> bool:
    """Document listing with per-country metadata."""
    if isinstance(d.get("countries_by_region"), dict) and d["countries_by_region"]:
        return True
    docs = d.get("documents")
    if not isinstance(docs, list) or not docs:
        return False
    sample = next((doc for doc in docs if isinstance(doc, dict)), None)
    if not sample:
        return False
    return bool(sample.get("country_iso3") or sample.get("countries"))


def _is_focus_area(d: dict) -> bool:
    """``countries_grouped`` with nested plan data."""
    cg = d.get("countries_grouped")
    if not isinstance(cg, list) or len(cg) < _TABLE_MIN_ROWS:
        return False
    sample = next((c for c in cg if isinstance(c, dict)), None)
    if not sample:
        return False
    return isinstance(sample.get("plans"), list) or bool(sample.get("country_name"))


# ── Metric / title derivation ────────────────────────────────────────────


def _derive_metric(d: dict) -> str:
    disp = d.get("indicator_display_name")
    if isinstance(disp, str) and disp.strip():
        return str(disp).strip()[:160]
    ri = d.get("resolved_indicator")
    if isinstance(ri, dict) and ri.get("name"):
        return str(ri["name"]).strip()[:160]
    ind = d.get("indicator")
    if isinstance(ind, dict):
        dn = ind.get("display_name")
        if isinstance(dn, str) and dn.strip():
            return str(dn).strip()[:160]
        if ind.get("name"):
            return str(ind["name"]).strip()[:160]
    if isinstance(ind, str) and ind.strip():
        return ind.strip()[:160]
    for key in ("metric", "indicator_name", "indicator_name_resolved"):
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:160]
    return "Value"


def _source_qualifier(d: dict) -> str:
    st = str(d.get("source_type") or "").strip().lower()
    if st == "upr_documents":
        return UPR_SOURCE_QUALIFIER
    agg = str(d.get("aggregation") or "").strip().lower()
    if "upr" in agg:
        return UPR_SOURCE_QUALIFIER
    return ""


# ── Payload builders ─────────────────────────────────────────────────────
# Each builder receives the *inner* data dict and the user query.
# Returns a payload dict with a ``_score`` key for internal ranking,
# or ``None`` if a valid payload cannot be constructed.


def _build_line_chart(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    series = d.get("series")
    if not isinstance(series, list):
        return None

    points: List[Dict[str, Any]] = []
    for p in series:
        if not isinstance(p, dict):
            continue
        x = _parse_numeric(p.get("year") or p.get("x"))
        y = _parse_numeric(p.get("value") or p.get("y"))
        if x is None or y is None:
            continue
        xi = int(x)
        if xi < 1900 or xi > 2100:
            continue
        pt: Dict[str, Any] = {"x": xi, "y": y}
        if p.get("data_status"):
            pt["data_status"] = str(p["data_status"])
        if p.get("period_name"):
            pt["period_name"] = str(p["period_name"])
        points.append(pt)

    if len(points) < 2:
        return None

    points.sort(key=lambda r: r["x"])
    metric = _derive_metric(d)
    country = str(d.get("country_display_name") or d.get("country_name") or "").strip()[:160]
    qual = _source_qualifier(d)

    title = _("%(metric)s over time", metric=metric)
    if country:
        title = _("%(metric)s in %(country)s over time", metric=metric, country=country)
    if qual:
        title = f"{title} ({qual})"

    return {
        "type": "line",
        "title": title[:220],
        "metric": metric[:120],
        "country": country or None,
        "x": "year",
        "y_label": metric[:120],
        "series": points,
        "_score": len(points),
    }


def _build_bar_chart(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    countries = d.get("countries")
    if not isinstance(countries, list) or not countries:
        return None

    categories: List[Dict[str, Any]] = []
    for c in countries:
        if not isinstance(c, dict):
            continue
        label = str(
            c.get("country") or c.get("label") or c.get("name") or ""
        ).strip()
        value = _parse_numeric(c.get("value"))
        if not label or value is None:
            continue
        categories.append({"label": label[:80], "value": value})

    if len(categories) < 2:
        return None

    metric = str(d.get("indicator") or d.get("metric") or "Value").strip()[:120]
    title = f"{metric} — comparison" if metric != "Value" else "Country comparison"
    orientation = "horizontal" if len(categories) > 6 else "vertical"

    return {
        "type": "bar",
        "title": title[:220],
        "metric": metric,
        "categories": categories,
        "orientation": orientation,
        "_score": len(categories),
    }


def _build_pie_chart(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    counts = d.get("counts_by_area")
    if not isinstance(counts, dict) or len(counts) < 2:
        return None

    slices: List[Dict[str, Any]] = []
    for label, value in sorted(counts.items(), key=lambda kv: -(kv[1] or 0)):
        if not isinstance(value, (int, float)):
            continue
        slices.append({
            "label": str(label).replace("_", " ").title()[:80],
            "value": float(value),
        })

    if len(slices) < 2:
        return None

    return {
        "type": "pie",
        "title": "Distribution by focus area"[:220],
        "slices": slices,
        "_score": len(slices),
    }


def _build_country_table(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    rows = d.get("rows")
    if not isinstance(rows, list) or len(rows) < _TABLE_MIN_ROWS:
        return None

    metric = _derive_metric(d)
    title = f"{metric} by country" if metric != "Value" else "Values by country"

    has_period = any(isinstance(r, dict) and r.get("period_used") for r in rows)
    has_source = any(isinstance(r, dict) and r.get("assignment_name") for r in rows)
    has_status = any(isinstance(r, dict) and r.get("data_status") for r in rows)

    columns: List[Dict[str, Any]] = [
        {"key": "country_name", "label": "Country", "sortable": True, "type": "text"},
        {"key": "region", "label": "Operational region", "sortable": True, "type": "text"},
        {"key": "value", "label": metric or "Value", "sortable": True, "type": "number"},
    ]
    if has_period:
        columns.append({"key": "period", "label": "Period", "sortable": True, "type": "text"})
    if has_source:
        columns.append({"key": "source", "label": "Source", "sortable": True, "type": "text"})
    if has_status:
        columns.append({"key": "status", "label": "Status", "sortable": True, "type": "text"})

    table_rows: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row: Dict[str, Any] = {
            "country_name": str(r.get("country_name") or "").strip(),
            "iso3": str(r.get("iso3") or "").strip().upper(),
            "region": str(r.get("region") or "").strip(),
            "value": _parse_numeric(r.get("value")),
        }
        if has_period:
            row["period"] = str(r.get("period_used") or "").strip()
        if has_source:
            row["source"] = str(r.get("assignment_name") or "").strip()
        if has_status:
            row["status"] = str(r.get("data_status") or "").strip()
        table_rows.append(row)

    if not table_rows:
        return None

    return {
        "type": "data_table",
        "title": title[:220],
        "metric": (metric or "Value")[:120],
        "columns": columns,
        "rows": table_rows,
        "total_rows": len(table_rows),
        "sort_by": "value",
        "sort_order": "desc",
        "_score": len(table_rows),
    }


def _build_country_map(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    rows = d.get("rows")
    if not isinstance(rows, list) or len(rows) < 3:
        return None

    region = _detect_region(query)
    metric = _derive_metric(d)
    countries: List[Dict[str, Any]] = []
    seen: set = set()

    for r in rows:
        if not isinstance(r, dict):
            continue
        iso3 = str(r.get("iso3") or "").strip().upper()
        if not _valid_iso3(iso3) or iso3 in seen:
            continue
        r_region = str(r.get("region") or "").strip()
        if region and not _matches_region(r_region, region):
            continue
        value = _parse_numeric(r.get("value"))
        if value is None:
            continue
        seen.add(iso3)
        countries.append({
            "iso3": iso3,
            "value": value,
            "label": str(r.get("country_name") or r.get("label") or iso3).strip(),
            "region": r_region,
        })

    if len(countries) < 3:
        return None

    title = f"{metric} by country" if metric != "Value" else "Values by country"
    if region:
        title = f"{metric} — {region}"

    return {
        "type": "worldmap",
        "title": title[:160],
        "metric": metric[:120],
        "countries": countries,
        "_score": len(countries),
    }


def _build_document_map(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    region = _detect_region(query)
    countries: List[Dict[str, Any]] = []
    seen: set = set()

    cbr = d.get("countries_by_region")
    if isinstance(cbr, dict):
        for rkey, clist in cbr.items():
            if not isinstance(clist, list):
                continue
            if region and not _matches_region(rkey, region):
                continue
            for c in clist:
                if not isinstance(c, dict):
                    continue
                iso3 = str(c.get("iso3") or "").strip().upper()
                if not _valid_iso3(iso3) or iso3 in seen:
                    continue
                seen.add(iso3)
                label = str(c.get("name") or c.get("label") or iso3).strip()
                val = c.get("latest_plan_year")
                if not isinstance(val, int) or val < 2000 or val > 2100:
                    val = 1
                countries.append({"iso3": iso3, "value": val, "label": label, "region": rkey})

    docs = d.get("documents")
    if isinstance(docs, list) and not countries:
        latest_year: Dict[str, int] = {}
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            year = doc.get("plan_year")
            if not isinstance(year, int) or year < 2000 or year > 2100:
                year = None
            primary = str(doc.get("country_iso3") or "").strip().upper()
            if _valid_iso3(primary) and year:
                if primary not in latest_year or year > latest_year[primary]:
                    latest_year[primary] = year
            for cc in doc.get("countries") or []:
                if not isinstance(cc, dict):
                    continue
                iso3 = str(cc.get("iso3") or "").strip().upper()
                if _valid_iso3(iso3) and year:
                    if iso3 not in latest_year or year > latest_year[iso3]:
                        latest_year[iso3] = year

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            added = False
            for cc in doc.get("countries") or []:
                if not isinstance(cc, dict):
                    continue
                iso3 = str(cc.get("iso3") or "").strip().upper()
                if not _valid_iso3(iso3) or iso3 in seen:
                    continue
                cc_region = str(cc.get("region") or "").strip()
                if region and not _matches_region(cc_region, region):
                    continue
                seen.add(iso3)
                countries.append({
                    "iso3": iso3,
                    "value": latest_year.get(iso3, 1),
                    "label": str(cc.get("name") or iso3).strip(),
                    "region": cc_region,
                })
                added = True
            if not added:
                primary = str(doc.get("country_iso3") or "").strip().upper()
                if not _valid_iso3(primary) or primary in seen:
                    continue
                p_region = str(doc.get("country_region") or "").strip()
                if region and not _matches_region(p_region, region):
                    continue
                seen.add(primary)
                countries.append({
                    "iso3": primary,
                    "value": latest_year.get(primary, 1),
                    "label": str(doc.get("country_name") or primary).strip(),
                    "region": p_region,
                })

    if len(countries) < 2:
        return None

    has_years = any(
        isinstance(c.get("value"), int) and c["value"] != 1 and 2000 <= c["value"] <= 2100
        for c in countries
    )
    metric = "Most recent plan year" if has_years else "Documents available"
    title = f"{metric} by country"
    if region:
        title = f"{metric} — {region}"

    return {
        "type": "worldmap",
        "title": title[:160],
        "metric": metric[:120],
        "countries": countries,
        "_score": len(countries),
    }


def _build_focus_area_table(d: dict, query: str = "") -> Optional[Dict[str, Any]]:
    cg = d.get("countries_grouped")
    areas: List[str] = list((d.get("counts_by_area") or {}).keys())
    rows: List[Dict[str, Any]] = []

    if isinstance(cg, list):
        for entry in cg:
            if not isinstance(entry, dict):
                continue
            plans = entry.get("plans") or []
            latest = plans[0] if plans else {}
            evidence = 0
            snippets: List[str] = []
            seen_snip: set = set()
            for plan in plans:
                if not isinstance(plan, dict):
                    continue
                for ad in (plan.get("area_details") or {}).values():
                    if not isinstance(ad, dict):
                        continue
                    evidence += int(ad.get("evidence_chunks") or 0)
                    for ex in ad.get("activity_examples") or []:
                        s = str(ex).strip()
                        if len(s) < 20:
                            continue
                        norm = s.lower()[:60]
                        if norm in seen_snip:
                            continue
                        seen_snip.add(norm)
                        snippets.append(s)
            snippets.sort(key=len, reverse=True)
            highlight = "; ".join(snippets[:3])
            if len(highlight) > 350:
                highlight = highlight[:347] + "\u2026"
            rows.append({
                "name": entry.get("country_name"),
                "iso3": entry.get("country_iso3"),
                "year": latest.get("plan_year"),
                "doc": latest.get("document_title"),
                "url": latest.get("document_url"),
                "highlight": highlight,
            })

    if not rows:
        compacted = d.get("countries")
        if isinstance(compacted, list):
            rows = [c for c in compacted if isinstance(c, dict)]
            areas = d.get("areas_queried") or areas or []

    if len(rows) < _TABLE_MIN_ROWS:
        return None

    area_label = ", ".join(a.replace("_", " ").title() for a in areas) if areas else "Focus Areas"
    title = f"{area_label} \u2014 plans by country ({len(rows)} countries)"

    has_hl = any(isinstance(c, dict) and c.get("highlight") for c in rows)
    columns: List[Dict[str, Any]] = [
        {"key": "country", "label": "Country", "sortable": True, "type": "text"},
        {"key": "plan_year", "label": "Plan Year", "sortable": True, "type": "text"},
        {"key": "document", "label": "Document", "sortable": True, "type": "link", "url_key": "document_url"},
    ]
    if has_hl:
        columns.append({"key": "highlight", "label": "Activities & Partnerships", "sortable": True, "type": "text"})

    table_rows: List[Dict[str, Any]] = []
    for c in rows:
        if not isinstance(c, dict):
            continue
        row: Dict[str, Any] = {
            "country": str(c.get("name") or "").strip(),
            "iso3": str(c.get("iso3") or "").strip().upper(),
            "plan_year": c.get("year"),
            "document": str(c.get("doc") or "").strip(),
            "document_url": str(c.get("url") or "").strip(),
        }
        if has_hl:
            row["highlight"] = str(c.get("highlight") or "").strip()
        table_rows.append(row)

    if not table_rows:
        return None

    return {
        "type": "data_table",
        "title": title[:220],
        "columns": columns,
        "rows": table_rows,
        "total_rows": len(table_rows),
        "sort_by": "plan_year",
        "sort_order": "desc",
        # Skip automatic reference-data enrichment unless the query asks for it;
        # otherwise LLM batch fills add minutes of latency and unreliable columns.
        "table_kind": "unified_plans_focus",
        "_score": len(table_rows),
    }


# ── Builder registry ─────────────────────────────────────────────────────
# (predicate, builder, payload_slot, priority)
# Lower priority = evaluated first.  Within the same slot the highest
# ``_score`` wins.

_REGISTRY: List[Tuple[Callable, Callable, str, int]] = [
    (_is_timeseries,         _build_line_chart,        "chart_payload", 10),
    (_is_comparison,         _build_bar_chart,          "chart_payload", 15),
    (_is_categorical_counts, _build_pie_chart,          "chart_payload", 25),
    (_is_country_rows,       _build_country_table,      "table_payload", 20),
    (_is_country_rows,       _build_country_map,        "map_payload",   30),
    (_is_focus_area,         _build_focus_area_table,   "table_payload", 22),
    (_is_country_docs,       _build_document_map,       "map_payload",   30),
]


# ── Viz selector ─────────────────────────────────────────────────────────


def _apply_viz_preferences(
    payloads: Dict[str, Any],
    query: str,
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Set ``output_hint`` based on available payloads and user intent."""
    result = dict(payloads)
    if user_context.get("map_requested") and "map_payload" in result:
        result["output_hint"] = "map"
    elif user_context.get("chart_requested") and "chart_payload" in result:
        result["output_hint"] = "chart"
    elif "chart_payload" in result:
        result["output_hint"] = "chart"
    elif "table_payload" in result:
        result["output_hint"] = "table"
    elif "map_payload" in result:
        result["output_hint"] = "map"
    return result


# ── Dynamic LLM enrichment ───────────────────────────────────────────────

_cache: Dict[Tuple[str, str], Any] = {}
_cache_ts: float = 0.0
_cache_lock = threading.Lock()


def _llm_call_with_json_fallback(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
) -> Optional[Dict[str, Any]]:
    """Make an LLM call that reliably returns parsed JSON.

    Strategy:
    1. Try with ``response_format: json_object`` (works for most models).
    2. If the API rejects it (400), retry without it.
    3. Parse the response with ``_extract_json`` (handles fences / preamble).

    For reasoning models (GPT-5 family etc.) ``max_completion_tokens`` covers
    both internal reasoning *and* visible output, so we apply a higher floor
    to avoid empty responses when the reasoning budget exhausts the cap.
    """
    from app.utils.ai_utils import openai_model_supports_sampling_params

    is_reasoning_model = not openai_model_supports_sampling_params(model)
    effective_max = max_tokens
    if is_reasoning_model:
        effective_max = max(max_tokens, _REASONING_MODEL_MIN_COMPLETION_TOKENS)

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": effective_max,
        "response_format": {"type": "json_object"},
    }
    if not is_reasoning_model:
        kwargs["temperature"] = 0.0

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning("LLM call failed (both attempts): %s", exc)
            return None

    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        logger.warning("LLM call returned empty content (model=%s, effective_max_tokens=%d)", model, effective_max)
        return None

    parsed = _extract_json(raw)
    if isinstance(parsed, dict):
        return parsed

    logger.info("LLM call: could not extract JSON from: %s", raw[:300])
    return None


def _analyze_needed_columns(
    query: str,
    existing_columns: List[str],
    metric: str,
    client: Any,
    model: str,
) -> Dict[str, Any]:
    """Ask the LLM what enrichment columns the query requires.

    The prompt instructs the LLM to scan the *entire* query for column names,
    including columns listed in "currently with columns …" phrasing and
    "replace X with Y" instructions, so that all user-requested columns are
    captured — not just the ones being changed.

    A post-validation step ensures that any derived column whose denominator
    is not yet present gets the missing column auto-added.
    """
    _empty: Dict[str, Any] = {"columns": [], "derived": []}

    example1 = (
        '{"columns":[{"key":"population","label":"Population (est.)","type":"number"},'
        '{"key":"income_group","label":"Income group (est.)","type":"text"}],'
        '"derived":[{"key":"staff_per_capita","label":"' + metric + ' per capita (est.)",'
        '"type":"number","numerator":"value","denominator":"population"}]}'
    )
    example2 = (
        '{"columns":[{"key":"inform_risk_category","label":"INFORM Risk category (est.)","type":"text"},'
        '{"key":"population","label":"Population (est.)","type":"number"}],'
        '"derived":[{"key":"pct_of_population","label":"' + metric + ' as % of population (est.)",'
        '"type":"percent","numerator":"value","denominator":"population"}]}'
    )
    prompt = (
        "You are analysing a data table about countries.\n\n"
        f"User query: {query}\n"
        f"Table metric (the main value column): {metric}\n"
        f"Existing columns already in the table: {', '.join(existing_columns)}\n\n"
        "Task: Identify ALL reference-data columns the user wants added to this table.\n\n"
        "Detection rules:\n"
        "1. Scan the ENTIRE query text. If the user lists desired columns "
        "(e.g. 'Country | INFORM Risk | Population | Staff %'), include EVERY "
        "column from that list that is NOT already in existing columns.\n"
        "2. 'Replace X with Y' or 'instead of X' — include Y as a new column. "
        "Also include any OTHER columns mentioned in the same query.\n"
        "3. If the query mentions a column name ANYWHERE (population, INFORM, "
        "income, HDI, GDP, climate risk, or anything else) and it is not in "
        "existing columns, include it.\n"
        "4. If the query asks for a ratio or percentage (e.g. 'staff as % of "
        "population', 'per capita', 'proportion of population'), include BOTH "
        "the denominator column (e.g. population) AND a derived column.\n"
        "5. When in doubt, INCLUDE the column. It is much better to include an "
        "extra column than to miss one the user asked for.\n\n"
        "Return a JSON object with this exact shape (no other text):\n"
        '{"columns":[{"key":"column_key","label":"Display Label (est.)","type":"number|text"}],\n'
        ' "derived":[{"key":"derived_key","label":"Label (est.)",\n'
        '             "type":"number|percent","numerator":"value","denominator":"column_key"}]}\n\n'
        "Examples:\n\n"
        f"1. Query about per capita and income group:\n{example1}\n\n"
        "2. Query says 'replace INFORM Severity with INFORM Risk category' "
        f"and also mentions Population and Staff as % of population:\n{example2}\n\n"
        'Return {"columns":[],"derived":[]} ONLY if the query truly needs no extra columns.\n'
        "IMPORTANT: Your entire response must be a single JSON object, nothing else."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a data analysis assistant. Identify which reference-data "
                "columns to add to a country table based on the user's query. "
                "Respond with exactly one JSON object and nothing else."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    parsed = _llm_call_with_json_fallback(client, model, messages, max_tokens=512)
    if not parsed:
        logger.warning("Enrichment column analysis: no valid response from LLM")
        return _empty

    cols = parsed.get("columns") or []
    derived = parsed.get("derived") or []
    if not isinstance(cols, list):
        cols = []
    if not isinstance(derived, list):
        derived = []

    col_key_set = set(existing_columns) | {
        c["key"] for c in cols if isinstance(c, dict) and c.get("key")
    }
    for d in derived:
        if not isinstance(d, dict):
            continue
        den = d.get("denominator", "")
        if den and den != "value" and den not in col_key_set:
            cols.append({
                "key": den,
                "label": f"{den.replace('_', ' ').title()} (est.)",
                "type": "number",
            })
            col_key_set.add(den)

    return {"columns": cols, "derived": derived}


def _generate_enrichment_values(
    countries: List[Dict[str, str]],
    columns: List[Dict[str, str]],
    client: Any,
    model: str,
) -> Dict[str, Dict[str, Any]]:
    """Batch LLM calls to fill enrichment column values."""
    col_specs = "\n".join(f"- {c['key']}: {c['label']} ({c.get('type', 'text')})" for c in columns)
    col_keys = [c["key"] for c in columns]

    def _call_batch(batch: List[Dict[str, str]], batch_idx: int) -> Dict[str, Dict[str, Any]]:
        t0 = _time.monotonic()
        country_list = json.dumps(batch, ensure_ascii=False)
        prompt = (
            f"For each country, provide values for these columns:\n{col_specs}\n\n"
            "Return a JSON object: {\"countries\":[{\"iso3\":\"XXX\"," + ",".join(f'"{k}":...' for k in col_keys) + "}]}\n"
            "Use best available data.  For numeric columns return numbers.\n"
            "IMPORTANT: Your entire response must be a single JSON object, nothing else.\n\n"
            f"Countries:\n{country_list}"
        )
        messages = [
            {"role": "system", "content": "You are a data assistant. You respond with exactly one JSON object and nothing else."},
            {"role": "user", "content": prompt},
        ]
        parsed = _llm_call_with_json_fallback(client, model, messages, max_tokens=8192)
        if not parsed:
            logger.warning("Enrichment batch %d: no valid JSON from LLM (%.1fs)", batch_idx, _time.monotonic() - t0)
            return {}

        result_rows = parsed.get("countries") if isinstance(parsed, dict) else None
        if not isinstance(result_rows, list):
            result_rows = list(parsed.values())[0] if isinstance(parsed, dict) else []
            if not isinstance(result_rows, list):
                result_rows = []

        result: Dict[str, Dict[str, Any]] = {}
        for entry in result_rows:
            if not isinstance(entry, dict):
                continue
            iso3 = str(entry.get("iso3") or "").strip().upper()
            if not _valid_iso3(iso3):
                continue
            vals: Dict[str, Any] = {}
            for col in columns:
                rv = entry.get(col["key"])
                if col.get("type") == "number":
                    try:
                        vals[col["key"]] = int(float(rv)) if rv is not None else None
                    except (ValueError, TypeError):
                        vals[col["key"]] = None
                else:
                    vals[col["key"]] = str(rv or "").strip() or None
            result[iso3] = vals

        logger.info(
            "Enrichment batch %d: %d countries in %.1fs",
            batch_idx, len(result), _time.monotonic() - t0,
        )
        return result

    batches = [
        countries[i: i + _ENRICHMENT_BATCH_SIZE]
        for i in range(0, len(countries), _ENRICHMENT_BATCH_SIZE)
    ]
    merged: Dict[str, Dict[str, Any]] = {}

    try:
        workers = min(_ENRICHMENT_MAX_WORKERS, len(batches))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_call_batch, batch, idx): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures, timeout=_ENRICHMENT_TIMEOUT):
                try:
                    merged.update(future.result(timeout=10))
                except Exception as exc:
                    logger.warning("Enrichment batch %d failed: %s", futures[future], exc)
    except TimeoutError:
        for f, idx in futures.items():
            if f.done():
                try:
                    merged.update(f.result(timeout=0))
                except Exception:
                    pass
        logger.warning(
            "Enrichment timed out: %d/%d batches",
            sum(1 for f in futures if f.done()), len(batches),
        )
    except Exception as exc:
        logger.warning("Enrichment failed: %s", exc, exc_info=True)

    return merged


def _looks_like_inline_stat_summary(stripped: str) -> bool:
    """True when a pipe-heavy line is coverage / KPI prose, not a table header.

    Agent summaries often include lines like
    ``Counts - Cash: 0 | CEA: 0 | … (286 plans analysed)`` which must not be
    fed into the enrichment column detector (it invents bogus columns).
    """
    s = stripped.lower()
    if stripped.count("|") < 2:
        return False
    if "plans analysed" in s or "plans analyzed" in s:
        return True
    if _STAT_LINE_PLANS_RE.search(s):
        return True
    if "coverage:" in s and re.search(r"\d+\s*/\s*\d+", stripped):
        return True
    if "countries with" in s and "out of" in s and re.search(r"\d+", stripped):
        return True
    if "counts" in s and "cea" in s and ":" in stripped:
        return True
    if (
        "livelihoods" in s
        and "social protection" in s
        and "cash" in s
        and re.search(r":\s*\d", stripped)
    ):
        return True
    cells_raw = stripped.split("|")
    cells = [c.strip() for c in cells_raw if c.strip()]
    if len(cells) >= 4:
        numish = 0
        for c in cells:
            ct = re.sub(r"[*_`]", "", c).strip()
            if re.fullmatch(r"[\d,\.\s%:]+", ct) or re.search(r":\s*[\d,]+$", ct):
                numish += 1
        if numish >= max(3, int(len(cells) * 0.55)):
            return True
    return False


def _unified_plans_focus_wants_reference_enrichment(combined_text: str) -> bool:
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


def _table_enrichment_model() -> str:
    """Model for table column analysis + per-country enrichment (not agent reasoning)."""
    try:
        from flask import current_app, has_request_context

        if has_request_context():
            m = (current_app.config.get("AI_TABLE_ENRICHMENT_MODEL") or "").strip()
            if m:
                return m
    except Exception:
        pass
    return "gpt-4o-mini"


def _extract_answer_column_hints(answer_text: str) -> str:
    """Extract column names from the agent answer text.

    Detects two patterns:
    1. Markdown table headers: ``| Country | Population | ... |``
    2. Inline pipe-separated lists in prose: ``...columns: Country | Region | Population | ...``

    Returns a comma-separated string of column names for the enrichment
    prompt, or ``""`` if none are found.
    """
    if not answer_text:
        return ""

    for line in answer_text.split("\n"):
        stripped = line.strip()

        if stripped.count("|") < 3:
            continue

        if _looks_like_inline_stat_summary(stripped):
            continue

        cells_raw = stripped.split("|")
        cells = [c.strip().strip(".").strip() for c in cells_raw if c.strip().strip(".").strip()]

        if not cells:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue

        numeric_count = sum(
            1 for c in cells
            if c.replace(",", "").replace(".", "").replace("%", "").replace(" ", "").isdigit()
        )
        if numeric_count > len(cells) // 2:
            continue

        if len(cells[0]) > 80:
            parts = re.split(r"[.:]\s+", cells[0])
            cells[0] = parts[-1].strip()
        if len(cells[-1]) > 80:
            parts = re.split(r"[.]\s+", cells[-1])
            cells[-1] = parts[0].strip()

        clean = [c for c in cells if 1 < len(c) < 60]
        if len(clean) >= 3:
            return ", ".join(clean)

    return ""


def _apply_enrichment(
    table_payload: Dict[str, Any],
    query: str,
    client: Any,
    model: str,
    answer_text: str = "",
) -> Dict[str, Any]:
    """Dynamically enrich a table payload with LLM-determined columns."""
    rows = table_payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return table_payload

    enrichment_model = _table_enrichment_model()

    if table_payload.get("table_kind") == "unified_plans_focus":
        combined = f"{query or ''}\n{answer_text or ''}"
        if not _unified_plans_focus_wants_reference_enrichment(combined):
            return table_payload

    existing_columns = [c for c in table_payload.get("columns", []) if isinstance(c, dict) and c.get("key")]
    existing_keys = [c["key"] for c in existing_columns]
    existing_key_set = set(existing_keys)
    _reserved_table_keys = frozenset({"country_name", "country", "region", "iso3", "value"})

    def _already_present(key: str) -> bool:
        if key in existing_key_set:
            return True
        key_lower = (key or "").strip().lower()
        return key_lower in _reserved_table_keys

    metric = (table_payload.get("metric") or "Value").rstrip(". ")

    answer_hints = _extract_answer_column_hints(answer_text)
    enrichment_query = query
    if answer_hints:
        enrichment_query = f"{query}\nColumns the user expects in the table: {answer_hints}"

    t0 = _time.monotonic()
    spec = _analyze_needed_columns(
        enrichment_query, existing_keys, metric, client, enrichment_model
    )
    cols_to_add = [
        c for c in spec.get("columns", [])
        if isinstance(c, dict) and c.get("key") and not _already_present(c["key"])
    ]
    derived = [
        d for d in spec.get("derived", [])
        if isinstance(d, dict) and d.get("key") and not _already_present(d["key"])
    ]

    if not cols_to_add and not derived:
        logger.info("Enrichment analysis: no columns needed (%.1fs)", _time.monotonic() - t0)
        return table_payload

    logger.info(
        "Enrichment analysis: %d columns + %d derived in %.1fs",
        len(cols_to_add), len(derived), _time.monotonic() - t0,
    )

    countries_list = [
        {"iso3": r.get("iso3", ""), "name": r.get("country_name", "")}
        for r in rows if isinstance(r, dict) and r.get("iso3")
    ]
    if not countries_list:
        return table_payload

    col_keys = [c["key"] for c in cols_to_add]
    enriched_vals: Dict[str, Dict[str, Any]] = {}
    uncached: List[Dict[str, str]] = []

    global _cache, _cache_ts  # noqa: PLW0603
    with _cache_lock:
        now = _time.time()
        if _cache and (now - _cache_ts) > _ENRICHMENT_CACHE_TTL:
            _cache.clear()
            _cache_ts = 0.0

        for c in countries_list:
            iso3 = c["iso3"].upper()
            cached = {}
            all_hit = True
            for ck in col_keys:
                key = (iso3, ck)
                if key in _cache:
                    cached[ck] = _cache[key]
                else:
                    all_hit = False
            if all_hit and cached:
                enriched_vals[iso3] = cached
            else:
                uncached.append(c)

    if uncached:
        generated = _generate_enrichment_values(uncached, cols_to_add, client, enrichment_model)
        enriched_vals.update(generated)
        with _cache_lock:
            for iso3, vals in generated.items():
                for ck, cv in vals.items():
                    _cache[(iso3, ck)] = cv
            if not _cache_ts:
                _cache_ts = _time.time()
    else:
        logger.info("Enrichment: all %d countries served from cache", len(enriched_vals))

    if not enriched_vals:
        logger.warning("Enrichment: no data returned")
        return table_payload

    new_columns = list(table_payload.get("columns", []))
    value_idx = next(
        (i for i, c in enumerate(new_columns) if c.get("key") == "value"),
        len(new_columns),
    )
    for col in reversed(cols_to_add):
        new_columns.insert(value_idx, {
            "key": col["key"],
            "label": col["label"],
            "sortable": True,
            "type": col.get("type", "text"),
        })

    for der in derived:
        ins = next(
            (i for i, c in enumerate(new_columns) if c.get("key") == "value"),
            len(new_columns),
        ) + 1
        label = der.get("label", "").replace("{metric}", metric)
        new_columns.insert(ins, {
            "key": der["key"],
            "label": label,
            "sortable": True,
            "type": der.get("type", "number"),
        })

    new_rows: List[Dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        iso3 = str(row.get("iso3") or "").strip().upper()
        ev = enriched_vals.get(iso3, {})
        for col in cols_to_add:
            row[col["key"]] = ev.get(col["key"])
        for der in derived:
            num_key = der.get("numerator", "value")
            den_key = der.get("denominator", "")
            num = row.get(num_key)
            den = row.get(den_key)
            if isinstance(num, (int, float)) and isinstance(den, (int, float)) and den > 0:
                row[der["key"]] = round(num / den * 100, 4)
            else:
                row[der["key"]] = None
        new_rows.append(row)

    enriched = dict(table_payload)
    enriched["columns"] = new_columns
    enriched["rows"] = new_rows
    enriched["enriched"] = True
    logger.info(
        "Enrichment completed in %.1fs — %d/%d countries",
        _time.monotonic() - t0, len(enriched_vals), len(rows),
    )
    return enriched


# ── Core scanning logic ──────────────────────────────────────────────────


def _scan_steps(
    steps: List[Dict[str, Any]],
    query: str,
) -> Dict[str, Dict[str, Any]]:
    """Walk *steps* (most-recent-first), returning the best payload per slot."""
    best: Dict[str, Dict[str, Any]] = {}
    best_scores: Dict[str, float] = {}

    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        obs = _parse_obs(step.get("observation"))
        if not obs:
            continue
        if obs.get("skipped"):
            continue
        if "success" in obs and not obs.get("success"):
            continue
        data = _inner(obs)

        for predicate, builder, slot, _priority in _REGISTRY:
            try:
                if not predicate(data):
                    continue
            except Exception:
                continue

            try:
                payload = builder(data, query)
            except Exception:
                continue
            if not payload:
                continue

            score = payload.pop("_score", 0)
            if slot not in best or score > best_scores.get(slot, -1):
                best[slot] = payload
                best_scores[slot] = score

    return best


# ── Public API ───────────────────────────────────────────────────────────


def infer_payloads(
    steps: List[Dict[str, Any]],
    query: str = "",
    user_context: Optional[Dict[str, Any]] = None,
    client: Any = None,
    model: str = "",
    answer_text: str = "",
) -> Dict[str, Any]:
    """Scan agent steps and build all applicable visualisation payloads.

    Returns a dict that may contain any combination of ``chart_payload``,
    ``map_payload``, ``table_payload``, and ``output_hint``.

    *answer_text*, when provided, lets the enrichment pipeline detect
    column names the user expects (e.g. from a markdown table the agent
    drafted) even when the rewritten query doesn't list them explicitly.
    """
    if not steps:
        return {}

    user_context = user_context or {}
    best = _scan_steps(steps, query)

    if not best:
        return {}

    result = _apply_viz_preferences(best, query, user_context)

    if "table_payload" in result and client:
        try:
            result["table_payload"] = _apply_enrichment(
                result["table_payload"], query, client, model,
                answer_text=answer_text,
            )
        except Exception as exc:
            logger.warning("Enrichment failed (non-fatal): %s", exc)

    return result


def build_payload_from_tool_result(
    tool_result: Any,
    query: str = "",
) -> Dict[str, Any]:
    """Build payloads from a single tool result (fast-path helper).

    Same registry-based detection as :func:`infer_payloads` but operates on
    one observation instead of a list of steps.
    """
    obs = _parse_obs(tool_result)
    if not obs:
        return {}
    if "success" in obs and not obs.get("success"):
        return {}
    data = _inner(obs)

    best: Dict[str, Dict[str, Any]] = {}
    best_scores: Dict[str, float] = {}

    for predicate, builder, slot, _priority in _REGISTRY:
        try:
            if not predicate(data):
                continue
        except Exception:
            continue
        try:
            payload = builder(data, query)
        except Exception:
            continue
        if not payload:
            continue
        score = payload.pop("_score", 0)
        if slot not in best or score > best_scores.get(slot, -1):
            best[slot] = payload
            best_scores[slot] = score

    return best
