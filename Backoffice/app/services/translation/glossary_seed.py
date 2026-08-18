"""Seed must-tier glossary terms from Indicator Bank and Common Words."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, Tuple

from app.extensions import db

logger = logging.getLogger(__name__)


def _upsert_term(source: str, target: str, target_lang: str, origin: str) -> bool:
    from app.models.translation_quality import TranslationGlossaryTerm

    source = (source or "").strip()
    target = (target or "").strip()
    if not source or not target or source.lower() == target.lower() and target_lang != "en":
        if not source or not target:
            return False
    if target_lang == "en":
        return False
    row = TranslationGlossaryTerm.query.filter_by(
        source_term=source, source_lang="en", target_lang=target_lang
    ).first()
    if row:
        return False
    db.session.add(
        TranslationGlossaryTerm(
            source_term=source,
            source_lang="en",
            target_term=target,
            target_lang=target_lang,
            tier="must",
            origin=origin,
            is_active=True,
        )
    )
    return True


def _iter_name_pairs(name: str, translations: dict | None) -> Iterable[Tuple[str, str, str]]:
    source = (name or "").strip()
    if not source or not isinstance(translations, dict):
        return
    for lang, val in translations.items():
        text = (val or "").strip()
        if lang and lang != "en" and text:
            yield source, text, str(lang).lower()


def seed_from_indicator_bank() -> Dict[str, int]:
    """Insert must-terms from indicator/sector/unit/SPEF names and Common Words."""
    from app.models.indicator_bank import (
        CommonWord,
        IndicatorBank,
        IndicatorBankSpef,
        IndicatorBankType,
        IndicatorBankUnit,
        Sector,
        SubSector,
    )

    added = 0
    try:
        for row in IndicatorBank.query.filter(IndicatorBank.archived.is_(False)).all():
            for src, tgt, lang in _iter_name_pairs(row.name, row.name_translations):
                if _upsert_term(src, tgt, lang, "indicator_bank"):
                    added += 1
        for model, origin in (
            (Sector, "sector"),
            (SubSector, "subsector"),
            (IndicatorBankType, "indicator_type"),
            (IndicatorBankUnit, "indicator_unit"),
            (IndicatorBankSpef, "spef"),
        ):
            for row in model.query.all():
                name = getattr(row, "name", None)
                trans = getattr(row, "name_translations", None)
                for src, tgt, lang in _iter_name_pairs(name, trans):
                    if _upsert_term(src, tgt, lang, origin):
                        added += 1
        for row in CommonWord.query.all():
            term = (getattr(row, "term", None) or "").strip()
            meanings = getattr(row, "meaning_translations", None)
            if not term or not isinstance(meanings, dict):
                continue
            for lang, val in meanings.items():
                text = (val or "").strip()
                if lang and lang != "en" and text:
                    if _upsert_term(term, text, str(lang).lower(), "common_word"):
                        added += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("glossary seed failed")
        raise
    return {"added": added}
