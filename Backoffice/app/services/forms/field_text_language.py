"""Detect whether an entry-form text value is in a different language than the UI.

Focal points type free text in whatever language they work in. Another person
opening the same form, with a different display language selected, should be
able to preview a translation. This module only decides whether that preview
is worth offering. It does not translate and it does not change the stored value.

The browser copy of this heuristic lives in
``app/static/js/forms/modules/field-translation-preview.js``. Keep the two
in step: script detection, the Latin stopword lists, and the confidence bar.
"""

from __future__ import annotations

import re
from typing import Optional

# Below this, the text is too ambiguous to badge (names, codes, one-word notes).
PREVIEW_CONFIDENCE = 0.55

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")

# Letters that identify a language inside an Arabic-script run.
_URDU_CHARS = frozenset("ٹڈڑں")
_PERSIAN_CHARS = frozenset("پچژگ")
_UKRAINIAN_CHARS = frozenset("іїєґ")

# Stopwords that are distinctive enough to separate the languages people
# actually type into narrative fields. Single-letter tokens ("a", "y") are
# left out so a name or a code cannot flip the result.
_LATIN_STOPWORDS = {
    "en": frozenset({
        "the", "and", "of", "to", "in", "for", "with", "from", "that", "this",
        "was", "were", "are", "is", "been", "have", "has", "had", "not", "but",
        "or", "as", "by", "on", "at", "an", "their", "they", "which", "when",
        "where", "what", "who", "into", "over", "after", "before", "because",
        "during", "between", "about", "than", "then", "also", "only", "its",
        "be", "will", "would", "can", "could", "should", "our", "your",
    }),
    "fr": frozenset({
        "les", "des", "une", "dans", "pour", "avec", "sur", "est", "sont",
        "été", "était", "que", "qui", "dont", "cette", "ces", "aux", "par",
        "pas", "plus", "nous", "vous", "ils", "elles", "leur", "comme", "mais",
        "où", "donc", "car", "ainsi", "entre", "après", "avant", "chez", "sous",
        "vers", "depuis", "très", "aussi", "ont", "elle", "cette", "aux",
        "votre", "notre", "merci", "bonjour", "la", "le", "de", "un", "et", "du",
        "au", "en", "à",
    }),
    "es": frozenset({
        "los", "las", "una", "del", "con", "para", "por", "son", "está", "que",
        "como", "más", "pero", "porque", "cuando", "donde", "también", "entre",
        "sobre", "desde", "hasta", "muy", "este", "esta", "estos", "estas",
        "hay", "fue", "fueron", "han", "tiene", "sus", "el", "la", "de", "en",
        "un", "y", "se", "su", "al",
    }),
    "pt": frozenset({
        "não", "uma", "para", "com", "por", "como", "mais", "mas", "também",
        "está", "são", "foi", "foram", "tem", "dos", "das", "nos", "nas",
        "pelo", "pela", "entre", "sobre", "desde", "muito", "este", "esta",
        "isso", "quando", "onde", "porque", "na", "no", "em", "os", "as", "do",
        "da", "ao", "ou", "se",
    }),
    "de": frozenset({
        "und", "der", "die", "das", "den", "dem", "des", "ein", "eine", "nicht",
        "mit", "von", "für", "auf", "ist", "sind", "war", "waren", "auch",
        "nach", "bei", "aus", "zum", "zur", "oder", "aber", "wenn", "wie",
        "sich", "dass", "hat", "haben", "wurde", "wurden", "über", "zwischen",
        "im", "am", "vom", "nicht",
    }),
    "it": frozenset({
        "che", "non", "una", "per", "con", "sono", "come", "più", "anche",
        "questo", "questa", "degli", "delle", "dalla", "nella", "perché",
        "quando", "dove", "dopo", "prima", "molto", "stato", "stata", "hanno",
        "della", "nel", "sul", "sullo", "gli", "uno", "una", "del", "dei",
        "il", "lo", "la", "di", "un", "e", "in", "da", "su",
    }),
}

# Diacritics that belong to one language much more than the others.
_DISTINCTIVE = {
    "es": frozenset("ñ¿¡"),
    "pt": frozenset("ãõ"),
    "fr": frozenset("œæ"),
    "de": frozenset("äöüß"),
}


def normalize_language_code(lang: Optional[str], *, default: str = "en") -> str:
    """Reduce ``fr-FR`` / ``zh_Hans`` to a base ISO code."""
    if not isinstance(lang, str):
        return default
    base = lang.strip().lower().replace("-", "_").split("_", 1)[0]
    if not base or not re.fullmatch(r"[a-z]{2,3}", base):
        return default
    return base


def _script_language(text: str) -> Optional[str]:
    """Return a language code when a non-Latin script dominates the text."""
    urdu = persian = arabic = devanagari = bengali = thai = hangul = 0
    kana = han = cyrillic = ukrainian = greek = hebrew = latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if ch in _UKRAINIAN_CHARS:
            ukrainian += 1
            cyrillic += 1
        elif ch in _URDU_CHARS:
            urdu += 1
            arabic += 1
        elif ch in _PERSIAN_CHARS:
            persian += 1
            arabic += 1
        elif (
            0x0600 <= o <= 0x06FF
            or 0x0750 <= o <= 0x077F
            or 0x08A0 <= o <= 0x08FF
            or 0xFB50 <= o <= 0xFDFF
            or 0xFE70 <= o <= 0xFEFF
        ):
            arabic += 1
        elif 0x0900 <= o <= 0x097F:
            devanagari += 1
        elif 0x0980 <= o <= 0x09FF:
            bengali += 1
        elif 0x0E00 <= o <= 0x0E7F:
            thai += 1
        elif 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            hangul += 1
        elif 0x3040 <= o <= 0x30FF:
            kana += 1
        elif 0x4E00 <= o <= 0x9FFF:
            han += 1
        elif 0x0400 <= o <= 0x04FF:
            cyrillic += 1
        elif 0x0370 <= o <= 0x03FF:
            greek += 1
        elif 0x0590 <= o <= 0x05FF:
            hebrew += 1
        elif ("a" <= ch.lower() <= "z") or ch.lower() in "àáâãäåæçèéêëìíîïñòóôõöùúûüýœ":
            latin += 1

    def _accept(lang: str, count: int) -> Optional[str]:
        if count < 2:
            return None
        # A couple of foreign letters inside an otherwise Latin sentence are a
        # quote, not the language of the field.
        if latin and count < latin and count < 4:
            return None
        return lang

    # Prefer the specific language when its own letters are present, and judge
    # "is this the field's script?" against the whole script run.
    if urdu >= 2:
        return _accept("ur", arabic)
    if persian >= 2:
        return _accept("fa", arabic)
    if kana >= 2:
        return _accept("ja", kana + han)
    if ukrainian >= 2:
        return _accept("uk", cyrillic)

    generic = (
        ("ar", arabic),
        ("hi", devanagari),
        ("bn", bengali),
        ("th", thai),
        ("ko", hangul),
        ("zh", han),
        ("ru", cyrillic),
        ("el", greek),
        ("he", hebrew),
    )
    lang, count = max(generic, key=lambda item: item[1])
    return _accept(lang, count)


def detect_field_text_language(text: str) -> tuple[Optional[str], float]:
    """Best-effort language of a free-text answer.

    Returns ``(None, 0.0)`` when the text is too short or too ambiguous to
    badge. Script detection is high confidence. Latin detection needs several
    stopwords so a person's name does not look like a foreign sentence.
    """
    raw = (text or "").strip()
    if len(raw) < 2:
        return None, 0.0

    script = _script_language(raw)
    if script:
        return script, 0.92

    cleaned = _URL_RE.sub(" ", raw)
    cleaned = _EMAIL_RE.sub(" ", cleaned)
    words = [w.lower() for w in _WORD_RE.findall(cleaned)]
    if len(words) < 3:
        return None, 0.0

    lower = cleaned.lower()
    hits = {lang: 0 for lang in _LATIN_STOPWORDS}
    for word in words:
        for lang, vocab in _LATIN_STOPWORDS.items():
            if word in vocab:
                hits[lang] += 1

    denom = float(len(words))
    scores = {lang: hits[lang] / denom for lang in hits}
    distinctive_hits = {}
    for lang, chars in _DISTINCTIVE.items():
        n = sum(1 for ch in lower if ch in chars)
        distinctive_hits[lang] = n
        scores[lang] = scores.get(lang, 0.0) + min(0.24, n * 0.08)

    best = max(scores, key=scores.get)
    best_score = scores[best]
    ordered = sorted(scores.values(), reverse=True)
    second = ordered[1] if len(ordered) > 1 else 0.0

    if hits.get(best, 0) < 2 and distinctive_hits.get(best, 0) == 0:
        return None, 0.0
    if best_score < 0.18:
        return None, 0.0
    if (best_score - second) < 0.08 and hits.get(best, 0) < 4:
        return None, 0.0

    confidence = min(0.9, 0.45 + best_score)
    return best, confidence


def translation_preview_decision(text: str, display_language: str) -> dict:
    """Whether a field should offer a translation preview.

    ``offer`` is true only when detection is confident and the detected
    language is not the viewer's selected display language.
    """
    display = normalize_language_code(display_language)
    detected, confidence = detect_field_text_language(text)
    offer = bool(detected and detected != display and confidence >= PREVIEW_CONFIDENCE)
    return {
        "offer": offer,
        "detected_language": detected,
        "confidence": round(float(confidence), 4),
        "display_language": display,
    }
