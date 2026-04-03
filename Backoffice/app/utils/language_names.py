"""
Helpers for presenting language names in the UI.

Two main helpers:

* ``language_endonym``  – native name (e.g. "العربية", "Français").
  Used in the language-switcher dropdown so each language is labelled
  in its own script.

* ``language_display_name`` – name in the *viewer's* current locale
  (e.g. when viewing in English: "French", "Arabic").
  Used everywhere else (translation fields, settings, modals, …).
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)
from typing import Optional


def _capitalize_first_cased_char(text: str) -> str:
    """Uppercase first cased character when the script supports case."""
    if not text:
        return text
    for i, ch in enumerate(text):
        # Scripts without case (e.g., Arabic/Chinese) return same upper/lower.
        if ch.isalpha() and ch.upper() != ch.lower():
            return f"{text[:i]}{ch.upper()}{text[i + 1:]}"
    return text


def _normalize_lang_code(code: Optional[str]) -> str:
    """Normalize a locale/language code to a base ISO language code."""
    if not code:
        return ""
    s = str(code).strip().lower().replace("-", "_")
    if not s:
        return ""
    # If locale-like (e.g., en_US) keep only base language.
    return s.split("_")[0] or s


@lru_cache(maxsize=1024)
def language_endonym(code: Optional[str]) -> Optional[str]:
    """Return the language name in its own language (endonym).

    Examples:
    - 'ar' -> 'العربية'
    - 'fr' -> 'Français'
    - 'ru' -> 'Русский'

    Returns None if the code is invalid or cannot be resolved.
    """
    base = _normalize_lang_code(code)
    if not base:
        return None
    try:
        from babel import Locale  # Babel is already a dependency via Flask-Babel
        loc = Locale.parse(base)
        name = loc.get_display_name(base)
        if isinstance(name, str) and name.strip():
            return _capitalize_first_cased_char(name.strip())
    except Exception as e:
        logger.debug("language_endonym failed for %s: %s", code, e)
        return None
    return None


@lru_cache(maxsize=4096)
def language_display_name(code: Optional[str], viewer_locale: Optional[str] = None) -> Optional[str]:
    """Return the language name as seen by the current viewer.

    When *viewer_locale* is ``'en'`` (default / most common), this gives
    English names: ``'fr'`` → ``'French'``, ``'ar'`` → ``'Arabic'``.

    Falls back to :func:`language_endonym` if Babel cannot resolve the
    combination.
    """
    base = _normalize_lang_code(code)
    if not base:
        return None
    viewer = _normalize_lang_code(viewer_locale) or _current_ui_locale()
    try:
        from babel import Locale
        loc = Locale.parse(base)
        name = loc.get_display_name(viewer)
        if isinstance(name, str) and name.strip():
            return _capitalize_first_cased_char(name.strip())
    except Exception as e:
        logger.debug("language_display_name failed for %s: %s", code, e)
    return language_endonym(code)


def _current_ui_locale() -> str:
    """Best-effort detection of the viewer's current UI language."""
    try:
        from flask import has_request_context, session
        if has_request_context():
            lang = session.get("language")
            if lang:
                return _normalize_lang_code(lang)
    except Exception as e:
        logger.debug("_current_ui_locale failed: %s", e)
    return "en"

