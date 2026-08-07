"""Compact public analytics for Custom GPT and other external integrations."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.services.indicators.bank_service import IndicatorBankFilters, get_indicator_list

CANONICAL_METRICS: Dict[str, Dict[str, Any]] = {
    "volunteers": {
        "indicator_id": 724,
        "name": "Number of people volunteering.",
        "search": "number of volunteers",
    },
}

SEARCH_SUMMARY_FIELDS = ("id", "name", "type", "unit", "fdrs_kpi_code", "sector")

# Known questionnaire template ids, for informational labelling only (not a security boundary).
_TEMPLATE_PROGRAMME_LABELS: Dict[int, str] = {
    21: "FDRS",
    22: "UPR",
    24: "UPR",
}

COUNTRY_SEARCH_SUMMARY_FIELDS = ("id", "name", "iso3", "iso2", "region")


def _slim_indicator(indicator: Dict[str, Any]) -> Dict[str, Any]:
    out = {field: indicator.get(field) for field in SEARCH_SUMMARY_FIELDS}
    sector = indicator.get("sector")
    if isinstance(sector, dict):
        out["sector_primary"] = sector.get("primary")
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def resolve_indicator_query(query: str, *, limit: int = 5) -> Dict[str, Any]:
    raw = (query or "").strip()
    if not raw:
        return {"query": raw, "best_match": None, "alternatives": []}

    if raw.isdigit():
        indicator_id = int(raw)
        return {
            "query": raw,
            "best_match": {"id": indicator_id, "match_reason": "numeric_id"},
            "alternatives": [],
        }

    q = _normalize(raw)
    if raw.isdigit():
        pass  # handled above
    elif "volunteer" in q and "staff" not in q:
        meta = CANONICAL_METRICS["volunteers"]
        return {
            "query": raw,
            "best_match": {
                "id": meta["indicator_id"],
                "name": meta.get("name"),
                "match_reason": "canonical:volunteers",
            },
            "alternatives": [],
        }

    filters = IndicatorBankFilters(search=raw)
    indicators, _total, _page, _per_page = get_indicator_list(
        filters, page=1, per_page=max(limit + 5, 10)
    )
    ranked = sorted(
        indicators,
        key=lambda ind: (
            0 if "volunteer" in _normalize(ind.get("name", "")) and "trained" not in _normalize(ind.get("name", "")) else 1,
            ind.get("id") or 0,
        ),
    )
    if not ranked:
        return {"query": raw, "best_match": None, "alternatives": []}

    best = ranked[0]
    alts = [_slim_indicator(ind) for ind in ranked[1 : limit + 1]]
    return {
        "query": raw,
        "best_match": {**_slim_indicator(best), "match_reason": "search_ranked"},
        "alternatives": alts,
    }


def _parse_num_value(row: Dict[str, Any]) -> Optional[float]:
    val = row.get("num_value")
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    raw = row.get("value")
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    match = re.search(r"(20\d{2})", name)
    year = int(match.group(1)) if match else 9999
    semi = 1 if re.search(r"jan|jun|half|semi|h1|h2", name, re.I) else 0
    return (year, semi, name)


def fetch_public_data_rows(
    *,
    indicator_bank_id: int,
    period_name: Optional[str] = None,
    max_pages: int = 20,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Paginate GET /api/v1/data internally (slim public responses)."""
    from app.routes.api.data import get_all_data

    rows: List[Dict[str, Any]] = []
    page = 1
    total_pages = 1
    truncated = False
    cap = max(1, min(int(max_pages), 20))

    while page <= min(cap, total_pages):
        query: Dict[str, Any] = {
            "indicator_bank_id": indicator_bank_id,
            "page": page,
            "per_page": 5000,
        }
        if period_name:
            query["period_name"] = period_name

        with current_app.test_request_context("/api/v1/data", query_string=query):
            resp = get_all_data()

        if resp.status_code != 200:
            raise ValueError(f"Public data fetch failed (HTTP {resp.status_code})")

        payload = resp.get_json() or {}
        rows.extend(payload.get("data") or [])
        total_pages = int(payload.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1

    truncated = total_pages > cap
    return rows, truncated


def fetch_public_scoped_rows(
    *,
    template_id: Optional[int] = None,
    indicator_bank_id: Optional[int] = None,
    period_name: Optional[str] = None,
    country_id: Optional[int] = None,
    max_pages: int = 20,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Paginate GET /api/v1/data internally, scoped by template_id and/or indicator_bank_id.

    Same anonymous-request code path as :func:`fetch_public_data_rows` (and therefore the
    same server-side privacy enforcement: only ``FormItem`` rows with ``privacy=public`` are
    ever returned — see ``app.services.data_retrieval.form.query_form_data``). Unlike
    ``fetch_public_data_rows``, this does not require a specific indicator, so it can scope
    to an entire questionnaire (e.g. ``template_id=21`` for FDRS) to answer "who submitted
    anything public" rather than "who reported this one indicator".
    """
    if template_id is None and indicator_bank_id is None:
        raise ValueError("Provide template_id or indicator_bank_id")

    from app.routes.api.data import get_all_data

    rows: List[Dict[str, Any]] = []
    page = 1
    total_pages = 1
    cap = max(1, min(int(max_pages), 20))

    while page <= min(cap, total_pages):
        query: Dict[str, Any] = {"page": page, "per_page": 5000}
        if template_id is not None:
            query["template_id"] = int(template_id)
        if indicator_bank_id is not None:
            query["indicator_bank_id"] = int(indicator_bank_id)
        if period_name:
            query["period_name"] = period_name
        if country_id is not None:
            query["country_id"] = int(country_id)

        with current_app.test_request_context("/api/v1/data", query_string=query):
            resp = get_all_data()

        if resp.status_code != 200:
            raise ValueError(f"Public data fetch failed (HTTP {resp.status_code})")

        payload = resp.get_json() or {}
        rows.extend(payload.get("data") or [])
        total_pages = int(payload.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1

    truncated = total_pages > cap
    return rows, truncated


def aggregate_global_trend(
    *,
    indicator_bank_id: Optional[int] = None,
    query: str = "",
    period_name: str = "",
    max_pages: int = 20,
) -> Dict[str, Any]:
    """Return deduplicated global totals grouped by period (compact JSON)."""
    resolved_from: Optional[str] = None
    indicator_meta: Dict[str, Any]

    if indicator_bank_id is not None:
        indicator_meta = {"id": int(indicator_bank_id)}
    elif query.strip():
        resolved = resolve_indicator_query(query.strip(), limit=1)
        best = resolved.get("best_match") or {}
        if not best.get("id"):
            raise ValueError(f"Could not resolve indicator for query: {query!r}")
        indicator_bank_id = int(best["id"])
        indicator_meta = {k: v for k, v in best.items() if k != "match_reason"}
        resolved_from = best.get("match_reason")
    else:
        raise ValueError("Provide indicator_bank_id or query")

    rows, truncated = fetch_public_data_rows(
        indicator_bank_id=int(indicator_bank_id),
        period_name=period_name.strip() or None,
        max_pages=max_pages,
    )
    deduped = _dedupe_rows(rows)

    by_period: Dict[str, Dict[str, Any]] = {}
    for row in deduped:
        period = row.get("period_name") or "Unknown"
        val = _parse_num_value(row)
        if val is None:
            continue
        bucket = by_period.setdefault(
            period,
            {"period_name": period, "total": 0.0, "countries_reporting": 0},
        )
        bucket["total"] += val
        bucket["countries_reporting"] += 1

    periods = sorted(by_period.values(), key=lambda p: _period_sort_key(p["period_name"]))
    for bucket in periods:
        bucket["total"] = round(bucket["total"])

    notes = [
        "Totals sum deduplicated public submissions across all National Societies.",
        "Dedupe keeps the latest submission_id per (country_id, period_name).",
        "Only rows with data_status='available' are included.",
    ]
    if truncated:
        notes.append(f"Stopped after {max_pages} pages; totals may be incomplete.")

    return {
        "indicator": indicator_meta,
        "indicator_bank_id": indicator_bank_id,
        "resolved_from": resolved_from,
        "dedupe_strategy": "latest_submission_per_country_period",
        "raw_rows_fetched": len(rows),
        "rows_after_dedupe": len(deduped),
        "by_period": periods,
        "notes": notes,
        "truncated": truncated,
    }


def aggregate_submission_coverage(
    *,
    template_id: Optional[int] = None,
    indicator_bank_id: Optional[int] = None,
    query: str = "",
    period_name: str = "",
    country_id: Optional[int] = None,
    max_pages: int = 20,
) -> Dict[str, Any]:
    """
    Count distinct countries with at least one public submitted value, grouped by period.

    Answers questions like "how many countries submitted an annual FDRS report in 2024
    (or across all years)?" using the same public/anonymous data path as
    :func:`aggregate_global_trend` — a country counts as having "submitted" only if it has
    at least one row with ``data_status='available'`` on a ``privacy=public`` form item for
    the requested template/indicator. This is **public data coverage**, not internal
    assignment/workflow status (submitted/pending/approved), which is never exposed to
    unauthenticated callers.
    """
    if template_id is None and indicator_bank_id is None and not query.strip():
        raise ValueError("Provide template_id, indicator_bank_id, or query")

    resolved_from: Optional[str] = None
    indicator_meta: Optional[Dict[str, Any]] = None
    if indicator_bank_id is None and query.strip():
        resolved = resolve_indicator_query(query.strip(), limit=1)
        best = resolved.get("best_match") or {}
        if best.get("id"):
            indicator_bank_id = int(best["id"])
            indicator_meta = {k: v for k, v in best.items() if k != "match_reason"}
            resolved_from = best.get("match_reason")

    rows, truncated = fetch_public_scoped_rows(
        template_id=template_id,
        indicator_bank_id=indicator_bank_id,
        period_name=period_name.strip() or None,
        country_id=country_id,
        max_pages=max_pages,
    )

    available = [row for row in rows if row.get("data_status") == "available"]

    by_period: Dict[str, Dict[str, Any]] = {}
    all_country_ids: set = set()
    for row in available:
        period = row.get("period_name") or "Unknown"
        bucket = by_period.setdefault(period, {"period_name": period, "_country_ids": set()})
        cid = row.get("country_id")
        if cid is not None:
            bucket["_country_ids"].add(cid)
            all_country_ids.add(cid)

    periods = [
        {"period_name": bucket["period_name"], "countries_submitted": len(bucket["_country_ids"])}
        for bucket in by_period.values()
    ]
    periods.sort(key=lambda p: _period_sort_key(p["period_name"]))

    programme = _TEMPLATE_PROGRAMME_LABELS.get(int(template_id)) if template_id is not None else None

    notes = [
        "Counts countries with at least one public (privacy=public) value for the requested "
        "template/indicator and period — this is public data coverage, not a count of "
        "internal assignment/workflow status.",
        "Only rows with data_status='available' are counted.",
        "countries_submitted_total is the distinct count across all periods in scope "
        "(all years, unless period_name narrows it).",
    ]
    if truncated:
        notes.append(f"Stopped after {max_pages} pages; counts may be incomplete.")

    return {
        "template_id": template_id,
        "programme": programme,
        "indicator": indicator_meta,
        "indicator_bank_id": indicator_bank_id,
        "resolved_from": resolved_from,
        "period_name_filter": period_name.strip() or None,
        "countries_submitted_total": len(all_country_ids),
        "by_period": periods,
        "raw_rows_fetched": len(rows),
        "notes": notes,
        "truncated": truncated,
    }


def resolve_country_query(query: str, *, limit: int = 5) -> Dict[str, Any]:
    """
    Resolve a country name, ISO2/ISO3 code, or numeric id to Country reference fields.

    ``Country`` is a reference dimension table (~192 rows: id, name, iso2, iso3, region) that
    is already fully public — it is returned unconditionally in the ``countries[]`` array of
    authenticated ``/data`` responses and carries no submission data. Resolving a name to an
    id here avoids paginating a full dimension table just to look up one country.
    """
    from app.models import Country
    from app.utils.api_serialization import format_country_info_minimal

    raw = (query or "").strip()
    if not raw:
        return {"query": raw, "best_match": None, "alternatives": []}

    if raw.isdigit():
        country = Country.query.get(int(raw))
        if not country:
            return {"query": raw, "best_match": None, "alternatives": []}
        return {
            "query": raw,
            "best_match": {**format_country_info_minimal(country), "match_reason": "numeric_id"},
            "alternatives": [],
        }

    q = _normalize(raw)

    def _score(country: "Country") -> float:
        name = _normalize(country.name or "")
        short = _normalize(country.short_name or "")
        iso2 = (country.iso2 or "").strip().lower()
        iso3 = (country.iso3 or "").strip().lower()
        if q == iso2 or q == iso3:
            return 1.0
        if q == name or (short and q == short):
            return 0.95
        if name.startswith(q) or (short and short.startswith(q)):
            return 0.85
        if q in name or (short and q in short):
            return 0.7
        translations = country.name_translations if isinstance(country.name_translations, dict) else {}
        for translated in translations.values():
            if not isinstance(translated, str):
                continue
            norm_translated = _normalize(translated)
            if norm_translated == q:
                return 0.9
            if q in norm_translated:
                return 0.6
        return 0.0

    scored = [(country, _score(country)) for country in Country.query.all()]
    scored = [(country, score) for country, score in scored if score > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].name or ""))

    if not scored:
        return {"query": raw, "best_match": None, "alternatives": []}

    best_country, best_score = scored[0]
    cap = max(1, min(int(limit), 20))
    alternatives = [format_country_info_minimal(country) for country, _ in scored[1 : cap + 1]]
    return {
        "query": raw,
        "best_match": {
            **format_country_info_minimal(best_country),
            "match_reason": "search_ranked",
            "relevance": round(best_score, 3),
        },
        "alternatives": alternatives,
    }
