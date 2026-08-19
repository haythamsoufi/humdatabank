"""Dashboard metrics for translation quality."""

from __future__ import annotations

from typing import Any, Dict

from flask import current_app

from app.services.translation.catalog_service import (
    PROVENANCE_HUMAN,
    STATUS_APPROVED,
    is_source_locale,
)
from app.services.translation.result_cache import cache_stats


def _empty_locale_bucket() -> Dict[str, Any]:
    return {
        "total": 0,
        "translated": 0,
        "human_approved": 0,
        "machine": 0,
        "unknown": 0,
        "engines": {},
    }


def _configured_target_locales() -> list:
    configured = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    if not configured:
        supported = current_app.config.get("SUPPORTED_LANGUAGES") or []
        configured = [code for code in supported if not is_source_locale(str(code))]
    return [
        str(code).strip().lower()
        for code in configured
        if code and not is_source_locale(str(code))
    ]


def quality_dashboard_payload() -> Dict[str, Any]:
    from app.models.translation_quality import (
        TranslationGlossaryCandidate,
        TranslationGlossaryTerm,
        TranslationString,
    )

    locales = {loc: _empty_locale_bucket() for loc in _configured_target_locales()}
    rows = TranslationString.query.all()
    for row in rows:
        loc = (row.locale or "").strip().lower()
        if not loc or is_source_locale(loc):
            continue
        bucket = locales.setdefault(loc, _empty_locale_bucket())
        bucket["total"] += 1
        if (row.msgstr or "").strip():
            bucket["translated"] += 1
        if row.provenance == PROVENANCE_HUMAN or row.status == STATUS_APPROVED:
            bucket["human_approved"] += 1
        elif row.provenance == "machine":
            bucket["machine"] += 1
            if row.engine:
                bucket["engines"][row.engine] = bucket["engines"].get(row.engine, 0) + 1
        else:
            bucket["unknown"] += 1

    glossary_terms = TranslationGlossaryTerm.query.filter_by(is_active=True).count()
    pending_candidates = TranslationGlossaryCandidate.query.filter_by(status="pending").count()

    human_share = 0.0
    translated = sum(v["translated"] for v in locales.values())
    human = sum(v["human_approved"] for v in locales.values())
    if translated:
        human_share = round(100.0 * human / translated, 1)

    from app.services.translation.catalog_hygiene import filelock_status

    catalog_imported = any(bucket["total"] for bucket in locales.values())

    return {
        "locales": locales,
        "catalog_imported": catalog_imported,
        "glossary_terms": int(glossary_terms),
        "pending_candidates": int(pending_candidates),
        "human_approved_share_pct": human_share,
        "cache": cache_stats(),
        "filelock_protection": filelock_status(),
        "glossary_hit_note": (
            "Hit-rate is counted on new MT calls that match a must-term "
            "(see translation_result_cache + glossary_forcing)."
        ),
    }
