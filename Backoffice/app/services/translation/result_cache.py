"""MT result cache keyed on source hash + language pair + engine."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Bump when post-processing changes (e.g. glossary enforce vs token-splice)
# so stale rows are not reused.
RESULT_CACHE_GENERATION = "v3"


def source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _engine_key(engine: str) -> str:
    base = (engine or "default").strip() or "default"
    return f"{base}:{RESULT_CACHE_GENERATION}"


def get_cached(text: str, source_lang: str, target_lang: str, engine: str) -> Optional[str]:
    """Return a stored translation for this exact source text and language pair.

    Prefer a row for *engine*, then any engine. Narrative retries often land on
    Libre after IFRC fails; requiring the same engine key forced a full re-MT.
    """
    try:
        from app.models.translation_quality import TranslationResultCache

        rows = (
            TranslationResultCache.query.filter_by(
                source_hash=source_hash(text),
                source_lang=source_lang,
                target_lang=target_lang,
            ).all()
        )
        if not rows:
            return None
        wanted = _engine_key(engine)
        for row in rows:
            if row.engine == wanted and row.translated_text:
                return row.translated_text
        for row in rows:
            if row.translated_text:
                return row.translated_text
    except Exception:
        logger.debug("translation result cache read skipped", exc_info=True)
    return None


def get_cached_many(
    texts: list[str], source_lang: str, target_lang: str, engine: str
) -> dict[str, str]:
    """Batched ``get_cached``: one query for many texts instead of one per text.

    Returns ``{text: translated_text}`` for every text with a cached row
    (engine match preferred, else any engine — same precedence as
    ``get_cached``). Texts without a hit are simply absent from the result.
    """
    unique_texts = list(dict.fromkeys(text for text in texts if text))
    if not unique_texts:
        return {}
    try:
        from app.models.translation_quality import TranslationResultCache

        hash_to_text = {source_hash(text): text for text in unique_texts}
        rows = (
            TranslationResultCache.query.filter(
                TranslationResultCache.source_hash.in_(hash_to_text.keys()),
                TranslationResultCache.source_lang == source_lang,
                TranslationResultCache.target_lang == target_lang,
            ).all()
        )
        wanted = _engine_key(engine)
        best: dict[str, str] = {}
        fallback: dict[str, str] = {}
        for row in rows:
            text = hash_to_text.get(row.source_hash)
            if not text or not row.translated_text:
                continue
            if row.engine == wanted:
                best.setdefault(text, row.translated_text)
            else:
                fallback.setdefault(text, row.translated_text)
        return {**fallback, **best}
    except Exception:
        logger.debug("translation result cache batch read skipped", exc_info=True)
        return {}


def put_cached_many(
    items: list[tuple[str, str]], source_lang: str, target_lang: str, engine: str
) -> None:
    """Batched ``put_cached``: upsert many rows and commit once instead of per row.

    ``items`` is a list of ``(text, translated)`` pairs; repeated *text*
    values are collapsed (last write wins) so one batch can never violate the
    ``(source_hash, source_lang, target_lang, engine)`` unique constraint.
    """
    deduped: dict[str, str] = {}
    for text, translated in items:
        if text and translated:
            deduped[text] = translated
    if not deduped:
        return
    try:
        from app.extensions import db
        from app.models.translation_quality import TranslationResultCache

        engine_key = _engine_key(engine)
        digests = {text: source_hash(text) for text in deduped}
        existing = {
            row.source_hash: row
            for row in TranslationResultCache.query.filter(
                TranslationResultCache.source_hash.in_(digests.values()),
                TranslationResultCache.source_lang == source_lang,
                TranslationResultCache.target_lang == target_lang,
                TranslationResultCache.engine == engine_key,
            ).all()
        }
        for text, translated in deduped.items():
            digest = digests[text]
            row = existing.get(digest)
            if row:
                row.translated_text = translated
            else:
                db.session.add(
                    TranslationResultCache(
                        source_hash=digest,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        engine=engine_key,
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
            logger.debug("result cache batch rollback failed", exc_info=True)
        logger.debug("translation result cache batch write skipped", exc_info=True)


def put_cached(text: str, source_lang: str, target_lang: str, engine: str, translated: str) -> None:
    if not text or not translated:
        return
    try:
        from app.extensions import db
        from app.models.translation_quality import TranslationResultCache

        digest = source_hash(text)
        engine_key = _engine_key(engine)
        row = TranslationResultCache.query.filter_by(
            source_hash=digest,
            source_lang=source_lang,
            target_lang=target_lang,
            engine=engine_key,
        ).first()
        if row:
            row.translated_text = translated
        else:
            db.session.add(
                TranslationResultCache(
                    source_hash=digest,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    engine=engine_key,
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
