"""Force approved glossary terms in machine translation.

Must-terms stay in the English source so the engine can produce natural word
order. After MT, unofficial renderings of those terms are swapped for the
official target form from ``translation_glossary_term``.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

TermPair = Tuple[str, str]
TranslateTermFn = Callable[[str], Optional[str]]


def _db_must_terms(target_lang: str) -> List[TermPair]:
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


def terms_for_target(
    target_lang: str,
    terms: Optional[Sequence[TermPair]] = None,
) -> List[TermPair]:
    """Return (source_en, target) pairs from the glossary table, longest first."""
    rows = list(terms) if terms is not None else _db_must_terms(target_lang)
    return sorted(rows, key=lambda kv: len(kv[0]), reverse=True)


def _english_term_variants(term: str) -> List[str]:
    """Singular/plural English surfaces for a glossary source term."""
    text = " ".join((term or "").split())
    if not text:
        return []
    words = text.split()
    last = words[-1]
    variants = [text]
    if last.endswith("ies") and len(last) > 3:
        variants.append(" ".join(words[:-1] + [last[:-3] + "y"]))
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 1:
        variants.append(" ".join(words[:-1] + [last[:-1]]))
    elif last.endswith("y") and len(last) > 1 and last[-2].lower() not in "aeiou":
        variants.append(" ".join(words[:-1] + [last[:-1] + "ies"]))
    else:
        variants.append(" ".join(words[:-1] + [last + "s"]))
    uniq: List[str] = []
    for item in variants:
        if item and item not in uniq:
            uniq.append(item)
    uniq.sort(key=len, reverse=True)
    return uniq


def _are_related_terms(left: str, right: str) -> bool:
    a = (left or "").lower().strip()
    b = (right or "").lower().strip()
    if not a or not b:
        return False
    if a == b:
        return True
    left_vars = {item.lower() for item in _english_term_variants(a)}
    return b in left_vars


def source_has_must_terms(
    source_text: str,
    target_lang: str,
    terms: Optional[Sequence[TermPair]] = None,
) -> bool:
    return bool(_source_terms_in_text(source_text or "", target_lang, terms=terms))


def _source_terms_in_text(
    source_text: str,
    target_lang: str,
    terms: Optional[Sequence[TermPair]] = None,
) -> List[TermPair]:
    """Non-overlapping glossary hits in the English source, longest first."""
    hits: List[TermPair] = []
    occupied = [False] * len(source_text)
    for src, official in terms_for_target(target_lang, terms=terms):
        if not src:
            continue
        for variant in _english_term_variants(src):
            for match in re.finditer(
                rf"(?<!\w){re.escape(variant)}(?!\w)", source_text, flags=re.IGNORECASE
            ):
                if any(occupied[i] for i in range(match.start(), match.end())):
                    continue
                for i in range(match.start(), match.end()):
                    occupied[i] = True
                hits.append((src, official))
    return hits


def _arabic_match_definiteness(official: str, unofficial: str) -> str:
    """If the model used a definite NP, put ال on the last word of an idafa."""
    unofficial = (unofficial or "").strip()
    official = (official or "").strip()
    if not official or not unofficial:
        return official
    unofficial_def = unofficial.startswith("ال") or " ال" in unofficial
    if not unofficial_def:
        return official
    parts = official.split()
    if not parts:
        return official
    if not parts[-1].startswith("ال"):
        parts[-1] = "ال" + parts[-1]
    return " ".join(parts)


# Arabic broken-plural number pairs. Language morphology, not house-term aliases.
_AR_NUMBER_PAIRS = (
    ("نقطة", "نقاط"),
    ("النقطة", "النقاط"),
)


def _arabic_number_variants(text: str) -> List[str]:
    """نقطة↔نقاط so isolated singular MT still matches in-sentence plurals."""
    seed = (text or "").strip()
    if not seed:
        return []
    found = [seed]
    for singular, plural in _AR_NUMBER_PAIRS:
        if singular in seed:
            found.append(seed.replace(singular, plural))
        if plural in seed:
            found.append(seed.replace(plural, singular))
    uniq: List[str] = []
    for item in found:
        if item and item not in uniq:
            uniq.append(item)
    return uniq


def _arabic_definiteness_surfaces(text: str) -> List[str]:
    found = [text]
    if text.startswith("ال") and len(text) > 3:
        found.append(text[2:])
        return found
    found.append("ال" + text)
    parts = text.split()
    if len(parts) < 2:
        return found
    all_def = [(p if p.startswith("ال") else "ال" + p) for p in parts]
    found.append(" ".join(all_def))
    last_def = list(parts)
    if not last_def[-1].startswith("ال"):
        last_def[-1] = "ال" + last_def[-1]
    found.append(" ".join(last_def))
    first_def = list(parts)
    if not first_def[0].startswith("ال"):
        first_def[0] = "ال" + first_def[0]
    found.append(" ".join(first_def))
    return found


def _surfaces_to_find(unofficial: str, lang: str) -> List[str]:
    text = (unofficial or "").strip()
    if len(text) < 2:
        return []
    if lang != "ar":
        return [text]
    found: List[str] = []
    for seed in _arabic_number_variants(text):
        found.extend(_arabic_definiteness_surfaces(seed))
    # Longest first so we do not splice inside a longer definite NP.
    uniq: List[str] = []
    for surface in found:
        if surface and surface not in uniq:
            uniq.append(surface)
    uniq.sort(key=len, reverse=True)
    return uniq


def _replace_surface(text: str, surface: str, replacement: str) -> str:
    if not surface or surface == replacement:
        return text
    if surface in text:
        return text.replace(surface, replacement)
    return re.sub(rf"(?<!\w){re.escape(surface)}(?!\w)", replacement, text, flags=re.IGNORECASE)


def enforce_glossary_terms(
    source_text: str,
    translated: str,
    target_lang: str,
    translate_term: TranslateTermFn,
    terms: Optional[Sequence[TermPair]] = None,
) -> str:
    """Swap the model's rendering of must-terms for the official target form.

    ``translate_term`` is a short EN→target call (same engine). Related
    singular/plural glossary keys from the DB are included so in-context
    pluralization still matches. ``terms`` is a test override; production
    always reads active must-tier rows.
    """
    if not source_text or not translated:
        return translated
    hits = _source_terms_in_text(source_text, target_lang, terms=terms)
    if not hits:
        return translated

    all_terms = terms_for_target(target_lang, terms=terms)
    out = translated
    for src, official in hits:
        related = [(src, official)]
        for other_src, other_off in all_terms:
            if other_src != src and _are_related_terms(src, other_src):
                related.append((other_src, other_off))
        seen_src = {item[0] for item in related}
        for variant in _english_term_variants(src):
            if variant not in seen_src:
                related.append((variant, official))
                seen_src.add(variant)

        replacements: List[Tuple[str, str]] = []
        for rel_src, rel_official in related:
            try:
                unofficial = translate_term(rel_src)
            except Exception:
                logger.debug("glossary term MT failed for %r", rel_src, exc_info=True)
                unofficial = None
            unofficial = (str(unofficial).strip() if unofficial else "")
            if not unofficial or unofficial == rel_official:
                continue
            for surface in _surfaces_to_find(unofficial, target_lang):
                replacement = rel_official
                if target_lang == "ar":
                    replacement = _arabic_match_definiteness(rel_official, surface)
                if not surface or surface == replacement:
                    continue
                present = surface in out or (
                    target_lang != "ar"
                    and re.search(rf"(?<!\w){re.escape(surface)}(?!\w)", out, flags=re.IGNORECASE)
                )
                if present:
                    replacements.append((surface, replacement))

        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
        for surface, replacement in replacements:
            out = _replace_surface(out, surface, replacement)
    return out


def protect_glossary_terms(
    text: str,
    target_lang: str,
    terms: Optional[Sequence[TermPair]] = None,
) -> Tuple[str, Dict[str, str], int]:
    """
    Replace source terms with opaque tokens. Restore map values are the *target* terms.

    Kept for tests and any remaining callers. Live auto-translate uses
    :func:`enforce_glossary_terms` after MT instead, so word order is preserved.
    """
    if not text:
        return text, {}, 0
    token_map: Dict[str, str] = {}
    hit_count = 0
    out = text
    counter = 10_000  # stay clear of variable-protection counters
    for source, target in terms_for_target(target_lang, terms=terms):
        if not source or source.lower() not in out.lower():
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", flags=re.IGNORECASE)

        def _repl(_m, tgt=target, c=counter):
            nonlocal hit_count, counter
            from app.services.translation.auto_translator import (
                _MT_VAR_TOKEN_PREFIX,
                _make_mt_protection_token,
            )

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
