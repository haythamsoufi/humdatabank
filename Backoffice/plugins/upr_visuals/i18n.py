"""Export-language helpers for UPR visuals (MT + Backoffice locale).

Language gates (do not collapse these — they answer different questions):

1. ``is_rtl()`` / ``RTL_LANGS`` — document ``dir``, table column flip, print
   layout. Hebrew is included.
2. ``uses_arabic_font()`` / ``ARABIC_FONT_LANGS`` — Tajawal. Arabic-script
   locales only; Hebrew stays on the Latin stack.
3. ``current_export_language() == "ar"`` — Arabic grammar and CHF copy
   (مليون / ملايين, فرنك سويسري) in ``formatters``.
4. Arabic *script* (``\\u0600–\\u06ff``) — ``split_display_amount``, used when
   a string already contains Arabic letters regardless of the export language.

JS ``data-rtl-langs`` / ``data-arabic-font-langs`` on the language select must
match ``RTL_LANGS`` / ``ARABIC_FONT_LANGS`` here.
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

logger = logging.getLogger(__name__)

_TX_SESSION: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "upr_visuals_tx_session", default=None
)
_LOAD_MEMO: contextvars.ContextVar[dict[tuple, Any] | None] = contextvars.ContextVar(
    "upr_visuals_load_memo", default=None
)
_PROGRESS_LOCK = threading.Lock()
_PROGRESS: dict[str, dict[str, Any]] = {}
_PROGRESS_TTL_S = 600

RTL_LANGS = frozenset({"ar", "fa", "he", "ur"})
ARABIC_FONT_LANGS = frozenset({"ar", "fa", "ur"})
_DEFAULT_SYSTEM_LANGS = frozenset({"en", "fr", "es", "ar", "ru", "zh"})


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
    """True when the export language uses a right-to-left *layout* (gate 1)."""
    return (normalize_language_code(lang) or current_export_language()) in RTL_LANGS


def uses_arabic_font(lang: str | None = None) -> bool:
    """True when body text should use Tajawal (gate 2). Hebrew is RTL but not this."""
    return (normalize_language_code(lang) or current_export_language()) in ARABIC_FONT_LANGS


def arabic_font_class(lang: str | None = None) -> str:
    return "upr-arabic-font" if uses_arabic_font(lang) else ""


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
        logger.warning("UPR visuals: translation engine unavailable; skipping live MT", exc_info=True)
        return False


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


def _progress_key(progress_id: str, aes_id: int | None = None) -> str:
    pid = parse_progress_id(progress_id)
    if not pid:
        return ""
    if aes_id:
        return f"{int(aes_id)}_{pid}"
    return pid


def _progress_dir() -> Path | None:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            path = Path(current_app.instance_path) / "upr_visuals_progress"
            path.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        logger.debug("UPR visuals: progress directory unavailable", exc_info=True)
    return None


def _progress_path(key: str) -> Path | None:
    folder = _progress_dir()
    if folder is None:
        return None
    return folder / f"{key}.json"


def _read_progress_file(key: str) -> dict[str, Any] | None:
    path = _progress_path(key)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_progress_file(key: str, rec: dict[str, Any]) -> None:
    path = _progress_path(key)
    if path is None:
        return
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("UPR visuals: could not persist progress %s", key, exc_info=True)
        try:
            tmp.unlink()
        except OSError:
            pass


def _prune_visuals_progress(now: float) -> None:
    stale = [
        key
        for key, rec in _PROGRESS.items()
        if now - float(rec.get("updated") or 0) > _PROGRESS_TTL_S
    ]
    for key in stale:
        _PROGRESS.pop(key, None)
        path = _progress_path(key)
        if path is None:
            continue
        try:
            path.unlink()
        except OSError:
            pass


def start_visuals_progress(progress_id: str, *, aes_id: int | None = None) -> None:
    key = _progress_key(progress_id, aes_id)
    if not key:
        return
    now = time.time()
    rec = {
        "done": 0,
        "total": 0,
        "pending": 0,
        "lang": "",
        "elapsed": 0,
        "status": "running",
        "updated": now,
        "aes_id": int(aes_id or 0),
    }
    with _PROGRESS_LOCK:
        _prune_visuals_progress(now)
        _PROGRESS[key] = rec
        _write_progress_file(key, rec)


def update_visuals_progress(progress_id: str, *, aes_id: int | None = None, **kw: Any) -> None:
    key = _progress_key(progress_id, aes_id)
    if not key:
        return
    now = time.time()
    with _PROGRESS_LOCK:
        rec = _PROGRESS.get(key) or _read_progress_file(key)
        if rec is None:
            rec = {"status": "running", "updated": now, "aes_id": int(aes_id or 0)}
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
        if aes_id:
            rec["aes_id"] = int(aes_id)
        _PROGRESS[key] = rec
        _write_progress_file(key, rec)


def get_visuals_progress(progress_id: str, *, aes_id: int | None = None) -> dict[str, Any] | None:
    key = _progress_key(progress_id, aes_id)
    if not key:
        return None
    now = time.time()
    with _PROGRESS_LOCK:
        _prune_visuals_progress(now)
        rec = _PROGRESS.get(key) or _read_progress_file(key)
        if rec is None:
            return None
        if aes_id and int(rec.get("aes_id") or 0) not in {0, int(aes_id)}:
            return None
        _PROGRESS[key] = rec
        return dict(rec)


@contextmanager
def payload_load_memo() -> Iterator[None]:
    """Reuse AES/item/entry loads across the collect + apply localize_export passes."""
    token = _LOAD_MEMO.set({})
    try:
        yield
    finally:
        _LOAD_MEMO.reset(token)


def memoized_load(key: tuple, fn: Callable[[], Any]) -> Any:
    store = _LOAD_MEMO.get()
    if store is None:
        return fn()
    if key not in store:
        store[key] = fn()
    return store[key]


def localize_export(
    fn: Callable[[], Any],
    *,
    on_progress: Any = None,
    progress_id: str = "",
    aes_id: int | None = None,
) -> Any:
    """Collect live-MT strings, batch-translate them, then run *fn* with the map.

    System languages and English skip the collect pass. *on_progress* matches
    ``t_batch`` (``done``, ``total``, ``lang``, ``elapsed``).
    """
    pid = parse_progress_id(progress_id)
    if pid:
        start_visuals_progress(pid, aes_id=aes_id)

    def emit(**kw: Any) -> None:
        if pid:
            update_visuals_progress(pid, aes_id=aes_id, **kw)
        if on_progress:
            on_progress(**kw)

    lang = current_export_language()
    with payload_load_memo():
        if lang == "en" or is_system_language(lang) or not can_machine_translate(lang):
            result = fn()
            if pid:
                update_visuals_progress(pid, aes_id=aes_id, done=0, total=0, lang=lang, status="done")
            return result

        session: dict[str, Any] = {"phase": "collect", "texts": [], "map": {}}
        token = _TX_SESSION.set(session)
        try:
            first = fn()
            unique = list(dict.fromkeys(item for item in session["texts"] if str(item).strip()))
            emit(done=0, total=len(unique), lang=lang, elapsed=0, status="running")
            if not unique:
                if pid:
                    update_visuals_progress(
                        pid, aes_id=aes_id, done=0, total=0, lang=lang, status="done"
                    )
                return first
            translated = t_batch(unique, on_progress=emit)
            session["map"] = {
                src: dst for src, dst in zip(unique, translated) if dst and str(dst).strip()
            }
            session["phase"] = "apply"
            result = fn()
            if pid:
                update_visuals_progress(
                    pid,
                    aes_id=aes_id,
                    done=len(unique),
                    total=len(unique),
                    lang=lang,
                    status="done",
                )
            return result
        except Exception:
            if pid:
                update_visuals_progress(pid, aes_id=aes_id, status="failed")
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


def rtl_css(lang: str | None = None) -> str:
    """RTL narrative justify. Fonts live in ``typography`` — do not add stacks here."""
    if not is_rtl(lang):
        return ""
    return """
html[dir="rtl"] .upr-nar-p--Body {
  text-align: justify;
}
"""
