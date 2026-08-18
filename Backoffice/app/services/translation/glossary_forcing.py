"""Force approved glossary terms through the existing QZXNTK token mechanism."""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from app.services.translation.auto_translator import _make_mt_protection_token, _MT_VAR_TOKEN_PREFIX

logger = logging.getLogger(__name__)

# House terms that must not drift. Target forms are official IFRC wording.
_STATIC_MUST_TERMS: Dict[str, Dict[str, str]] = {
    "Focal Point": {"fr": "point focal", "es": "punto focal", "ar": "نقطة اتصال", "ru": "координатор", "zh": "协调人", "hi": "फोकल पॉइंट"},
    "Focal Points": {"fr": "points focaux", "es": "puntos focales", "ar": "نقاط اتصال", "ru": "координаторы", "zh": "协调人", "hi": "फोकल पॉइंट"},
    "National Society": {"fr": "Société nationale", "es": "Sociedad Nacional", "ar": "الجمعية الوطنية", "ru": "Национальное общество", "zh": "国家红会", "hi": "राष्ट्रीय सोसाइटी"},
    "National Societies": {"fr": "Sociétés nationales", "es": "Sociedades Nacionales", "ar": "الجمعيات الوطنية", "ru": "Национальные общества", "zh": "国家红会", "hi": "राष्ट्रीय सोसाइटियाँ"},
    "IFRC": {"fr": "IFRC", "es": "IFRC", "ar": "IFRC", "ru": "IFRC", "zh": "IFRC", "hi": "IFRC"},
    "CEA": {"fr": "CEA", "es": "CEA", "ar": "CEA", "ru": "CEA", "zh": "CEA", "hi": "CEA"},
    "CVA": {"fr": "CVA", "es": "CVA", "ar": "CVA", "ru": "CVA", "zh": "CVA", "hi": "CVA"},
    "PGI": {"fr": "PGI", "es": "PGI", "ar": "PGI", "ru": "PGI", "zh": "PGI", "hi": "PGI"},
    "FDRS": {"fr": "FDRS", "es": "FDRS", "ar": "FDRS", "ru": "FDRS", "zh": "FDRS", "hi": "FDRS"},
    "UPR": {"fr": "UPR", "es": "UPR", "ar": "UPR", "ru": "UPR", "zh": "UPR", "hi": "UPR"},
}


def _db_must_terms(target_lang: str) -> List[Tuple[str, str]]:
    try:
        from app.models.translation_quality import TranslationGlossaryTerm

        rows = (
            TranslationGlossaryTerm.query.filter_by(
                is_active=True,
                source_lang="en",
                target_lang=target_lang,
                tier="must",
            )
            .all()
        )
        return [(r.source_term, r.target_term) for r in rows if r.source_term and r.target_term]
    except Exception:
        logger.debug("glossary db terms unavailable", exc_info=True)
        return []


def terms_for_target(target_lang: str) -> List[Tuple[str, str]]:
    """Return (source_en, target) pairs, longest first so compounds win."""
    merged: Dict[str, str] = {}
    for src, by_lang in _STATIC_MUST_TERMS.items():
        tgt = by_lang.get(target_lang)
        if tgt:
            merged[src] = tgt
    for src, tgt in _db_must_terms(target_lang):
        merged[src] = tgt
    return sorted(merged.items(), key=lambda kv: len(kv[0]), reverse=True)


def protect_glossary_terms(text: str, target_lang: str) -> Tuple[str, Dict[str, str], int]:
    """
    Replace source terms with opaque tokens. Restore map values are the *target* terms.

    Returns (protected_text, token_to_target, hit_count).
    """
    if not text:
        return text, {}, 0
    token_map: Dict[str, str] = {}
    hit_count = 0
    out = text
    counter = 10_000  # stay clear of variable-protection counters
    for source, target in terms_for_target(target_lang):
        if not source or source.lower() not in out.lower():
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", flags=re.IGNORECASE)

        def _repl(_m, tgt=target, c=counter):
            nonlocal hit_count, counter
            token = _make_mt_protection_token(_MT_VAR_TOKEN_PREFIX, counter)
            counter += 1
            token_map[token] = tgt
            hit_count += 1
            return token

        out, n = pattern.subn(_repl, out)
        if n:
            counter += n
    return out, token_map, hit_count


def restore_glossary_tokens(text: str, token_map: Dict[str, str]) -> str:
    if not text or not token_map:
        return text
    restored = text
    for token, target in token_map.items():
        restored = restored.replace(token, target)
    return restored
