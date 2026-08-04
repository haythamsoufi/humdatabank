"""Analytics helpers: indicator resolution, dedupe, and global trend aggregation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from databank_client import (
    get_indicator,
    get_public_data_all_pages,
    search_indicators,
)

# Canonical headcount metrics (FDRS / UPR). indicator_id when known avoids search.
CANONICAL_METRICS: Dict[str, Dict[str, Any]] = {
    "volunteers": {
        "indicator_id": 724,
        "name": "Number of people volunteering.",
        "fdrs_kpi_code": "KPI_PeopleVol",
        "aliases": (
            "volunteers",
            "volunteer",
            "total volunteers",
            "number of volunteers",
            "people volunteering",
            "volunteer count",
        ),
    },
    "staff": {
        "indicator_id": None,
        "name": "Number of staff",
        "fdrs_kpi_code": None,
        "aliases": ("staff", "number of staff", "total staff"),
        "search": "number of staff",
    },
    "branches": {
        "indicator_id": None,
        "name": "Number of branches",
        "fdrs_kpi_code": "KPI_noBranches",
        "aliases": ("branches", "number of branches", "total branches"),
        "search": "number of branches",
    },
    "local_units": {
        "indicator_id": None,
        "name": "Number of local units",
        "fdrs_kpi_code": None,
        "aliases": ("local units", "local unit", "number of local units"),
        "search": "number of local units",
    },
}

QUALIFIER_PENALTIES = (
    "trained",
    "insurance",
    "insured",
    "accident",
    "retention",
    "rate",
    "percentage",
    "covered",
    "active volunteers trained",
    "community health",
    "first aid volunteers",
)

DIMENSION_KEYS = frozenset(
    {
        "arrays",
        "form_items",
        "countries",
        "national_societies",
        "indicator_bank",
        "assignment_statuses",
        "matrix_cells",
        "dynamic_data",
        "repeat_data",
        "dynamic_context",
    }
)

SEARCH_SUMMARY_FIELDS = (
    "id",
    "name",
    "type",
    "unit",
    "fdrs_kpi_code",
    "sector",
    "tags",
    "emergency",
    "archived",
)


def slim_indicator(indicator: Dict[str, Any]) -> Dict[str, Any]:
    out = {field: indicator.get(field) for field in SEARCH_SUMMARY_FIELDS}
    sector = indicator.get("sector")
    if isinstance(sector, dict):
        out["sector_primary"] = sector.get("primary")
    return out


def slim_public_data_response(
    payload: Dict[str, Any],
    *,
    include_dimensions: bool = False,
) -> Dict[str, Any]:
    if include_dimensions:
        return payload
    return {key: value for key, value in payload.items() if key not in DIMENSION_KEYS}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _match_canonical(query: str) -> Optional[Tuple[str, Dict[str, Any], float]]:
    q = _normalize(query)
    if not q:
        return None
    if q.isdigit():
        return None
    best_key: Optional[str] = None
    best_score = 0.0
    for key, meta in CANONICAL_METRICS.items():
        for alias in meta.get("aliases", ()):
            alias_norm = _normalize(alias)
            if q == alias_norm:
                return key, meta, 1.0
            if alias_norm in q or q in alias_norm:
                score = 0.92 if alias_norm in q else 0.85
                if score > best_score:
                    best_key = key
                    best_score = score
    if best_key and best_score >= 0.85:
        return best_key, CANONICAL_METRICS[best_key], best_score
    return None


def _stem_token(token: str) -> str:
    t = token.rstrip("s")
    if t.endswith("ing") and len(t) > 5:
        t = t[:-3]
    return t


def _score_indicator(query: str, indicator: Dict[str, Any]) -> float:
    q = _normalize(query)
    name = _normalize(indicator.get("name") or "")
    if not q or not name:
        return 0.0
    score = 0.0
    if q == name.rstrip("."):
        score = 1.0
    elif name.rstrip(".").startswith(q):
        score = 0.9
    elif q in name:
        score = 0.75
    else:
        tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
        name_words = [w for w in re.split(r"[^a-z0-9]+", name) if w]
        if tokens and all(
            any(_stem_token(t) in _stem_token(w) or w.startswith(_stem_token(t)) for w in name_words)
            for t in tokens
        ):
            score = 0.65

    fdrs = _normalize(indicator.get("fdrs_kpi_code") or "")
    if fdrs and fdrs in q:
        score = max(score, 0.95)

    tags = indicator.get("tags") or []
    if isinstance(tags, list) and "FDRS" in tags:
        score += 0.05

    if indicator.get("type") == "number":
        score += 0.03

    name_l = name
    if any(p in name_l for p in QUALIFIER_PENALTIES):
        generic = any(
            g in q
            for g in ("volunteer", "staff", "branch", "local unit", "total", "number of")
        )
        if generic:
            score -= 0.35

    if indicator.get("fdrs_kpi_code") and score >= 0.5:
        score += 0.08

    return max(0.0, min(1.0, score))


def resolve_indicator(
    query: str,
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    """Resolve a natural-language or numeric indicator reference."""
    raw = (query or "").strip()
    if not raw:
        raise ValueError("query is required")

    if raw.isdigit():
        indicator = get_indicator(int(raw))
        slim = slim_indicator(indicator)
        return {
            "query": raw,
            "best_match": {**slim, "confidence": 1.0, "match_reason": "numeric_id"},
            "alternatives": [],
        }

    canonical = _match_canonical(raw)
    if canonical:
        key, meta, confidence = canonical
        indicator_id = meta.get("indicator_id")
        if indicator_id is not None:
            indicator = get_indicator(int(indicator_id))
            slim = slim_indicator(indicator)
            return {
                "query": raw,
                "canonical_metric": key,
                "best_match": {
                    **slim,
                    "confidence": confidence,
                    "match_reason": "canonical_alias",
                },
                "alternatives": [],
            }
        search_term = meta.get("search") or meta.get("name") or key
        search_result = search_indicators(search=search_term)
        ranked = _rank_indicators(raw, search_result.get("indicators") or [])
        if not ranked:
            raise ValueError(f"No indicator found for canonical metric '{key}'")
        best, best_score = ranked[0]
        alts = [
            {**slim_indicator(ind), "confidence": round(score, 3)}
            for ind, score in ranked[1:limit]
        ]
        return {
            "query": raw,
            "canonical_metric": key,
            "best_match": {
                **slim_indicator(best),
                "confidence": round(best_score, 3),
                "match_reason": "canonical_search",
            },
            "alternatives": alts,
        }

    search_result = search_indicators(search=raw)
    ranked = _rank_indicators(raw, search_result.get("indicators") or [])
    if not ranked:
        return {"query": raw, "best_match": None, "alternatives": []}

    best, best_score = ranked[0]
    alts = [
        {**slim_indicator(ind), "confidence": round(score, 3)}
        for ind, score in ranked[1:limit]
    ]
    return {
        "query": raw,
        "best_match": {
            **slim_indicator(best),
            "confidence": round(best_score, 3),
            "match_reason": "search_ranked",
        },
        "alternatives": alts,
    }


def _rank_indicators(
    query: str,
    indicators: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], float]]:
    scored = [(ind, _score_indicator(query, ind)) for ind in indicators]
    scored = [(ind, s) for ind, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].get("id", 0)))
    return scored


def search_indicators_ranked(
    *,
    search: str = "",
    indicator_type: str = "",
    sector: str = "",
    sub_sector: str = "",
    emergency: str = "",
    archived: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    result = search_indicators(
        search=search,
        indicator_type=indicator_type,
        sector=sector,
        sub_sector=sub_sector,
        emergency=emergency,
        archived=archived,
    )
    indicators = result.get("indicators") or []
    ranked = _rank_indicators(search or indicator_type or sector, indicators)
    cap = max(1, min(int(limit), 50))
    slimmed = [
        {**slim_indicator(ind), "relevance": round(score, 3)}
        for ind, score in ranked[:cap]
    ]
    return {
        "indicators": slimmed,
        "count": len(slimmed),
        "total_matches": len(indicators),
    }


def parse_num_value(row: Dict[str, Any]) -> Optional[float]:
    val = row.get("num_value")
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    raw = row.get("value")
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def dedupe_rows(
    rows: List[Dict[str, Any]],
    *,
    strategy: str = "latest_submission",
) -> List[Dict[str, Any]]:
    if strategy != "latest_submission":
        raise ValueError(f"Unsupported dedupe strategy: {strategy}")

    best: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for row in rows:
        if row.get("data_status") != "available":
            continue
        key = (row.get("country_id"), row.get("period_name"))
        prev = best.get(key)
        sid = row.get("submission_id") or 0
        if prev is None or sid > (prev.get("submission_id") or 0):
            best[key] = row
    return list(best.values())


def _period_sort_key(period_name: str) -> Tuple[Any, ...]:
    name = period_name or ""
    m = re.search(r"(20\d{2})", name)
    year = int(m.group(1)) if m else 9999
    semi = 1 if re.search(r"jan|jun|half|semi|h1|h2", name, re.I) else 0
    return (year, semi, name)


def aggregate_global_trend(
    *,
    indicator_bank_id: Optional[int] = None,
    query: str = "",
    period_name: str = "",
    dedupe: str = "latest_submission",
    include_country_breakdown: bool = False,
    max_pages: int = 20,
) -> Dict[str, Any]:
    """Fetch public data and return deduplicated global totals grouped by period."""
    indicator_meta: Dict[str, Any]
    resolved_from: Optional[str] = None

    if indicator_bank_id is not None:
        indicator_meta = slim_indicator(get_indicator(int(indicator_bank_id)))
    elif query.strip():
        resolved = resolve_indicator(query.strip(), limit=1)
        best = resolved.get("best_match")
        if not best or not best.get("id"):
            raise ValueError(f"Could not resolve indicator for query: {query!r}")
        indicator_bank_id = int(best["id"])
        indicator_meta = {
            k: v
            for k, v in best.items()
            if k not in ("confidence", "match_reason", "relevance")
        }
        resolved_from = resolved.get("match_reason") or resolved.get("canonical_metric")
    else:
        raise ValueError("Provide indicator_bank_id or query")

    raw = get_public_data_all_pages(
        indicator_bank_id=indicator_bank_id,
        period_name=period_name.strip() or None,
        related="page",
        per_page=5000,
        max_pages=max_pages,
    )
    rows = raw.get("data") or []
    deduped = dedupe_rows(rows, strategy=dedupe)

    by_period: Dict[str, Dict[str, Any]] = {}
    country_lookup: Dict[str, Dict[int, float]] = {}

    for row in deduped:
        period = row.get("period_name") or "Unknown"
        val = parse_num_value(row)
        if val is None:
            continue
        bucket = by_period.setdefault(
            period,
            {"period_name": period, "total": 0.0, "countries_reporting": 0},
        )
        bucket["total"] += val
        bucket["countries_reporting"] += 1
        if include_country_breakdown:
            country_lookup.setdefault(period, {})[int(row.get("country_id") or 0)] = val

    periods = sorted(by_period.values(), key=lambda p: _period_sort_key(p["period_name"]))
    for bucket in periods:
        bucket["total"] = round(bucket["total"])

    notes = [
        "Totals sum deduplicated public submissions across all National Societies.",
        "Dedupe keeps the latest submission_id per (country_id, period_name).",
        "Only rows with data_status='available' are included.",
        "Semi-annual periods (e.g. Jan-Jun 2024) are separate from full-year periods.",
    ]
    if raw.get("truncated"):
        notes.append(raw.get("warning") or "Pagination truncated; totals may be incomplete.")

    out: Dict[str, Any] = {
        "indicator": indicator_meta,
        "indicator_bank_id": indicator_bank_id,
        "resolved_from": resolved_from,
        "dedupe_strategy": f"{dedupe}_per_country_period",
        "raw_rows_fetched": len(rows),
        "rows_after_dedupe": len(deduped),
        "by_period": periods,
        "notes": notes,
        "truncated": bool(raw.get("truncated")),
    }
    if include_country_breakdown:
        out["by_country_period"] = country_lookup
    return out
