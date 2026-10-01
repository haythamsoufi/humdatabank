"""Shared display names for locale codes.

Admin screens used to keep their own copies of this lookup. One helper keeps
the label stable when ``Config.LANGUAGE_DISPLAY_NAMES`` changes.
"""

from __future__ import annotations


def language_display_name(language_code, *, fallback=None):
    """Return a human-readable label for a locale code.

    ``fallback`` is used when the code is missing from both display maps.
    The default fallback is ``"N/A"`` for an empty code and the raw code otherwise.
    """
    from config import Config

    raw = "" if language_code is None else str(language_code).strip()
    if not raw:
        return "N/A" if fallback is None else fallback

    base = raw.split("_")[0].split("-")[0]
    if base.lower() == "zz":
        return "Unknown"

    display = getattr(Config, "LANGUAGE_DISPLAY_NAMES", None) or {}
    all_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", None) or {}
    label = (
        display.get(raw)
        or display.get(base)
        or display.get(base.lower())
        or all_names.get(raw)
        or all_names.get(base)
        or all_names.get(base.lower())
    )
    if label:
        return label
    if fallback is not None:
        return fallback
    return raw
