"""MT result cache keyed on source hash + language pair + engine."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def get_cached(text: str, source_lang: str, target_lang: str, engine: str) -> Optional[str]:
    try:
        from app.models.translation_quality import TranslationResultCache

        row = TranslationResultCache.query.filter_by(
            source_hash=source_hash(text),
            source_lang=source_lang,
            target_lang=target_lang,
            engine=engine,
        ).first()
        if row:
            return row.translated_text
    except Exception:
        logger.debug("translation result cache read skipped", exc_info=True)
    return None


def put_cached(text: str, source_lang: str, target_lang: str, engine: str, translated: str) -> None:
    if not text or not translated:
        return
    try:
        from app.extensions import db
        from app.models.translation_quality import TranslationResultCache

        digest = source_hash(text)
        row = TranslationResultCache.query.filter_by(
            source_hash=digest,
            source_lang=source_lang,
            target_lang=target_lang,
            engine=engine,
        ).first()
        if row:
            row.translated_text = translated
        else:
            db.session.add(
                TranslationResultCache(
                    source_hash=digest,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    engine=engine,
                    source_text=text[:8000],
                    translated_text=translated,
                )
            )
        db.session.commit()
    except Exception:
        try:
            from app.extensions import db

            db.session.rollback()
        except Exception:
            logger.debug("result cache rollback failed", exc_info=True)
        logger.debug("translation result cache write skipped", exc_info=True)


def cache_stats() -> dict:
    try:
        from app.models.translation_quality import TranslationResultCache

        return {"rows": int(TranslationResultCache.query.count())}
    except Exception:
        return {"rows": 0}
