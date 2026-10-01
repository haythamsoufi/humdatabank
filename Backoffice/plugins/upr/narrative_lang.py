"""Detect the language of an uploaded UPR narrative.

The visuals export language is only the translation *target*. Narratives are
not stored as English, so the source has to be read off the document itself.
Detection is local and deterministic: script blocks for non-Latin text, then
stopword scores for Latin text. Short or ambiguous Latin falls back to English,
which keeps unlabeled chrome and proper nouns on the historical English path.
"""

from __future__ import annotations

import re
from collections import Counter

# (language or script key, pattern). First matching *dominant* script wins;
# "cyrl" / "arab" / "deva" are disambiguated below.
_SCRIPT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ja", re.compile(r"[\u3040-\u30ff]")),
    ("ko", re.compile(r"[\uac00-\ud7af]")),
    ("zh", re.compile(r"[\u4e00-\u9fff]")),
    ("arab", re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")),
    ("he", re.compile(r"[\u0590-\u05ff]")),
    ("hy", re.compile(r"[\u0530-\u058f]")),
    ("el", re.compile(r"[\u0370-\u03ff]")),
    ("ka", re.compile(r"[\u10a0-\u10ff]")),
    ("cyrl", re.compile(r"[\u0400-\u04ff]")),
    ("deva", re.compile(r"[\u0900-\u097f]")),
    ("bn", re.compile(r"[\u0980-\u09ff]")),
    ("pa", re.compile(r"[\u0a00-\u0a7f]")),
    ("gu", re.compile(r"[\u0a80-\u0aff]")),
    ("or", re.compile(r"[\u0b00-\u0b7f]")),
    ("ta", re.compile(r"[\u0b80-\u0bff]")),
    ("te", re.compile(r"[\u0c00-\u0c7f]")),
    ("kn", re.compile(r"[\u0c80-\u0cff]")),
    ("ml", re.compile(r"[\u0d00-\u0d7f]")),
    ("si", re.compile(r"[\u0d80-\u0dff]")),
    ("th", re.compile(r"[\u0e00-\u0e7f]")),
    ("lo", re.compile(r"[\u0e80-\u0eff]")),
    ("bo", re.compile(r"[\u0f00-\u0fff]")),
    ("my", re.compile(r"[\u1000-\u109f]")),
    ("km", re.compile(r"[\u1780-\u17ff]")),
    ("am", re.compile(r"[\u1200-\u137f]")),
)

_LATIN_LETTER = re.compile(r"[A-Za-z\u00c0-\u024f]")
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)

# Function words that are distinctive to one language. Shared tokens are dropped
# below so "for"/"den"/"para" cannot vote for two languages at once.
_LATIN_STOPWORDS_RAW: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "and", "of", "with", "that", "this", "are", "was", "from",
        "their", "which", "have", "been", "people", "national",
    }),
    "fr": frozenset({
        "les", "des", "une", "pour", "dans", "avec", "sont", "qui", "aux",
        "cette", "nous", "vous", "être", "aussi", "société", "volontaires",
    }),
    "es": frozenset({
        "los", "las", "del", "está", "más", "pero", "también", "sobre",
        "desde", "sociedad", "voluntarios", "comunidades",
    }),
    "pt": frozenset({
        "não", "dos", "das", "são", "voluntários", "pela", "pelo", "também",
    }),
    "de": frozenset({
        "und", "der", "die", "das", "dem", "ein", "eine", "ist", "nicht",
        "von", "für", "auf", "sich", "auch", "werden", "sind", "oder",
        "gesellschaft",
    }),
    "it": frozenset({
        "della", "sono", "più", "questo", "questa", "degli", "nelle", "dalla",
        "società", "anche",
    }),
    "nl": frozenset({
        "het", "een", "van", "voor", "zijn", "niet", "wordt", "naar",
        "samenleving",
    }),
    "pl": frozenset({
        "się", "jest", "oraz", "przez", "które", "jako", "może", "tylko",
        "społeczeństwo",
    }),
    "sv": frozenset({
        "och", "att", "för", "är", "inte", "ett", "också", "från",
    }),
    "da": frozenset({
        "samfundet", "nogle", "mellem", "bliver", "meget", "af",
    }),
    "no": frozenset({
        "samfunnet", "mellom", "noe", "denne", "blir", "mye", "av",
    }),
    "fi": frozenset({
        "että", "sekä", "mutta", "myös", "ovat", "yhteiskunta", "kanssa",
    }),
    "hu": frozenset({
        "hogy", "nem", "azt", "vagy", "mint", "csak", "társadalom",
    }),
    "cs": frozenset({
        "jsou", "které", "společnost", "také", "nebo",
    }),
    "sk": frozenset({
        "sú", "alebo", "tiež", "ktoré", "spoločnosť", "pre",
    }),
    "ro": frozenset({
        "și", "este", "pentru", "sunt", "societatea", "voluntarii",
    }),
    "tr": frozenset({
        "için", "olan", "olarak", "değil", "toplum", "gönüllü", "daha",
    }),
    "id": frozenset({
        "adalah", "pada", "dari", "masyarakat", "relawan", "tidak",
    }),
    "ms": frozenset({
        "daripada", "ialah", "sukarelawan", "kepada",
    }),
    "vi": frozenset({
        "của", "các", "được", "trong", "không", "người",
    }),
    "sw": frozenset({
        "katika", "ambayo", "lakini", "jamii", "wajitoleaji", "kuhusu",
    }),
}


def _distinctive_stopwords(table: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    owners: dict[str, set[str]] = {}
    for lang, words in table.items():
        for word in words:
            owners.setdefault(word, set()).add(lang)
    return {
        lang: frozenset(word for word in words if len(owners[word]) == 1)
        for lang, words in table.items()
    }


_LATIN_STOPWORDS = _distinctive_stopwords(_LATIN_STOPWORDS_RAW)

_MIN_SCRIPT_CHARS = 8
_MIN_LATIN_TOKENS = 8
_MIN_STOP_HITS = 3


def detect_narrative_language(text: str) -> str:
    """Return an ISO 639-1 code for *text*, or ``en`` when the sample is too thin."""
    sample = (text or "")[:8000]
    if not sample.strip():
        return "en"

    counts = {key: len(pattern.findall(sample)) for key, pattern in _SCRIPT_PATTERNS}
    latin = len(_LATIN_LETTER.findall(sample))
    # Japanese and Korean mix Han characters with kana or hangul. A few kana
    # or hangul decide the language; Han alone stays Chinese. Latin prose that
    # merely quotes a word does not.
    if counts.get("ja", 0) >= 2 and counts["ja"] >= latin:
        return "ja"
    if counts.get("ko", 0) >= 2 and counts["ko"] >= latin:
        return "ko"
    non_latin = sum(counts.values())
    total = non_latin + latin
    if total <= 0:
        return "en"

    best_key, best_n = max(counts.items(), key=lambda item: item[1])
    if best_n >= _MIN_SCRIPT_CHARS and best_n >= latin and best_n * 2 >= total:
        if best_key == "cyrl":
            return _cyrillic_language(sample)
        if best_key == "arab":
            return _arabic_script_language(sample)
        if best_key == "deva":
            return _devanagari_language(sample)
        return best_key
    return _latin_language(sample)


def _cyrillic_language(text: str) -> str:
    if re.search(r"[әғқңөұүһ]", text):
        return "kk"
    if "ў" in text:
        return "be"
    if re.search(r"[їєґ]", text) or text.count("і") >= 3:
        return "uk"
    if re.search(r"[љњћђџ]", text):
        return "sr"
    if re.search(r"[ѓќ]", text):
        return "mk"
    if text.count("ъ") >= 2 and "ы" not in text and "і" not in text:
        return "bg"
    if re.search(r"[өү]", text):
        return "mn"
    return "ru"


def _arabic_script_language(text: str) -> str:
    if re.search(r"[ټډښځڅږګ]", text):
        return "ps"
    if re.search(r"[ےٹڈڑں]", text):
        return "ur"
    if re.search(r"[پچژگ]", text):
        return "fa"
    return "ar"


def _devanagari_language(text: str) -> str:
    if "आहे" in text or "आणि" in text:
        return "mr"
    if "छन्" in text or "होइन" in text:
        return "ne"
    return "hi"


def _latin_language(text: str) -> str:
    tokens = _TOKEN.findall(text.lower())
    if len(tokens) < _MIN_LATIN_TOKENS:
        return "en"
    counts = Counter(tokens)
    scores = {
        lang: sum(counts[word] for word in words)
        for lang, words in _LATIN_STOPWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_lang, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best >= _MIN_STOP_HITS and best >= second + 1:
        return best_lang
    return "en"
