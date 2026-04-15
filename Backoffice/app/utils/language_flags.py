"""
Language -> flag helpers.

Notes:
- Flags are inherently country/region, not language. For UI convenience we map a
  language code to a representative country flag (best-effort).
- For a small set of languages the UI already has CSS-based flags via
  Config.LANGUAGE_FLAG_ICONS (e.g. en->gb). For all other languages we fall back
  to emoji flags when we can derive a country code.
"""

from __future__ import annotations

from typing import Optional
from contextlib import suppress
from urllib.request import urlopen, Request
import os
import tempfile
import re

_TWEMOJI_SVG_BASE = "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/svg"

# Best-effort overrides where language code doesn't match a useful country code.
# Values are ISO 3166-1 alpha-2 country codes (lowercase).
LANGUAGE_TO_COUNTRY_FLAG = {
    # Existing defaults / common
    "en": "gb",
    "ar": "sa",
    "zh": "cn",
    "hi": "in",
    "ru": "ru",
    "fr": "fr",
    "es": "es",
    # Common mismatches / regional scripts
    "fa": "ir",
    "he": "il",
    "ur": "pk",
    "uk": "ua",  # Ukrainian (avoid "uk" = United Kingdom)
    "sv": "se",
    "cs": "cz",
    "el": "gr",
    "ko": "kr",
    "ja": "jp",
    "vi": "vn",
    "bn": "bd",
    "ne": "np",
    "si": "lk",
    "km": "kh",
    "lo": "la",
    "my": "mm",
    "ms": "my",
    "sw": "ke",
    "am": "et",
    "zu": "za",
    "af": "za",
    "ha": "ng",
    "yo": "ng",
    "ig": "ng",
    "pa": "in",
    "ta": "in",
    "te": "in",
    "mr": "in",
    "gu": "in",
    "ml": "in",
    "kn": "in",
    "or": "in",
    "as": "in",
    # Albanian
    "sq": "al",
}


def normalize_language_code(code: str) -> str:
    """Normalize to base ISO language code (e.g., fr_FR -> fr, en-US -> en)."""
    s = (code or "").strip().lower().replace("-", "_")
    if not s:
        return ""
    return s.split("_", 1)[0]


def _extract_region(code: str) -> str:
    """Extract region from a locale (e.g., fr_FR -> FR). Returns '' if none."""
    s = (code or "").strip().replace("-", "_")
    if not s or "_" not in s:
        return ""
    parts = s.split("_")
    if len(parts) < 2:
        return ""
    region = (parts[1] or "").strip()
    # Only support ISO 3166-1 alpha-2 regions for flags.
    if len(region) == 2 and region.isalpha():
        return region.upper()
    return ""


def _likely_region_from_babel(language_code: str) -> str:
    """Infer likely region using CLDR likelySubtags (via Babel), best-effort.

    Example: "sq" -> "AL" based on likelySubtags "sq_Latn_AL".
    """
    lang = normalize_language_code(language_code)
    if not lang:
        return ""
    with suppress(Exception):
        from babel.core import get_global  # type: ignore

        likely = get_global("likely_subtags") or {}
        val = likely.get(lang)
        if not val:
            return ""
        return _extract_region(val)
    return ""


def language_to_country_flag_code(language_code: str) -> Optional[str]:
    """Return a 2-letter country code for a language, best-effort."""
    raw = (language_code or "").strip()
    lang = normalize_language_code(raw)
    if not raw or not lang:
        return None

    # 1) If locale includes explicit region, prefer that (pt_BR -> BR)
    region = _extract_region(raw)
    if region:
        return region.lower()

    if lang in LANGUAGE_TO_COUNTRY_FLAG:
        return LANGUAGE_TO_COUNTRY_FLAG[lang]

    # 2) Use CLDR likelySubtags to pick a reasonable default country
    likely_region = _likely_region_from_babel(lang)
    if likely_region:
        return likely_region.lower()

    # Heuristic: many language codes match a country code (de, it, tr, etc.)
    if len(lang) == 2 and lang.isalpha():
        return lang
    # Some languages are 3-letter ISO 639-2/3; don't guess these into flags.
    if re.match(r"^[a-z]{3}$", lang):
        return None
    return None


def country_code_to_flag_emoji(country_code: str) -> Optional[str]:
    """Convert an ISO 3166-1 alpha-2 code to a flag emoji."""
    cc = (country_code or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha():
        return None
    base = 0x1F1E6  # Regional indicator symbol letter A
    return chr(base + (ord(cc[0]) - ord("A"))) + chr(base + (ord(cc[1]) - ord("A")))

def country_code_to_twemoji_svg_url(country_code: str) -> Optional[str]:
    """Return a Twemoji SVG URL for a given ISO 3166-1 alpha-2 code."""
    cc = (country_code or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha():
        return None
    base = 0x1F1E6  # Regional indicator symbol letter A
    cp1 = base + (ord(cc[0]) - ord("A"))
    cp2 = base + (ord(cc[1]) - ord("A"))
    seq = f"{cp1:x}-{cp2:x}"
    return f"{_TWEMOJI_SVG_BASE}/{seq}.svg"


def language_flag_emoji(language_code: str) -> str:
    """Return an emoji flag symbol for a language code.

    - If we can infer a country code, returns the corresponding country flag.
    - Otherwise returns a neutral flag symbol (white flag) so *every* language
      always has "a flag" in the UI.
    """
    cc = language_to_country_flag_code(language_code)
    if not cc:
        return "🏳️"
    return country_code_to_flag_emoji(cc) or "🏳️"


def language_flag_twemoji_svg_url(language_code: str) -> Optional[str]:
    """Return a Twemoji SVG URL for a language code, best-effort."""
    cc = language_to_country_flag_code(language_code)
    if not cc:
        return None
    return country_code_to_twemoji_svg_url(cc)


def prefetch_language_flags_to_local_cache(
    language_codes: list[str],
    *,
    instance_path: str,
    timeout_seconds: int = 8,
) -> dict:
    """Download any missing Twemoji flag SVGs to a local on-disk cache.

    IMPORTANT: This should only be called when system settings change (e.g. admin
    updates supported languages). Flag requests themselves must never fetch from
    the network.
    """
    cache_dir = os.path.join(instance_path, "flag_cache")
    with suppress(Exception):
        os.makedirs(cache_dir, exist_ok=True)

    # Dedupe by country code to avoid redundant downloads
    wanted_ccs: set[str] = set()
    for code in (language_codes or []):
        cc = language_to_country_flag_code(code)
        if cc:
            wanted_ccs.add(cc.lower())

    results = {
        "cache_dir": cache_dir,
        "requested_languages": list(language_codes or []),
        "country_codes": sorted(wanted_ccs),
        "downloaded": [],
        "skipped_existing": [],
        "failed": [],
    }

    for cc in sorted(wanted_ccs):
        target_path = os.path.join(cache_dir, f"{cc}.svg")
        if os.path.exists(target_path):
            results["skipped_existing"].append(cc)
            continue

        url = country_code_to_twemoji_svg_url(cc)
        if not url:
            results["failed"].append({"cc": cc, "error": "no_url"})
            continue

        try:
            req = Request(url, headers={"User-Agent": "hum-databank/flags-cache"})
            with urlopen(req, timeout=timeout_seconds) as r:
                data = r.read()
            # Basic sanity check to avoid writing HTML error pages as .svg
            if not data or b"<svg" not in data[:1024]:
                raise ValueError("unexpected_response")

            # Atomic write
            with tempfile.NamedTemporaryFile(delete=False, dir=cache_dir, suffix=".tmp") as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            os.replace(tmp_path, target_path)
            results["downloaded"].append(cc)
        except Exception as e:
            with suppress(Exception):
                if "tmp_path" in locals() and tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            results["failed"].append({"cc": cc, "error": "Download failed."})

    return results
