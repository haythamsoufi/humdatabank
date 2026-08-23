"""Export-language helpers for UPR visuals (MT + Backoffice locale)."""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator

logger = logging.getLogger(__name__)

_TX_SESSION: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "upr_visuals_tx_session", default=None
)
_PROGRESS_LOCK = threading.Lock()
_PROGRESS: dict[str, dict[str, Any]] = {}
_PROGRESS_TTL_S = 600

RTL_LANGS = frozenset({"ar", "fa", "he", "ur"})
_DEFAULT_SYSTEM_LANGS = frozenset({"en", "fr", "es", "ar", "ru", "zh"})
_TAJAWAL_FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap"
)


def normalize_language_code(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    return raw.split("-", 1)[0]


def known_language_codes() -> set[str]:
    try:
        from config import Config

        names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", None) or {}
        return {normalize_language_code(code) for code in names if normalize_language_code(code)}
    except Exception:
        return {"en", "fr", "es", "ar", "ru", "zh", "hi"}


def parse_export_language(value: str | None, *, strict: bool = False) -> str:
    """Return a known ISO-639-1 code, or raise if *strict* and the value is unknown."""
    code = normalize_language_code(value) or "en"
    if code in known_language_codes():
        return code
    if strict:
        raise ValueError(f"Unsupported language: {value}")
    return "en"


def current_export_language() -> str:
    try:
        from flask_babel import get_locale

        loc = get_locale()
        if loc:
            return normalize_language_code(str(loc)) or "en"
    except Exception:
        pass
    import os

    env = normalize_language_code(os.environ.get("UPR_VISUALS_LANG"))
    return env or "en"


def is_rtl(lang: str | None = None) -> bool:
    return (normalize_language_code(lang) or current_export_language()) in RTL_LANGS


def system_language_codes() -> set[str]:
    """Admin-enabled Backoffice languages — already catalogued, no live MT needed."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            raw = current_app.config.get("SUPPORTED_LANGUAGES") or []
            codes = {normalize_language_code(item) for item in raw if normalize_language_code(item)}
            if codes:
                return codes
    except Exception:
        pass
    try:
        from config import Config

        raw = getattr(Config, "LANGUAGES", None) or []
        codes = {normalize_language_code(item) for item in raw if normalize_language_code(item)}
        if codes:
            return codes
    except Exception:
        pass
    return set(_DEFAULT_SYSTEM_LANGS)


def can_machine_translate(lang: str | None = None) -> bool:
    """False for English, catalogued system langs, or codes no engine can translate (e.g. rm)."""
    code = normalize_language_code(lang) or current_export_language()
    if not code or code == "en" or is_system_language(code):
        return False
    try:
        from app.services.translation.auto_translator import language_has_machine_translation

        return language_has_machine_translation(code)
    except Exception:
        return True


def is_system_language(lang: str | None = None) -> bool:
    code = normalize_language_code(lang) or current_export_language()
    return code in system_language_codes()


@contextmanager
def export_locale(lang: str | None) -> Iterator[str]:
    from flask_babel import force_locale

    code = parse_export_language(lang)
    with force_locale(code):
        yield code


def _machine_translate(text: str, lang: str) -> str | None:
    from app.services.translation.auto_translator import translate_text

    return translate_text(text, target_language=lang, source_language="en")


def _machine_translate_batch(texts: list[str], lang: str) -> list:
    from app.services.translation.auto_translator import translate_batch

    return translate_batch(texts, target_language=lang, source_language="en") or []


def parse_progress_id(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw or len(raw) > 64:
        return ""
    if all(char.isalnum() or char in "-_" for char in raw):
        return raw
    return ""


def _prune_visuals_progress(now: float) -> None:
    stale = [
        key
        for key, rec in _PROGRESS.items()
        if now - float(rec.get("updated") or 0) > _PROGRESS_TTL_S
    ]
    for key in stale:
        _PROGRESS.pop(key, None)


def start_visuals_progress(progress_id: str) -> None:
    pid = parse_progress_id(progress_id)
    if not pid:
        return
    now = time.time()
    with _PROGRESS_LOCK:
        _prune_visuals_progress(now)
        _PROGRESS[pid] = {
            "done": 0,
            "total": 0,
            "pending": 0,
            "lang": "",
            "elapsed": 0,
            "status": "running",
            "updated": now,
        }


def update_visuals_progress(progress_id: str, **kw: Any) -> None:
    pid = parse_progress_id(progress_id)
    if not pid:
        return
    now = time.time()
    with _PROGRESS_LOCK:
        rec = _PROGRESS.get(pid)
        if rec is None:
            rec = {"status": "running", "updated": now}
            _PROGRESS[pid] = rec
        if "done" in kw:
            rec["done"] = int(kw["done"] or 0)
        if "total" in kw:
            rec["total"] = int(kw["total"] or 0)
        if "lang" in kw:
            rec["lang"] = str(kw.get("lang") or "")
        if "elapsed" in kw:
            rec["elapsed"] = int(kw["elapsed"] or 0)
        if "status" in kw:
            rec["status"] = str(kw.get("status") or rec.get("status") or "running")
        rec["pending"] = max(0, int(rec.get("total") or 0) - int(rec.get("done") or 0))
        rec["updated"] = now


def get_visuals_progress(progress_id: str) -> dict[str, Any] | None:
    pid = parse_progress_id(progress_id)
    if not pid:
        return None
    now = time.time()
    with _PROGRESS_LOCK:
        _prune_visuals_progress(now)
        rec = _PROGRESS.get(pid)
        return dict(rec) if rec else None


def localize_export(fn: Callable[[], Any], *, on_progress: Any = None, progress_id: str = "") -> Any:
    """Collect live-MT strings, batch-translate them, then run *fn* with the map.

    System languages and English skip the collect pass. *on_progress* matches
    ``t_batch`` (``done``, ``total``, ``lang``, ``elapsed``).
    """
    pid = parse_progress_id(progress_id)
    if pid:
        start_visuals_progress(pid)

    def emit(**kw: Any) -> None:
        if pid:
            update_visuals_progress(pid, **kw)
        if on_progress:
            on_progress(**kw)

    lang = current_export_language()
    if lang == "en" or is_system_language(lang) or not can_machine_translate(lang):
        result = fn()
        if pid:
            update_visuals_progress(pid, done=0, total=0, lang=lang, status="done")
        return result

    session: dict[str, Any] = {"phase": "collect", "texts": [], "map": {}}
    token = _TX_SESSION.set(session)
    try:
        first = fn()
        unique = list(dict.fromkeys(item for item in session["texts"] if str(item).strip()))
        emit(done=0, total=len(unique), lang=lang, elapsed=0, status="running")
        if not unique:
            if pid:
                update_visuals_progress(pid, done=0, total=0, lang=lang, status="done")
            return first
        translated = t_batch(unique, on_progress=emit)
        session["map"] = {
            src: dst for src, dst in zip(unique, translated) if dst and str(dst).strip()
        }
        session["phase"] = "apply"
        result = fn()
        if pid:
            update_visuals_progress(
                pid, done=len(unique), total=len(unique), lang=lang, status="done"
            )
        return result
    except Exception:
        if pid:
            update_visuals_progress(pid, status="failed")
        raise
    finally:
        _TX_SESSION.reset(token)


def t(text: str | None) -> str:
    """Localize a static English display string for the active export locale.

    Prefer the plugin visual catalog (system languages, no network). Fall back
    to Flask-Babel for other UI msgids, then the translation API for languages
    outside the system set. English narrative still goes through ``t_batch``.
    """
    raw = "" if text is None else str(text)
    if not raw.strip():
        return raw
    lang = current_export_language()
    if lang == "en":
        return raw
    session = _TX_SESSION.get()
    if session and session.get("phase") == "apply":
        applied = session.get("map") or {}
        hit = applied.get(raw)
        if hit:
            return str(hit)
    from plugins.upr_visuals.strings import lookup_visual_string

    mapped = lookup_visual_string(raw, lang)
    if mapped:
        return mapped
    if is_system_language(lang):
        try:
            from flask_babel import gettext

            return gettext(raw)
        except Exception:
            logger.debug("UPR visuals gettext failed for %r → %s", raw[:80], lang, exc_info=True)
            return raw
    if not can_machine_translate(lang):
        return raw
    if session and session.get("phase") == "collect":
        session["texts"].append(raw)
        return raw
    if session and session.get("phase") == "apply":
        return raw
    try:
        result = _machine_translate(raw, lang)
        if result and str(result).strip():
            return str(result)
    except Exception:
        logger.debug("UPR visuals t() failed for %r → %s", raw[:80], lang, exc_info=True)
    return raw


_T_BATCH_CHUNK = 24


def _cached_translations(texts: list[str], lang: str) -> dict[str, str]:
    """Batched cache lookup: one query for the whole chunk instead of one per text."""
    try:
        from app.services.translation.result_cache import get_cached_many

        return get_cached_many(texts, "en", lang, "default")
    except Exception:
        return {}


def t_batch(texts: Iterable[str | None], *, on_progress: Any = None) -> list[str]:
    """Machine-translate a batch (narrative chunks, or labels for non-system languages)."""
    originals = [("" if item is None else str(item)) for item in texts]
    if not originals:
        return []
    lang = current_export_language()
    if lang == "en":
        return originals
    try:
        from app.services.translation.auto_translator import language_has_machine_translation

        if not language_has_machine_translation(lang):
            return originals
    except Exception:
        pass
    indexes = [i for i, text in enumerate(originals) if text.strip()]
    if not indexes:
        return originals
    payload = [originals[i] for i in indexes]
    total = len(payload)
    resolved: list[Any] = [None] * total
    pending: list[int] = []
    cache_hits = _cached_translations(payload, lang)
    for offset, text in enumerate(payload):
        hit = cache_hits.get(text)
        if hit:
            resolved[offset] = hit
        else:
            pending.append(offset)
    cached_n = total - len(pending)
    started = time.monotonic()
    logger.info("UPR visuals t_batch %s chunks → %s (%s cached)", total, lang, cached_n)
    if on_progress:
        on_progress(done=cached_n, total=total, lang=lang, elapsed=0)
    for start in range(0, len(pending), _T_BATCH_CHUNK):
        batch_idx = pending[start : start + _T_BATCH_CHUNK]
        chunk = [payload[i] for i in batch_idx]
        try:
            part = _machine_translate_batch(chunk, lang) or []
        except Exception:
            logger.debug("UPR visuals t_batch() failed → %s", lang, exc_info=True)
            part = []
        if len(part) < len(chunk):
            part = list(part) + [None] * (len(chunk) - len(part))
        for pos, index in enumerate(batch_idx):
            resolved[index] = part[pos]
        done = cached_n + min(start + len(batch_idx), len(pending))
        elapsed = int(time.monotonic() - started)
        logger.info("UPR visuals t_batch %s/%s → %s (%ss)", done, total, lang, elapsed)
        if on_progress:
            on_progress(done=done, total=total, lang=lang, elapsed=elapsed)
    out = list(originals)
    for offset, index in enumerate(indexes):
        value = resolved[offset] if offset < len(resolved) else None
        if value and str(value).strip():
            out[index] = str(value)
    return out


def localized_indicator_label(indicator_bank, fallback: str = "") -> str:
    """Prefer a stored IndicatorBank translation; otherwise the bank name / *fallback*."""
    if indicator_bank is None:
        return fallback
    lang = current_export_language()
    translations = getattr(indicator_bank, "name_translations", None)
    if isinstance(translations, dict):
        val = translations.get(lang)
        if isinstance(val, str) and val.strip():
            return val.strip()
    try:
        from app.utils.form_localization import get_localized_indicator_name

        label = (get_localized_indicator_name(indicator_bank) or "").strip()
        if label:
            return label
    except Exception:
        logger.debug("localized_indicator_label failed", exc_info=True)
    name = (getattr(indicator_bank, "name", None) or "").strip()
    return name or fallback


def localized_form_item_label(item, fallback: str = "") -> str:
    """Locale-specific form-item label, then indicator-bank translation, then *fallback*.

    The English ``FormItem.label`` is often a short working name; visuals use the
    official IndicatorBank name unless a stored translation or custom_label exists.
    """
    if item is None:
        return fallback
    lang = current_export_language()
    translations = getattr(item, "label_translations", None)
    if isinstance(translations, dict):
        val = translations.get(lang)
        if isinstance(val, str) and val.strip():
            return val.strip()
    custom = (getattr(item, "custom_label", None) or "").strip()
    if custom:
        return custom
    bank = getattr(item, "indicator_bank", None)
    if bank is not None:
        label = localized_indicator_label(bank, fallback=fallback)
        if label:
            return label
    return (getattr(item, "label", None) or fallback or "").strip() or fallback


_BABEL_LOCALE_ALIASES = {"zh": "zh_Hans"}


def _babel_territory_name(iso2: str | None, lang: str) -> str | None:
    code = (iso2 or "").strip().upper()
    if not code or not lang or lang == "en":
        return None
    try:
        from babel import Locale
    except Exception:
        return None
    for locale_id in (lang, _BABEL_LOCALE_ALIASES.get(lang, "")):
        if not locale_id:
            continue
        try:
            territories = Locale.parse(locale_id).territories or {}
            name = territories.get(code)
            if isinstance(name, str) and name.strip():
                return name.strip()
        except Exception:
            continue
    return None


def localized_country_name(country=None, *, iso2: str | None = None, fallback: str = "") -> str:
    """Country label: stored translation, then Babel territory name, then *fallback*.

    System languages never call the translation API. Header/export chrome uses this
    so a missing ``Country.name_translations`` row still localizes (e.g. Uganda → Ouganda).
    """
    lang = current_export_language()
    english = ""
    if country is not None:
        english = (getattr(country, "name", None) or "").strip()
        iso2 = iso2 or getattr(country, "iso2", None)
        translations = getattr(country, "name_translations", None)
        if isinstance(translations, dict):
            val = translations.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()
    english = english or (fallback or "").strip()
    if lang == "en":
        return english
    babel_name = _babel_territory_name(iso2, lang)
    if babel_name:
        return babel_name
    if is_system_language(lang):
        return english
    return t(english) if english else english


def localized_country_header(meta: dict[str, Any] | None = None) -> str:
    """Cover-style country name (uppercase) for the current export language."""
    meta = meta or {}
    name = localized_country_name(
        iso2=meta.get("iso2") or meta.get("appeal_iso2"),
        fallback=(meta.get("country_name") or "").strip(),
    )
    return name.upper() if name else ""


def localized_ns_display_name(ns, fallback: str = "") -> str:
    """National Society label: stored translations for system languages, MT otherwise."""
    from plugins.upr_visuals.catalog import display_ns_name

    english = display_ns_name(getattr(ns, "name", None) or fallback)
    if ns is None:
        return english
    lang = current_export_language()
    translations = getattr(ns, "name_translations", None)
    if isinstance(translations, dict):
        val = translations.get(lang)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if lang == "en" or is_system_language(lang):
        return english
    return t(english) if english else english


def _localize_assignment_label(text: str) -> str:
    """Translate the assignment/template part; keep `` – period`` as-is."""
    raw = (text or "").strip()
    if not raw:
        return ""
    for sep in (" \u2013 ", " – ", " - "):
        if sep in raw:
            head, tail = raw.split(sep, 1)
            return f"{t(head.strip())}{sep}{tail.strip()}"
    return t(raw)


def localized_assignment_title(assigned) -> str:
    """Assignment name for the current export language (tab title and downloads)."""
    if assigned is None:
        return ""
    lang = current_export_language()
    custom = (getattr(assigned, "custom_name", None) or "").strip()
    if custom:
        translations = getattr(assigned, "custom_name_translations", None)
        if isinstance(translations, dict):
            val = translations.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return custom if lang == "en" else _localize_assignment_label(custom)
    template = getattr(assigned, "template", None)
    english = (getattr(template, "name", None) or "").strip()
    name = english
    if template is not None and lang != "en":
        try:
            from app.utils.form_localization import get_localized_template_name

            name = (get_localized_template_name(template, locale=lang) or "").strip() or english
        except Exception:
            name = english
        if not name or name == english:
            name = t(english) if english else name
    elif lang != "en" and english:
        name = t(english)
    period = (getattr(assigned, "period_name", None) or "").strip()
    if name and period:
        return f"{name} \u2013 {period}"
    if name or period:
        return name or period
    fallback = (getattr(assigned, "display_name", None) or "").strip()
    return fallback if lang == "en" else _localize_assignment_label(fallback)


def localized_entity_name(entity, *, name_attr: str = "name", fallback: str = "") -> str:
    if entity is None:
        return fallback
    try:
        from app.utils.form_localization import get_localized_name_from_translations

        label = (
            get_localized_name_from_translations(entity, name_attr=name_attr) or ""
        ).strip()
        if label:
            return label
    except Exception:
        logger.debug("localized_entity_name failed", exc_info=True)
    return (getattr(entity, name_attr, None) or fallback or "").strip() or fallback


def _collect_block_texts(block: dict[str, Any], bag: list[tuple[dict, str]]) -> None:
    """Collect run text only. ``block["text"]`` is a derived join of the runs
    (see ``_rebuild_block_text``) and is never itself sent to MT: renderers
    (``narrative_pdf.py``, ``xml_idml.py``) read ``runs``, and the paragraph's
    own ``text`` is used only for a length-based flow-height estimate.
    """
    if block.get("style") == "Blank":
        return
    if block.get("kind") == "table":
        for row in block.get("rows") or []:
            for cell in row or []:
                for para in cell or []:
                    _collect_block_texts(para, bag)
        return
    for run in block.get("runs") or []:
        run_text = run.get("text")
        if isinstance(run_text, str) and run_text.strip():
            bag.append((run, "text"))


def _rebuild_block_text(block: dict[str, Any]) -> None:
    """Resync ``block["text"]`` from its (now-translated) runs, mirroring the
    join in ``word_reader._parse_word_para``, so the height estimate reflects
    translated content without a dedicated MT call for the paragraph text.
    """
    if block.get("style") == "Blank":
        return
    if block.get("kind") == "table":
        for row in block.get("rows") or []:
            for cell in row or []:
                for para in cell or []:
                    _rebuild_block_text(para)
        return
    runs = block.get("runs") or []
    if runs:
        block["text"] = "".join(str(run.get("text") or "") for run in runs).strip()


def translate_styled_blocks(
    blocks: list[dict[str, Any]],
    *,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """Translate styled narrative blocks in place (runs only). Skip Blank / hrefs.

    De-duplicates repeated strings (headings, labels, org names) before
    calling the MT engine, the same as ``localize_export`` does for
    visuals/chrome, then rebuilds each paragraph's ``text`` from its runs.
    """
    if current_export_language() == "en" or not blocks:
        return blocks
    bag: list[tuple[dict, str]] = []
    for block in blocks:
        _collect_block_texts(block, bag)
    if not bag:
        return blocks
    originals = [str(owner.get(key) or "") for owner, key in bag]
    unique = list(dict.fromkeys(item for item in originals if item.strip()))
    translated_unique = t_batch(unique, on_progress=on_progress)
    value_map = {
        src: dst for src, dst in zip(unique, translated_unique) if dst and str(dst).strip()
    }
    for (owner, key), original in zip(bag, originals):
        hit = value_map.get(original)
        if hit:
            owner[key] = hit
    for block in blocks:
        _rebuild_block_text(block)
    return blocks


def rtl_document_attrs(lang: str | None = None) -> dict[str, str]:
    code = normalize_language_code(lang) or current_export_language()
    return {"lang": code or "en", "dir": "rtl" if is_rtl(code) else "ltr"}


def rtl_font_link_html(lang: str | None = None) -> str:
    if not is_rtl(lang):
        return ""
    return (
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="{_TAJAWAL_FONTS_HREF}" rel="stylesheet">'
    )


def rtl_css(lang: str | None = None) -> str:
    if not is_rtl(lang):
        return ""
    body_font = '"Tajawal", "Arial", "Segoe UI", sans-serif'
    return f"""
html[dir="rtl"] body,
html[dir="rtl"] .upr-dashboard,
html[dir="rtl"] .upr-visual-report,
.upr-dashboard[dir="rtl"],
.upr-visual-report[dir="rtl"],
html[dir="rtl"] .upr-nar-p {{
  font-family: {body_font};
}}
html[dir="rtl"] .upr-doc-header__country,
html[dir="rtl"] .upr-doc-header__subtitle,
html[dir="rtl"] .upr-block__title,
html[dir="rtl"] .upr-kpi__label,
html[dir="rtl"] .upr-bar-label,
html[dir="rtl"] .upr-bar-group__title,
html[dir="rtl"] .upr-bar-yes,
html[dir="rtl"] .upr-empty,
html[dir="rtl"] .upr-doc-footer,
html[dir="rtl"] .upr-not-reported,
html[dir="rtl"] th,
html[dir="rtl"] td,
.upr-dashboard[dir="rtl"] .upr-doc-header__country,
.upr-dashboard[dir="rtl"] .upr-block__title,
.upr-dashboard[dir="rtl"] th,
.upr-dashboard[dir="rtl"] td {{
  font-family: {body_font};
}}
html[dir="rtl"] .upr-kpi__value,
html[dir="rtl"] .upr-bar-value,
html[dir="rtl"] .upr-bar-yes.upr-num,
html[dir="rtl"] .upr-reach-value,
html[dir="rtl"] .upr-reach-headline,
html[dir="rtl"] .upr-num,
html[dir="rtl"] .upr-support-total,
html[dir="rtl"] .upr-doc-footer__appeal strong {{
  font-family: "Montserrat", "Tajawal", sans-serif;
}}
html[dir="rtl"] .upr-nar-p--Body {{
  text-align: justify;
}}
"""
