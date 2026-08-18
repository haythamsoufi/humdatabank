"""CRUD for approved glossary terms in ``translation_glossary_term``."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from app.extensions import db

logger = logging.getLogger(__name__)

VALID_TIERS = ("must", "preferred")
LIST_LIMIT = 10000


class GlossaryTermError(ValueError):
    """Invalid glossary term payload."""


def _clean_source(text: str) -> str:
    from app.services.translation.glossary_llm import usable_glossary_term

    cleaned = usable_glossary_term(text, max_words=12, max_chars=500)
    if not cleaned:
        raise GlossaryTermError("invalid_source")
    return cleaned[:500]


def _clean_target(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        raise GlossaryTermError("invalid_target")
    return cleaned[:500]


def _clean_lang(code: str) -> str:
    lang = (code or "").strip().lower().replace("-", "_").split("_", 1)[0]
    if not lang or lang == "en":
        raise GlossaryTermError("invalid_lang")
    return lang


def _clean_tier(tier: Optional[str], default: str = "must") -> str:
    value = (tier or default or "must").strip().lower()
    if value not in VALID_TIERS:
        raise GlossaryTermError("invalid_tier")
    return value


def serialize_term(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "source_term": row.source_term,
        "source_lang": row.source_lang,
        "target_term": row.target_term,
        "target_lang": row.target_lang,
        "tier": row.tier,
        "origin": row.origin,
        "is_active": bool(row.is_active),
    }


def list_glossary_terms(
    *,
    target_lang: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = LIST_LIMIT,
) -> Dict[str, Any]:
    from app.models.translation_quality import TranslationGlossaryTerm

    q = TranslationGlossaryTerm.query
    if not include_inactive:
        q = q.filter_by(is_active=True)
    lang = (target_lang or "").strip().lower()
    if lang:
        q = q.filter_by(target_lang=lang)
    needle = " ".join((search or "").split())
    if needle:
        like = f"%{needle}%"
        q = q.filter(
            or_(
                TranslationGlossaryTerm.source_term.ilike(like),
                TranslationGlossaryTerm.target_term.ilike(like),
            )
        )
    total = q.count()
    rows = (
        q.order_by(
            func.lower(TranslationGlossaryTerm.source_term).asc(),
            TranslationGlossaryTerm.target_lang.asc(),
            TranslationGlossaryTerm.id.asc(),
        )
        .limit(max(1, min(int(limit or LIST_LIMIT), LIST_LIMIT)))
        .all()
    )
    return {
        "items": [serialize_term(r) for r in rows],
        "total": total,
        "shown": len(rows),
    }


def serialize_candidate(row) -> Dict[str, Any]:
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    return {
        "id": row.id,
        "source_term": row.source_term,
        "target_term": row.target_term,
        "target_lang": row.target_lang,
        "extractor": row.extractor,
        "confidence": float(row.confidence or 0),
        "proposed_tier": row.proposed_tier,
        "occurrence_count": int(row.occurrence_count or 1),
        "conflict": bool(evidence.get("conflict")),
        "official_term": evidence.get("official_term") or "",
    }


def list_glossary_candidates(*, limit: int = LIST_LIMIT) -> Dict[str, Any]:
    from app.models.translation_quality import TranslationGlossaryCandidate

    q = TranslationGlossaryCandidate.query.filter_by(status="pending")
    total = q.count()
    rows = (
        q.order_by(TranslationGlossaryCandidate.confidence.desc())
        .limit(max(1, min(int(limit or LIST_LIMIT), LIST_LIMIT)))
        .all()
    )
    items = [serialize_candidate(r) for r in rows]
    items.sort(key=lambda item: (0 if item.get("conflict") else 1, -(item.get("confidence") or 0)))
    return {
        "items": items,
        "total": total,
        "shown": len(items),
        "conflicts": sum(1 for item in items if item.get("conflict")),
    }


def upsert_glossary_term(
    *,
    source_term: str,
    target_term: str,
    target_lang: str,
    tier: Optional[str] = "must",
    origin: str = "manual",
) -> Dict[str, Any]:
    from app.models.translation_quality import TranslationGlossaryTerm

    src = _clean_source(source_term)
    tgt = _clean_target(target_term)
    lang = _clean_lang(target_lang)
    term_tier = _clean_tier(tier)
    row = TranslationGlossaryTerm.query.filter_by(
        source_term=src,
        source_lang="en",
        target_lang=lang,
    ).first()
    if row is None:
        row = TranslationGlossaryTerm(
            source_term=src,
            source_lang="en",
            target_term=tgt,
            target_lang=lang,
            tier=term_tier,
            origin=(origin or "manual")[:50],
            is_active=True,
        )
        db.session.add(row)
    else:
        row.target_term = tgt
        row.tier = term_tier
        row.is_active = True
        if origin and row.origin in (None, "", "manual"):
            row.origin = origin[:50]
    db.session.commit()
    return serialize_term(row)


def update_glossary_term(
    term_id: int,
    *,
    source_term: Optional[str] = None,
    target_term: Optional[str] = None,
    target_lang: Optional[str] = None,
    tier: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    from app.models.translation_quality import TranslationGlossaryTerm

    row = TranslationGlossaryTerm.query.get(int(term_id))
    if row is None:
        raise GlossaryTermError("not_found")
    if source_term is not None:
        row.source_term = _clean_source(source_term)
    if target_term is not None:
        row.target_term = _clean_target(target_term)
    if target_lang is not None:
        row.target_lang = _clean_lang(target_lang)
    if tier is not None:
        row.tier = _clean_tier(tier, default=row.tier or "must")
    if is_active is not None:
        row.is_active = bool(is_active)
    clash = (
        TranslationGlossaryTerm.query.filter_by(
            source_term=row.source_term,
            source_lang=row.source_lang or "en",
            target_lang=row.target_lang,
        )
        .filter(TranslationGlossaryTerm.id != row.id)
        .first()
    )
    if clash is not None:
        db.session.rollback()
        raise GlossaryTermError("duplicate")
    db.session.commit()
    return serialize_term(row)
