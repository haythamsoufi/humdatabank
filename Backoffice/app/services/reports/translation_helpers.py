"""Resolve multilingual report definition strings."""

from __future__ import annotations

from typing import Any


def normalize_language(language: str | None) -> str:
    if not language:
        return "en"
    return language.strip().lower().split("_", 1)[0].split("-", 1)[0] or "en"


def resolve_translation(
    translations: dict[str, Any] | None,
    *,
    language: str,
    default_language: str = "en",
    fallback: str | None = None,
) -> str | None:
    """Pick the best string for *language* from a translations dict."""
    if not translations or not isinstance(translations, dict):
        return fallback
    lang = normalize_language(language)
    default_lang = normalize_language(default_language)
    for key in (lang, default_lang, "en"):
        val = translations.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for val in translations.values():
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def wrap_legacy_text(text: str | None, *, language: str = "en") -> dict[str, str]:
    if text and str(text).strip():
        return {normalize_language(language): str(text).strip()}
    return {}


def apply_language_to_widget(widget: dict[str, Any], *, language: str, default_language: str) -> dict[str, Any]:
    """Return a shallow copy of *widget* with resolved title/content/footnote."""
    out = dict(widget)
    title = resolve_translation(
        widget.get("title_translations"),
        language=language,
        default_language=default_language,
        fallback=widget.get("title"),
    )
    if title:
        out["title"] = title
    content = resolve_translation(
        widget.get("content_translations"),
        language=language,
        default_language=default_language,
        fallback=widget.get("content"),
    )
    if content is not None:
        out["content"] = content
    footnote = resolve_translation(
        widget.get("footnote_translations"),
        language=language,
        default_language=default_language,
        fallback=widget.get("footnote"),
    )
    if footnote:
        out["footnote"] = footnote
    return out


def apply_language_to_section(section: dict[str, Any], *, language: str, default_language: str) -> dict[str, Any]:
    out = dict(section)
    title = resolve_translation(
        section.get("title_translations"),
        language=language,
        default_language=default_language,
        fallback=section.get("title"),
    )
    if title:
        out["title"] = title
    footnote = resolve_translation(
        section.get("footnote_translations"),
        language=language,
        default_language=default_language,
        fallback=section.get("footnote"),
    )
    if footnote:
        out["footnote"] = footnote
    widgets = []
    for widget in section.get("widgets") or []:
        widgets.append(apply_language_to_widget(widget, language=language, default_language=default_language))
    out["widgets"] = widgets
    return out


def translation_completeness(
    translations: dict[str, Any] | None,
    languages: list[str],
) -> dict[str, bool]:
    """Return {lang: True/False} indicating whether *translations* has text for each language."""
    langs = [normalize_language(lang) for lang in languages]
    result: dict[str, bool] = {}
    data = translations if isinstance(translations, dict) else {}
    for lang in langs:
        val = data.get(lang)
        result[lang] = isinstance(val, str) and bool(val.strip())
    return result
