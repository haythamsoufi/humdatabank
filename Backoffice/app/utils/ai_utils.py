"""
Shared AI utilities used across routes and services.

Centralizes duplicate logic for model compatibility, page context sanitization,
and other AI-related helpers to avoid drift and simplify maintenance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Set, Tuple


def openai_model_supports_sampling_params(model_name: str) -> bool:
    """
    Whether the given OpenAI model accepts sampling parameters.

    Some reasoning-focused models (e.g., GPT-5 family) may reject
    temperature, presence_penalty, frequency_penalty.
    """
    m = (model_name or "").strip().lower()
    if m.startswith("gpt-5") and not m.startswith("gpt-5.2"):
        return False
    return True


def sanitize_page_context(value: Any) -> Dict[str, Any]:
    """
    Treat page_context as untrusted input.

    Goals:
    - Keep only a small, predictable shape (reduce prompt injection surface + cost).
    - Avoid storing/sending sensitive URLs or large nested blobs.
    - We intentionally DROP currentUrl to avoid leaking query strings/tokens.
    """
    if not isinstance(value, dict):
        return {}

    def _cap_str(s: Any, n: int) -> str:
        s = "" if s is None else str(s)
        s = s.strip()
        return s if len(s) <= n else (s[:n] + "…")

    out: Dict[str, Any] = {}

    current_page = value.get("currentPage") or value.get("pathname") or value.get("route")
    if current_page:
        out["currentPage"] = _cap_str(current_page, 200)

    page_title = value.get("pageTitle") or value.get("title")
    if page_title:
        out["pageTitle"] = _cap_str(page_title, 200)

    page_data = value.get("pageData")
    if isinstance(page_data, dict):
        pd: Dict[str, Any] = {}
        for k in ("pageType", "selectedIndicator", "selectedRegion", "selectedYear", "country", "indicator", "period"):
            if k in page_data and page_data.get(k) is not None:
                pd[k] = _cap_str(page_data.get(k), 120)
        if pd:
            out["pageData"] = pd

    return out


def normalize_language_code(
    lang: Any,
    *,
    default: str = "en",
    allowed: Optional[Iterable[str]] = None,
) -> str:
    """
    Normalize a user-provided language to an ISO-ish short code (e.g. 'fr_FR' -> 'fr').

    Notes:
    - This is intentionally small and dependency-free (no external langdetect).
    - If `allowed` is provided, any value not in it falls back to `default`.
    """
    if not isinstance(lang, str):
        return default
    s = lang.strip().lower()
    if not s:
        return default
    # Drop region suffixes (en_US, fr-FR, etc.)
    s = re.split(r"[_-]", s, maxsplit=1)[0] or default
    if allowed is None:
        return s
    allowed_set = {str(x).strip().lower() for x in allowed if str(x).strip()}
    return s if s in allowed_set else default


# UPL document title patterns: "UPL-2024-...", "Country 2025 Unified Plan (UPL-2025-...)"
_UPL_YEAR_RE = re.compile(r"UPL-(\d{4})|(\d{4})\s+Unified\s+Plan", re.IGNORECASE)


def extract_upl_year_from_title(title: str) -> Optional[int]:
    """
    Extract the plan year from a Unified Plan (UPL) document title.

    Matches patterns such as:
    - "Vietnam 2024 Unified Plan (UPL-2024-MAAVN002)"
    - "Estonia 2025 Unified Plan (UPL-2025-MAAEE001)"
    - "UPL_SYRIA_2023 (UPL-2023-MAASY002)"

    Returns the four-digit year as int, or None if no year is found.
    """
    if not title or not isinstance(title, str):
        return None
    m = _UPL_YEAR_RE.search(title)
    if not m:
        return None
    for g in m.groups():
        if g:
            y = int(g)
            if 2000 <= y <= 2100:
                return y
    return None


def detect_query_language(
    message: str,
    *,
    allowed: Optional[Iterable[str]] = None,
) -> Tuple[str, float]:
    """
    Best-effort language detection for choosing the LLM response language.

    Returns: (language_code, confidence)

    We rely on:
    - Unicode script detection for ar/ru/zh/hi (high confidence)
    - Latin-script scoring for en/fr/es using:
      * greetings/phrases
      * diacritics (é, ç, ñ, ¿, ¡, …)
      * stopword ratios
    - Low-confidence fallback (so the caller can keep UI language)
    """
    allowed_set: Optional[Set[str]] = None
    if allowed is not None:
        allowed_set = {str(x).strip().lower() for x in allowed if str(x).strip()}

    text = (message or "").strip()
    if not text:
        return ("en", 0.0)

    # Count directional/script hints
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF" or "\uFB50" <= ch <= "\uFDFF" or "\uFE70" <= ch <= "\uFEFF")
    devanagari = sum(1 for ch in text if "\u0900" <= ch <= "\u097F")
    cyrillic = sum(1 for ch in text if "\u0400" <= ch <= "\u04FF")
    han = sum(1 for ch in text if "\u4E00" <= ch <= "\u9FFF")
    hira_kata = sum(1 for ch in text if "\u3040" <= ch <= "\u30FF")

    # Strong script detections
    if arabic > 0:
        lang = "ar"
        if allowed_set is None or lang in allowed_set:
            return (lang, 0.95)
    if devanagari > 0:
        lang = "hi"
        if allowed_set is None or lang in allowed_set:
            return (lang, 0.95)
    if han > 0:
        lang = "zh"
        if allowed_set is None or lang in allowed_set:
            return (lang, 0.90)
    if cyrillic > 0:
        lang = "ru"
        if allowed_set is None or lang in allowed_set:
            return (lang, 0.90)
    if hira_kata > 0:
        lang = "ja"
        if allowed_set is None or lang in allowed_set:
            return (lang, 0.90)

    lower = text.lower()

    # For very short inputs, greetings should dominate.
    stripped = re.sub(r"\s+", " ", lower).strip()
    if stripped:
        # NOTE: keep these intentionally small + high precision.
        fr_greetings = {"bonjour", "salut", "bonsoir", "merci"}
        es_greetings = {"hola", "gracias"}
        # Single-token / tiny-phrase handling
        if len(stripped) <= 30 and len(re.findall(r"\w+", stripped)) <= 4:
            if stripped in fr_greetings or any(g in stripped for g in ("s'il vous",)):
                lang = "fr"
                if allowed_set is None or lang in allowed_set:
                    return (lang, 0.70)
            if stripped in es_greetings or any(g in stripped for g in ("por favor", "¿", "¡")):
                lang = "es"
                if allowed_set is None or lang in allowed_set:
                    return (lang, 0.70)

    # Latin-script scoring for EN/FR/ES (no external deps).
    # Strip obvious noise (URLs, emails, numbers) so stopword ratios behave.
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", lower)
    cleaned = re.sub(r"\S+@\S+\.\S+", " ", cleaned)
    cleaned = re.sub(r"[\d_]+", " ", cleaned)
    cleaned = re.sub(r"[^\w\s'’\-¿¡]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = re.findall(r"[a-zA-ZÀ-ÖØ-öø-ÿ'’¿¡]+", cleaned)
    word_count = len(words)

    # Diacritics / punctuation markers (high precision, low recall)
    fr_diac = sum(1 for ch in lower if ch in "éèêëàâîïôöùûüçœæ")
    es_diac = sum(1 for ch in lower if ch in "ñáéíóúü¿¡")

    # Compact stopword lists (enough to be useful without a dependency).
    en_sw = {
        "the", "and", "to", "of", "in", "for", "on", "with", "is", "are", "was", "were",
        "what", "how", "why", "where", "when", "please", "can", "could", "help", "show",
        "i", "you", "we", "they", "it", "this", "that",
    }
    fr_sw = {
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "avec", "pour", "sur", "dans",
        "est", "sont", "était", "étaient", "que", "qui", "quoi", "comment", "pourquoi", "où", "quand",
        "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "ce", "c", "ça", "merci", "bonjour", "salut",
    }
    es_sw = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o", "con", "para", "por", "en",
        "es", "son", "era", "eran", "que", "quién", "qué", "cómo", "porqué", "por", "dónde", "cuándo",
        "yo", "tú", "usted", "él", "ella", "nosotros", "vosotros", "ellos", "ellas", "gracias", "hola",
    }

    def _norm_token(w: str) -> str:
        w = w.strip("’'").lower()
        # collapse French elision "d’" -> "d"
        if w in {"d’", "d'"}:
            return "d"
        if w in {"c’", "c'"}:
            return "c"
        return w

    en_hits = 0
    fr_hits = 0
    es_hits = 0
    for w in words:
        t = _norm_token(w)
        if t in en_sw:
            en_hits += 1
        if t in fr_sw:
            fr_hits += 1
        if t in es_sw:
            es_hits += 1

    # Score: stopwords dominate for longer text; diacritics help for short/mid text.
    denom = max(1, word_count)
    en_score = en_hits / denom
    fr_score = (fr_hits / denom) + min(0.20, fr_diac * 0.02)
    es_score = (es_hits / denom) + min(0.20, es_diac * 0.02)

    # Pick best Latin language.
    best_lang = "en"
    best_score = en_score
    if fr_score > best_score:
        best_lang, best_score = "fr", fr_score
    if es_score > best_score:
        best_lang, best_score = "es", es_score

    # Convert score to a confidence-ish value in [0.0, 0.85].
    # - For tiny/ambiguous text, keep confidence low so UI language wins.
    if denom <= 2 and best_score < 0.34 and fr_diac == 0 and es_diac == 0:
        best_lang, conf = "en", 0.10
    else:
        # Slightly optimistic mapping; capped.
        conf = min(0.85, 0.30 + best_score * 0.9)

    if allowed_set is not None and best_lang not in allowed_set:
        # Choose any allowed language as the safest fallback
        return (next(iter(sorted(allowed_set))) if allowed_set else "en", 0.10)
    return (best_lang, float(conf))
