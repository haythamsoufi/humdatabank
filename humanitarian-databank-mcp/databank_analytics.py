"""Analytics helpers: indicator search ranking and slim response shaping."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from databank_client import search_indicators

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
