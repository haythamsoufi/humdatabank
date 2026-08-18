"""Optional prose translation memory. Off until TRANSLATION_MEMORY_PROSE_ENABLED=true."""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from app.extensions import db


def prose_memory_enabled() -> bool:
    return str(os.getenv("TRANSLATION_MEMORY_PROSE_ENABLED") or "").strip().lower() == "true"


def source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def lookup_exact(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    if not prose_memory_enabled() or not text:
        return None
    from app.models.translation_quality import TranslationMemoryEntry

    row = (
        TranslationMemoryEntry.query.filter_by(
            source_hash=source_hash(text),
            source_lang=source_lang,
            target_lang=target_lang,
            is_active=True,
        )
        .first()
    )
    return row.target_text if row else None


def remember(source: str, target: str, source_lang: str, target_lang: str, *, origin: str = "manual") -> None:
    if not prose_memory_enabled() or not source or not target:
        return
    from app.models.translation_quality import TranslationMemoryEntry

    digest = source_hash(source)
    row = TranslationMemoryEntry.query.filter_by(
        source_hash=digest, source_lang=source_lang, target_lang=target_lang
    ).first()
    if row:
        row.target_text = target
        row.origin = origin
        row.is_active = True
    else:
        db.session.add(
            TranslationMemoryEntry(
                source_text=source,
                target_text=target,
                source_lang=source_lang,
                target_lang=target_lang,
                source_hash=digest,
                origin=origin,
            )
        )
    db.session.commit()
