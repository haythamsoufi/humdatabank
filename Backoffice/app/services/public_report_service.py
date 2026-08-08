"""Country report builder for Custom GPT Actions and the MCP connector.

The single, canonical implementation behind both ``GET /public/reports/country``
(Custom GPT's ``getCountryReport`` Action) and the MCP connector's
``databank_build_country_report`` tool, which proxies this same endpoint over HTTP
(see ``humanitarian-databank-mcp/databank_client.get_country_report``) rather than
duplicating the orchestration. Composes country/period resolution, a curated FDRS
headline KPI bundle, a multi-period trend, and cited narrative themes from public
documents into one compact report spec — calling the existing public
analytics/document *services* directly in-process (no HTTP round-trip to itself).

This module never renders HTML or charts — callers (Custom GPT, or the LLM behind
the MCP tool) render the actual visual one-pager themselves from the returned JSON,
optionally guided by :func:`get_report_template`.

Scope for v1:
  - "fdrs"     -> curated FDRS headline KPI bundle + a multi-period trend (template 21)
  - "upr"      -> narrative themes from public Unified Plan/Report/Midyear Report
                  documents only (not UPR-specific numeric indicators on template 22/24)
  - "combined" -> both of the above (default)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.services.public_analytics_service import (
    _dedupe_rows,
    _parse_num_value,
    aggregate_submission_coverage,
    fetch_public_scoped_rows,
    resolve_country_query,
)
from app.services.public_document_service import search_public_documents
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

# Curated FDRS headline bundle for country one-pagers — the same governance,
# finance, and reach KPI codes already used for FDRS data-quality scoring
# (see app/services/data_quality/catalogs/fdrs_v1_catalog.py:
# GOVERNANCE_KPI_CODES, REACH_KPI_CODES, FINANCE_TOTAL_INCOME/EXPENDITURE).
# Resolved to indicator_bank_id via fdrs_kpi_code, not hardcoded ids, so this
# stays correct even if the indicator bank differs across environments.
HEADLINE_KPIS: Tuple[Dict[str, str], ...] = (
    {"code": "KPI_PeopleVol", "label": "Volunteers"},
    {"code": "KPI_PStaff", "label": "Staff"},
    {"code": "KPI_noBranches", "label": "Branches"},
    {"code": "KPI_noLocalUnits", "label": "Local units"},
    {"code": "KPI_GB", "label": "Governing board members"},
    {"code": "KPI_IncomeLC_CHF", "label": "Total income (CHF)"},
    {"code": "KPI_expenditureLC_CHF", "label": "Total expenditure (CHF)"},
    {"code": "KPI_DonBlood", "label": "Blood donations"},
    {"code": "KPI_TrainFA", "label": "People trained in first aid"},
)

# The flagship indicator charted as a multi-period trend line (page 1 of the one-pager).
TREND_KPI_CODE = "KPI_PeopleVol"

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_MIDYEAR_HINT_RE = re.compile(r"jan-?jun|half|semi|\bh1\b|\bh2\b|mid|myr", re.IGNORECASE)

# fdrs_kpi_code -> indicator_bank_id, cached per worker process. A direct filtered
# query is already cheap (indicator_bank is a few hundred rows), but this avoids
# re-querying it once per KPI per report when fdrs_kpi_code assignments essentially
# never change at runtime.
_kpi_code_index_cache: Optional[Dict[str, int]] = None

_REPORT_STYLES_DIR = Path(__file__).resolve().parent.parent / "report_styles"


def _extract_year(text: str) -> Optional[int]:
    match = _YEAR_RE.search(text or "")
    return int(match.group(0)) if match else None


def _is_midyear_hint(text: str) -> bool:
    return bool(_MIDYEAR_HINT_RE.search(text or ""))


def _period_sort_key(period_name: str) -> Tuple[int, int, str]:
    name = period_name or ""
    year = _extract_year(name) or 9999
    semi = 1 if _is_midyear_hint(name) else 0
    return (year, semi, name)


def _resolve_headline_kpi_ids() -> Dict[str, int]:
    """Map each headline ``fdrs_kpi_code`` to its ``indicator_bank_id``."""
    global _kpi_code_index_cache
    if _kpi_code_index_cache is None:
        from app.models import IndicatorBank

        codes = [kpi["code"] for kpi in HEADLINE_KPIS]
        rows = (
            IndicatorBank.query.filter(IndicatorBank.fdrs_kpi_code.in_(codes))
            .with_entities(IndicatorBank.fdrs_kpi_code, IndicatorBank.id)
            .all()
        )
        _kpi_code_index_cache = {code: int(indicator_id) for code, indicator_id in rows if code}
    return dict(_kpi_code_index_cache)


def resolve_period_for_country(*, country_id: int, period_hint: str = "") -> Dict[str, Any]:
    """Find the FDRS period_name closest to period_hint for one country, plus the prior one.

    There is no public ``/periods`` endpoint, so this discovers real ``period_name``
    values from :func:`aggregate_submission_coverage` (scoped to this country) rather
    than guessing label formats — periods are free-text (e.g. "Annual 2024", "Jan-Jun
    2026").
    """
    try:
        coverage = aggregate_submission_coverage(template_id=FDRS_TEMPLATE_ID, country_id=country_id)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, this is best-effort discovery
        current_app.logger.warning("Submission coverage lookup failed for country_id=%s: %s", country_id, exc)
        return {
            "available_periods": [],
            "resolved_period": None,
            "prior_period": None,
            "requested_year": None,
            "match_note": f"Could not load submission coverage: {exc}",
        }

    available = sorted(
        {
            bucket["period_name"]
            for bucket in (coverage.get("by_period") or [])
            if bucket.get("countries_submitted") and bucket.get("period_name")
        },
        key=_period_sort_key,
    )

    result: Dict[str, Any] = {
        "available_periods": available,
        "resolved_period": None,
        "prior_period": None,
        "requested_year": None,
        "match_note": None,
    }
    if not available:
        result["match_note"] = "No public FDRS data found for this country in any period."
        return result

    hint = (period_hint or "").strip()
    hint_year = _extract_year(hint)
    hint_midyear = _is_midyear_hint(hint) if hint else False
    if hint_year is None and hint_midyear:
        hint_year = datetime.now(timezone.utc).year
    result["requested_year"] = hint_year

    candidates = available
    if hint_year is not None:
        candidates = [p for p in available if _extract_year(p) == hint_year]
        if not candidates:
            result["match_note"] = (
                f"No public FDRS data for {hint_year}; latest available period is {available[-1]}."
            )
            return result

    if hint_midyear:
        mid_candidates = [p for p in candidates if _is_midyear_hint(p)]
        if mid_candidates:
            resolved = sorted(mid_candidates, key=_period_sort_key)[-1]
        else:
            resolved = sorted(candidates, key=_period_sort_key)[-1]
            if hint_year is not None:
                result["match_note"] = (
                    f"No dedicated mid-year period found for {hint_year}; showing {resolved} instead."
                )
    else:
        resolved = sorted(candidates, key=_period_sort_key)[-1]

    idx = available.index(resolved)
    result["resolved_period"] = resolved
    result["prior_period"] = available[idx - 1] if idx > 0 else None
    return result


def _fetch_kpi_series(country_id: int, indicator_id: int) -> Tuple[Dict[str, float], bool]:
    """Every public FDRS value for one indicator/country, keyed by period_name.

    Always scoped to ``template_id=FDRS_TEMPLATE_ID`` — indicator_bank ids can be
    reused by non-FDRS templates (e.g. UPR planning) under overlapping period_name
    strings, which would otherwise blend unrelated reporting cycles into an FDRS
    trend/KPI. One page (5000 rows) comfortably covers one country's full history
    for a single indicator.
    """
    try:
        rows, truncated = fetch_public_scoped_rows(
            indicator_bank_id=indicator_id,
            template_id=FDRS_TEMPLATE_ID,
            country_id=country_id,
            max_pages=1,
        )
    except Exception as exc:  # noqa: BLE001 - one bad KPI should not fail the whole report
        current_app.logger.warning("KPI series fetch failed for indicator_bank_id=%s: %s", indicator_id, exc)
        return {}, False

    values: Dict[str, float] = {}
    for row in _dedupe_rows(rows):
        period = row.get("period_name")
        if not period:
            continue
        val = _parse_num_value(row)
        if val is not None:
            values[period] = val
    return values, truncated


def _fetch_all_kpi_series(
    country_id: int,
    kpi_ids: Dict[str, int],
) -> Dict[str, Tuple[Dict[str, float], bool]]:
    """One scoped fetch per resolved headline KPI, shared by headline values and the trend."""
    return {code: _fetch_kpi_series(country_id, indicator_id) for code, indicator_id in kpi_ids.items()}


def _build_headline_kpis(
    resolved_period: Optional[str],
    prior_period: Optional[str],
    kpi_ids: Dict[str, int],
    series_by_code: Dict[str, Tuple[Dict[str, float], bool]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for kpi in HEADLINE_KPIS:
        code = kpi["code"]
        indicator_id = kpi_ids.get(code)
        if indicator_id is None:
            continue
        series, _truncated = series_by_code.get(code, ({}, False))
        current = series.get(resolved_period) if resolved_period else None
        prior = series.get(prior_period) if prior_period else None
        change_pct = None
        if current is not None and prior not in (None, 0):
            change_pct = round(((current - prior) / prior) * 100, 1)
        out.append(
            {
                "code": code,
                "label": kpi["label"],
                "indicator_bank_id": indicator_id,
                "value": current,
                "prior_value": prior,
                "change_pct": change_pct,
            }
        )
    return out


def _build_trend(
    kpi_ids: Dict[str, int],
    series_by_code: Dict[str, Tuple[Dict[str, float], bool]],
) -> Dict[str, Any]:
    indicator_id = kpi_ids.get(TREND_KPI_CODE)
    trend_label = next((k["label"] for k in HEADLINE_KPIS if k["code"] == TREND_KPI_CODE), TREND_KPI_CODE)
    if indicator_id is None:
        return {"included": False}

    values, truncated = series_by_code.get(TREND_KPI_CODE, ({}, False))
    series = [{"period_name": period, "value": value} for period, value in values.items()]
    series.sort(key=lambda item: _period_sort_key(item["period_name"]))

    return {
        "included": bool(series),
        "indicator_code": TREND_KPI_CODE,
        "indicator_bank_id": indicator_id,
        "label": trend_label,
        "series": series,
        "truncated": truncated,
    }


def _narrative_query(country_name: str, hint_midyear: bool, *, year: Optional[int]) -> str:
    doc_phrase = "midyear report" if hint_midyear else "unified plan annual report"
    year_part = f" {year}" if year is not None else ""
    return f"{country_name} {doc_phrase}{year_part} focus areas achievements"


def _build_narrative(
    country_id: int,
    country_name: str,
    year: int,
    hint_midyear: bool,
) -> Dict[str, Any]:
    """Cited narrative themes from public Unified Plan/Report/Midyear Report chunks.

    Deliberately omits the year from the first search attempt: ``search_public_documents``
    auto-detects a year mentioned in free-text queries and applies it as a hard filter on
    ``document_date``, but that field has been observed to disagree with the actual
    title/content year for at least some real documents — including the year up front can
    silently miss the right document. Omitting it relies on the "snapshot" behavior (newest
    document per country/type), which is what most one-pager requests want. Only retry with
    an explicit year for genuinely historical requests, where "newest" would otherwise be
    the wrong document.
    """
    current_year = datetime.now(timezone.utc).year
    query = _narrative_query(country_name, hint_midyear, year=None)
    try:
        result = search_public_documents(query, country_id=country_id, top_k=6, min_score=0.2)
        chunks = result.get("chunks") or []
        if not chunks and year < current_year:
            query = _narrative_query(country_name, hint_midyear, year=year)
            result = search_public_documents(query, country_id=country_id, top_k=6, min_score=0.2)
            chunks = result.get("chunks") or []
    except Exception as exc:  # noqa: BLE001 - narrative is best-effort, never fail the report for it
        current_app.logger.warning("Narrative search failed for country_id=%s: %s", country_id, exc)
        return {"included": False, "reason": f"Document search failed: {exc}"}

    if not chunks:
        return {
            "included": False,
            "query_used": query,
            "reason": f"No public Unified Plan/Report document found for {country_name}.",
        }

    themes = [
        {
            "content": chunk.get("content"),
            "document_title": chunk.get("document_title"),
            "page_number": chunk.get("page_number"),
            "document_url": chunk.get("document_url"),
        }
        for chunk in chunks[:5]
    ]
    return {
        "included": True,
        "query_used": query,
        "count": len(themes),
        "themes": themes,
    }


def build_country_report(
    *,
    country: str,
    period_hint: str = "",
    report_type: str = "combined",
    include_prior_period: bool = True,
) -> Dict[str, Any]:
    """Assemble a one-country report spec: headline KPIs, a trend, and cited narrative themes."""
    normalized_type = (report_type or "combined").strip().lower()
    if normalized_type not in ("fdrs", "upr", "combined"):
        normalized_type = "combined"

    country_resolution = resolve_country_query(country, limit=5)
    best = country_resolution.get("best_match")
    if not best or not best.get("id"):
        return {
            "ok": False,
            "error": f"Could not resolve country: {country!r}",
            "alternatives": country_resolution.get("alternatives") or [],
        }

    country_id = int(best["id"])
    country_name = best.get("name") or country
    country_meta = {
        "id": country_id,
        "name": country_name,
        "iso2": best.get("iso2"),
        "iso3": best.get("iso3"),
        "region": best.get("region"),
    }

    hint = (period_hint or "").strip()
    hint_midyear = _is_midyear_hint(hint) if hint else False

    period_info: Dict[str, Any] = {
        "available_periods": [],
        "resolved_period": None,
        "prior_period": None,
        "requested_year": None,
        "match_note": None,
    }
    headline_kpis: List[Dict[str, Any]] = []
    trend: Dict[str, Any] = {"included": False}

    if normalized_type in ("fdrs", "combined"):
        period_info = resolve_period_for_country(country_id=country_id, period_hint=hint)
        kpi_ids = _resolve_headline_kpi_ids()
        if period_info.get("resolved_period") and kpi_ids:
            series_by_code = _fetch_all_kpi_series(country_id, kpi_ids)
            prior = period_info.get("prior_period") if include_prior_period else None
            headline_kpis = _build_headline_kpis(period_info["resolved_period"], prior, kpi_ids, series_by_code)
            trend = _build_trend(kpi_ids, series_by_code)

    narrative_year = period_info.get("requested_year") or _extract_year(hint) or datetime.now(timezone.utc).year
    narrative: Dict[str, Any] = {"included": False}
    if normalized_type in ("upr", "combined"):
        narrative = _build_narrative(country_id, country_name, narrative_year, hint_midyear)

    coverage = {
        "fdrs_data_available": any(k.get("value") is not None for k in headline_kpis),
        "narrative_available": bool(narrative.get("included")),
        "period_match_note": period_info.get("match_note"),
    }

    return {
        "ok": True,
        "country": country_meta,
        "report_type": normalized_type,
        "period": {
            "requested": hint or None,
            "resolved": period_info.get("resolved_period"),
            "prior": period_info.get("prior_period"),
            "available_periods": period_info.get("available_periods", []),
        },
        "coverage": coverage,
        "headline_kpis": headline_kpis,
        "trend": trend,
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "visibility": "public_only",
        "source": "IFRC Network Databank public API (databank.ifrc.org) — public data/documents only.",
        "notes": [
            "Numbers reflect public FDRS submissions only (data_status='available' on privacy=public items).",
            "Narrative themes are drawn only from public Unified Plan/Report document chunks — "
            "do not add outside knowledge; cite document_title + page_number per claim.",
            "If coverage.fdrs_data_available or coverage.narrative_available is false, say so "
            "explicitly in the one-pager rather than implying full reporting.",
        ],
    }


def list_report_styles() -> List[str]:
    if not _REPORT_STYLES_DIR.exists():
        return []
    return sorted(p.stem for p in _REPORT_STYLES_DIR.glob("*.html"))


def get_report_template(style: str = "default") -> Dict[str, Any]:
    """Return an HTML/CSS one-pager skeleton plus design tokens for a given style name.

    The caller (Custom GPT, or the MCP connector proxying ``GET /public/reports/template``)
    applies this layout/palette/typography to the report spec from
    :func:`build_country_report` — this function only loads static assets, it does not
    render or merge data itself.
    """
    normalized_style = (style or "default").strip().lower() or "default"
    available = list_report_styles()
    html_path = _REPORT_STYLES_DIR / f"{normalized_style}.html"
    if not html_path.exists():
        return {
            "ok": False,
            "error": f"Unknown template style {normalized_style!r}.",
            "available_styles": available,
        }

    html_template = html_path.read_text(encoding="utf-8")
    tokens_path = _REPORT_STYLES_DIR / f"{normalized_style}.tokens.json"
    design_tokens: Optional[Dict[str, Any]] = None
    if tokens_path.exists():
        try:
            design_tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            design_tokens = None

    return {
        "ok": True,
        "style": normalized_style,
        "available_styles": available,
        "html_template": html_template,
        "design_tokens": design_tokens,
        "usage_notes": [
            "Follow this skeleton's structure, colors, and typography when rendering the "
            "one-pager (as an HTML/canvas artifact, or translated to another renderer).",
            "Replace {{PLACEHOLDER}} tokens with real report data; keep section order and layout.",
            "Repeat the block between <!-- KPI_CARD:start --> and <!-- KPI_CARD:end --> once "
            "per entry in headline_kpis; omit cards whose value is null.",
            "Repeat the block between <!-- THEME_ITEM:start --> and <!-- THEME_ITEM:end --> once "
            "per entry in narrative.themes; omit the whole narrative section if not included.",
            "design_tokens (colors/fonts/spacing) apply even if you render as markdown, React, "
            "or an image-generation prompt instead of raw HTML.",
        ],
    }
