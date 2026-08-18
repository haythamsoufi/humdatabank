"""Gettext catalog source of truth in the database; .po/.mo are build artifacts."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

PROVENANCE_MACHINE = "machine"
PROVENANCE_HUMAN = "human"
PROVENANCE_IMPORTED = "imported"
PROVENANCE_UNKNOWN = "unknown_presumed_machine"
PROVENANCE_REMOTE_SYNC = "remote_sync"

STATUS_UNREVIEWED = "unreviewed"
STATUS_APPROVED = "approved"


def msgid_hash(msgid: str) -> str:
    return hashlib.sha256((msgid or "").encode("utf-8")).hexdigest()[:16]


def _actor_user_id() -> Optional[int]:
    try:
        if current_user and getattr(current_user, "is_authenticated", False):
            return int(current_user.id)
    except Exception:
        logger.debug("catalog_service: no actor user", exc_info=True)
    return None


def _is_human_protected(row: Any) -> bool:
    """A row is protected once a human has approved non-empty text for it.

    Machine/imported/unknown-provenance writers must never silently downgrade
    that work; see `force=` on upsert_string/upsert_batch for the deliberate
    override path.
    """
    return bool(row is not None and row.provenance == PROVENANCE_HUMAN and (row.msgstr or "").strip())


def _apply_row_update(
    row: Any,
    *,
    locale: str,
    msgid: str,
    new_msgstr: str,
    provenance: str,
    engine: Optional[str],
    status: Optional[str],
    actor: Optional[int],
    is_plural: bool = False,
    msgstr_plural: Optional[dict] = None,
    force: bool = False,
) -> Tuple[Any, bool, bool]:
    """Create or mutate *row* in-place (not flushed/committed). Returns (row, changed, protected)."""
    from app.models.translation_quality import TranslationString

    if row is not None and not force and provenance != PROVENANCE_HUMAN and _is_human_protected(row):
        return row, False, True

    resolved_status = status or (
        STATUS_APPROVED if provenance == PROVENANCE_HUMAN else STATUS_UNREVIEWED
    )

    if row is None:
        row = TranslationString(
            locale=locale,
            msgid=msgid,
            msgid_hash=msgid_hash(msgid),
            msgstr=new_msgstr,
            provenance=provenance,
            engine=engine,
            actor_user_id=actor,
            status=resolved_status,
            is_plural=bool(is_plural),
            msgstr_plural=msgstr_plural,
            version=1,
        )
        db.session.add(row)
        return row, bool(new_msgstr.strip()), False

    if row.msgstr != new_msgstr or (msgstr_plural and row.msgstr_plural != msgstr_plural):
        row.msgstr = new_msgstr
        row.provenance = provenance
        row.engine = engine
        row.actor_user_id = actor
        row.status = resolved_status
        row.is_plural = bool(is_plural)
        if msgstr_plural is not None:
            row.msgstr_plural = msgstr_plural
        row.version = int(row.version or 1) + 1
        row.updated_at = utcnow()
        return row, True, False

    # Same text: still upgrade provenance when a human confirms.
    if provenance == PROVENANCE_HUMAN and row.provenance != PROVENANCE_HUMAN:
        row.provenance = PROVENANCE_HUMAN
        row.status = STATUS_APPROVED
        row.actor_user_id = actor
        row.updated_at = utcnow()
        return row, True, False

    return row, False, False


def upsert_string(
    *,
    locale: str,
    msgid: str,
    msgstr: str,
    provenance: str,
    engine: Optional[str] = None,
    status: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    is_plural: bool = False,
    msgstr_plural: Optional[dict] = None,
    compile_after: bool = False,
    sync_po: bool = True,
    force: bool = False,
) -> bool:
    """Insert or update one catalog row. Returns True if msgstr changed.

    Human-approved rows (provenance="human" with non-empty text) are protected
    from being silently downgraded by a non-human write. Pass force=True only
    when the caller has an explicit, deliberate reason to replace reviewed text.
    """
    from app.models.translation_quality import TranslationString

    locale = (locale or "").strip().lower()
    if not locale or not msgid:
        return False

    row = TranslationString.query.filter_by(locale=locale, msgid=msgid).first()
    new_msgstr = "" if msgstr is None else str(msgstr)
    actor = actor_user_id if actor_user_id is not None else _actor_user_id()

    row, changed, protected = _apply_row_update(
        row,
        locale=locale,
        msgid=msgid,
        new_msgstr=new_msgstr,
        provenance=provenance,
        engine=engine,
        status=status,
        actor=actor,
        is_plural=is_plural,
        msgstr_plural=msgstr_plural,
        force=force,
    )

    if protected:
        logger.info(
            "catalog_service.upsert_string: protected human-approved string (locale=%s, msgid_hash=%s) from %s overwrite",
            locale, msgid_hash(msgid), provenance,
        )
        return False

    if changed:
        db.session.flush()
        if sync_po:
            _sync_po_entry(locale, msgid, new_msgstr, is_plural=is_plural, msgstr_plural=msgstr_plural)
        if compile_after:
            from app.utils.po_persistence import finalize_translation_writes

            finalize_translation_writes([locale], refresh=True)
    return changed


def upsert_many(
    msgid: str,
    lang_to_msgstr: Dict[str, str],
    *,
    provenance: str,
    engine: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[int, List[str]]:
    """Update one msgid across locales. Compiles once at the end."""
    updated: List[str] = []
    for lang, msgstr in (lang_to_msgstr or {}).items():
        if upsert_string(
            locale=lang,
            msgid=msgid,
            msgstr=msgstr,
            provenance=provenance,
            engine=engine,
            status=status,
            compile_after=False,
        ):
            updated.append(lang)
    if updated:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("catalog_service.upsert_many commit failed")
            return 0, []
        from app.utils.po_persistence import finalize_translation_writes

        finalize_translation_writes(updated, refresh=True)
    else:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return len(updated), updated


def upsert_batch(
    items: Iterable[Tuple[str, str, str]],
    *,
    provenance: str,
    engine: Optional[str] = None,
    status: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Batch upsert many (msgid, locale, msgstr) triples efficiently.

    Unlike calling upsert_string/upsert_many in a loop, this does exactly one
    DB round-trip to prefetch existing rows and one .po load/save cycle per
    *distinct locale* touched — not one per item. Use this for bulk operations
    (e.g. bulk auto-translate over many strings) to avoid O(n) full-catalog PO
    rewrites. The same human-approval protection as upsert_string applies.

    Returns {"updated": int, "updated_locales": [str, ...],
             "updated_pairs": [(locale, msgid), ...], "skipped_protected": int}.
    """
    from app.models.translation_quality import TranslationString

    normalized: List[Tuple[str, str, str]] = []
    for msgid, locale, msgstr in items:
        loc = (locale or "").strip().lower()
        if not loc or not msgid:
            continue
        normalized.append((msgid, loc, "" if msgstr is None else str(msgstr)))

    if not normalized:
        return {"updated": 0, "updated_locales": [], "updated_pairs": [], "skipped_protected": 0}

    locales_involved = sorted({loc for _mid, loc, _ms in normalized})
    existing = {
        (r.locale, r.msgid): r
        for r in TranslationString.query.filter(TranslationString.locale.in_(locales_involved)).all()
    }
    actor = _actor_user_id()

    changed_by_locale: Dict[str, Dict[str, str]] = {}
    updated_pairs: List[Tuple[str, str]] = []
    skipped_protected = 0

    for msgid, locale, msgstr in normalized:
        row = existing.get((locale, msgid))
        row, changed, protected = _apply_row_update(
            row,
            locale=locale,
            msgid=msgid,
            new_msgstr=msgstr,
            provenance=provenance,
            engine=engine,
            status=status,
            actor=actor,
            force=force,
        )
        if protected:
            skipped_protected += 1
            continue
        existing[(locale, msgid)] = row
        if changed:
            changed_by_locale.setdefault(locale, {})[msgid] = msgstr
            updated_pairs.append((locale, msgid))

    if skipped_protected:
        logger.info("catalog_service.upsert_batch: skipped %d human-approved string(s) (provenance=%s)", skipped_protected, provenance)

    if not updated_pairs:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return {"updated": 0, "updated_locales": [], "updated_pairs": [], "skipped_protected": skipped_protected}

    try:
        db.session.flush()
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("catalog_service.upsert_batch commit failed")
        return {"updated": 0, "updated_locales": [], "updated_pairs": [], "skipped_protected": skipped_protected}

    updated_locales = sorted(changed_by_locale.keys())
    for locale, msgid_map in changed_by_locale.items():
        _sync_po_entries_bulk(locale, msgid_map)

    from app.utils.po_persistence import finalize_translation_writes

    finalize_translation_writes(updated_locales, refresh=True)

    return {
        "updated": len(updated_pairs),
        "updated_locales": updated_locales,
        "updated_pairs": updated_pairs,
        "skipped_protected": skipped_protected,
    }


def apply_imported_updates(locale: str, msgid_to_msgstr: Dict[str, str]) -> int:
    """Write imported PO/XLSX values into the catalog without re-saving .po files."""
    n = 0
    for msgid, msgstr in (msgid_to_msgstr or {}).items():
        if upsert_string(
            locale=locale,
            msgid=msgid,
            msgstr=msgstr,
            provenance=PROVENANCE_IMPORTED,
            compile_after=False,
            sync_po=False,
        ):
            n += 1
    if n:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("catalog_service.apply_imported_updates commit failed")
            return 0
    return n


def compile_locale_from_db(locale: str) -> int:
    """Regenerate the .po artifact from translation_string rows, then compile .mo."""
    from app.models.translation_quality import TranslationString
    from app.routes.admin.utilities.helpers import _translations_po_path
    from app.utils.po_persistence import save_po_locked, finalize_translation_writes

    locale = (locale or "").strip().lower()
    if not locale or locale == "en":
        return 0
    po_path = _translations_po_path(locale)
    if not os.path.exists(po_path):
        return 0
    rows = TranslationString.query.filter_by(locale=locale).all()
    by_msgid = {r.msgid: r for r in rows if r.msgid}

    def mutator(po) -> bool:
        changed = False
        for entry in po:
            if not entry.msgid or entry.obsolete:
                continue
            row = by_msgid.get(entry.msgid)
            if row is None:
                continue
            if entry.msgstr != (row.msgstr or ""):
                entry.msgstr = row.msgstr or ""
                changed = True
            if row.is_plural and row.msgstr_plural:
                as_int = {int(k): v for k, v in row.msgstr_plural.items()}
                if getattr(entry, "msgstr_plural", None) != as_int:
                    entry.msgstr_plural = as_int
                    changed = True
        return changed

    save_po_locked(po_path, mutator)
    finalize_translation_writes([locale], refresh=True)
    return len(by_msgid)


def get_msgstr(msgid: str, locale: str) -> str:
    from app.models.translation_quality import TranslationString

    row = TranslationString.query.filter_by(locale=locale, msgid=msgid).first()
    if row is not None and (row.msgstr or "").strip():
        return row.msgstr or ""
    return _read_po_fallback(msgid, locale)


def get_row(msgid: str, locale: str):
    from app.models.translation_quality import TranslationString

    return TranslationString.query.filter_by(locale=locale, msgid=msgid).first()


def list_unreviewed(locale: str, *, limit: int = 50) -> List[Any]:
    from app.models.translation_quality import TranslationString

    return (
        TranslationString.query.filter(
            TranslationString.locale == locale,
            TranslationString.status != STATUS_APPROVED,
            TranslationString.msgstr != "",
        )
        .order_by(TranslationString.updated_at.desc())
        .limit(max(1, int(limit)))
        .all()
    )


def classify_catalog_msgids(pot_ids: Iterable[str], extra_ids: Iterable[str]) -> Tuple[set, set]:
    """Active = in the current .pot. Removed = known keys that are no longer in source."""
    pot = {m for m in pot_ids if m}
    extra = {m for m in extra_ids if m}
    return pot, extra - pot


def load_pot_msgids() -> Tuple[set, Dict[str, str]]:
    """Return (msgid set, source-page map) from messages.pot. Obsolete POT rows are ignored."""
    import polib

    from app.routes.admin.utilities.helpers import _extract_page_name, _translations_pot_path

    pot_ids: set = set()
    sources: Dict[str, str] = {}
    pot_path = _translations_pot_path()
    if not os.path.exists(pot_path):
        return pot_ids, sources
    pot = polib.pofile(pot_path)
    for entry in pot:
        if not entry.msgid or entry.obsolete:
            continue
        pot_ids.add(entry.msgid)
        if entry.occurrences and entry.msgid not in sources:
            src_path, _ = entry.occurrences[0]
            sources[entry.msgid] = _extract_page_name(src_path)
    return pot_ids, sources


def load_catalog_grid(languages: Iterable[str], language_names: Dict[str, str]) -> Dict[str, Any]:
    """Build the manage-translations grid from POT + DB, with .po as fallback.

    A string is 'removed' only when it is not in the current .pot. A leftover
    #~ duplicate of a still-extracted msgid is not treated as removed.
    """
    import polib

    from app.models.translation_quality import TranslationString
    from app.routes.admin.utilities.helpers import _entry_to_display_msgstr, _extract_page_name, _translations_po_path

    langs = [str(l) for l in languages if l]
    pot_ids, msgid_sources = load_pot_msgids()
    translation_data: Dict[str, Dict[str, Any]] = {}
    extra_ids: set = set()

    db_rows = TranslationString.query.filter(TranslationString.locale.in_([l for l in langs if l != "en"])).all()
    by_locale: Dict[str, Dict[str, Any]] = {}
    for row in db_rows:
        by_locale.setdefault(row.locale, {})[row.msgid] = row.msgstr or ""
        extra_ids.add(row.msgid)

    for lang in langs:
        translations: Dict[str, str] = dict(by_locale.get(lang, {}))
        po_path = _translations_po_path(lang)
        if os.path.exists(po_path):
            try:
                po = polib.pofile(po_path)
            except Exception:
                po = None
            if po is not None:
                for entry in po:
                    if not entry.msgid:
                        continue
                    extra_ids.add(entry.msgid)
                    if entry.obsolete:
                        if entry.occurrences and entry.msgid not in msgid_sources:
                            src_path, _ = entry.occurrences[0]
                            msgid_sources[entry.msgid] = "\x00" + _extract_page_name(src_path)
                        display = _entry_to_display_msgstr(entry)
                        if display.strip() and not str(translations.get(entry.msgid) or "").strip():
                            translations[entry.msgid] = display
                        continue
                    display = _entry_to_display_msgstr(entry)
                    if entry.msgid not in translations:
                        translations[entry.msgid] = display
                    elif display.strip() and not str(translations.get(entry.msgid) or "").strip():
                        translations[entry.msgid] = display
                    if entry.occurrences and entry.msgid not in msgid_sources:
                        src_path, _ = entry.occurrences[0]
                        msgid_sources[entry.msgid] = _extract_page_name(src_path)
        if lang != "en":
            extra_ids.update(translations.keys())
        translation_data[lang] = {
            "name": language_names.get(lang, lang.upper()),
            "translations": translations,
        }

    active_ids, removed_ids = classify_catalog_msgids(pot_ids or extra_ids, extra_ids)
    # If POT is missing, fall back to every known msgid as active so the grid is not empty.
    if not pot_ids:
        active_ids, removed_ids = extra_ids, set()
    all_msgids = sorted(active_ids | removed_ids)
    active_translation_msgids = [m for m in all_msgids if m not in removed_ids]

    empty_translation_counts: Dict[str, int] = {}
    empty_translation_msgids: Dict[str, List[str]] = {}
    for lang in langs:
        if lang == "en":
            continue
        lang_translations = translation_data.get(lang, {}).get("translations", {})
        empty = [m for m in active_translation_msgids if not str(lang_translations.get(m) or "").strip()]
        empty_translation_counts[lang] = len(empty)
        empty_translation_msgids[lang] = empty

    return {
        "translation_data": translation_data,
        "all_msgids": all_msgids,
        "active_translation_msgids": active_translation_msgids,
        "obsolete_msgids": removed_ids,
        "msgid_sources": msgid_sources,
        "empty_translation_counts": empty_translation_counts,
        "empty_translation_msgids": empty_translation_msgids,
    }


def _catalog_locales() -> List[str]:
    locales = current_app.config.get("SUPPORTED_LANGUAGES") or ["en", "fr", "es", "ar", "ru", "zh"]
    return [str(loc).strip().lower() for loc in locales if loc]


def catalog_removed_msgids() -> set:
    """Msgids the manage-translations grid treats as removed (not in the current .pot)."""
    from app.models.translation_quality import TranslationString
    from app.routes.admin.utilities.helpers import _translations_po_path

    pot_ids, _sources = load_pot_msgids()
    if not pot_ids:
        return set()

    extra_ids: set = set()
    for (msgid,) in (
        TranslationString.query.with_entities(TranslationString.msgid).distinct().all()
    ):
        if msgid:
            extra_ids.add(msgid)

    import polib

    for locale in _catalog_locales():
        po_path = _translations_po_path(locale)
        if not os.path.exists(po_path):
            continue
        try:
            po = polib.pofile(po_path)
        except Exception:
            logger.debug("catalog_removed_msgids: failed to read %s", po_path, exc_info=True)
            continue
        for entry in po:
            if entry.msgid:
                extra_ids.add(entry.msgid)

    _active, removed = classify_catalog_msgids(pot_ids, extra_ids)
    return removed


def purge_removed_strings(msgid: Optional[str] = None) -> Dict[str, Any]:
    """Delete grid-removed strings from the DB and locale catalogs.

    A string is removed when it is not in the current .pot — including leftover
    live .po entries and ``translation_string`` rows. Active .pot msgids are
    never deleted, even if a stale #~ copy exists.
    """
    from app.models.translation_quality import TranslationString
    from app.routes.admin.utilities.helpers import _translations_po_path
    from app.utils.po_lock import po_file_lock
    from app.utils.po_persistence import finalize_translation_writes

    removed_ids = catalog_removed_msgids()
    if msgid is not None:
        targets = {msgid} if msgid in removed_ids else set()
    else:
        targets = set(removed_ids)

    if not targets:
        return {
            "db_rows": 0,
            "files_updated": 0,
            "entries_removed": 0,
            "file_errors": [],
        }

    db_rows = (
        TranslationString.query.filter(TranslationString.msgid.in_(list(targets)))
        .delete(synchronize_session=False)
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("purge_removed_strings: catalog delete failed")
        return {
            "db_rows": 0,
            "files_updated": 0,
            "entries_removed": 0,
            "file_errors": ["db"],
        }

    import polib

    files_updated = 0
    entries_removed = 0
    file_errors: List[str] = []
    modified_langs: List[str] = []

    for locale in _catalog_locales():
        po_path = _translations_po_path(locale)
        if not os.path.exists(po_path):
            continue
        try:
            with po_file_lock(po_path):
                po = polib.pofile(po_path)
                removed_here = 0
                for entry in list(po):
                    if entry.msgid in targets:
                        po.remove(entry)
                        removed_here += 1
                if removed_here:
                    po.save(po_path)
                    files_updated += 1
                    entries_removed += removed_here
                    modified_langs.append(locale)
        except Exception:
            logger.warning("purge_removed_strings failed for %s", po_path, exc_info=True)
            file_errors.append(locale)

    if modified_langs:
        finalize_translation_writes(modified_langs, refresh=True)

    return {
        "db_rows": int(db_rows or 0),
        "files_updated": files_updated,
        "entries_removed": entries_removed,
        "file_errors": file_errors,
    }


def import_from_po_files(
    locales: Optional[Iterable[str]] = None,
    *,
    provenance: str = PROVENANCE_UNKNOWN,
) -> Dict[str, Any]:
    """Load current .po catalogs into translation_string, including empty msgstr rows.

    Skips obsolete (#~) copies. Does not overwrite human-approved rows.
    Fills empty existing rows when the .po has a value.
    """
    import polib

    from app.models.translation_quality import TranslationString
    from app.routes.admin.utilities.helpers import _translations_po_path

    if locales is None:
        locales = current_app.config.get("SUPPORTED_LANGUAGES") or ["en", "fr", "es", "ar", "ru", "zh"]

    target_locales = [str(loc).strip().lower() for loc in locales if loc and loc != "en"]
    existing_rows = {
        (r.locale, r.msgid): r
        for r in TranslationString.query.filter(TranslationString.locale.in_(target_locales)).all()
    }

    counts: Dict[str, Any] = {}
    pending: List[TranslationString] = []
    filled = 0

    with db.session.no_autoflush:
        for locale in target_locales:
            po_path = _translations_po_path(locale)
            if not os.path.exists(po_path):
                counts[locale] = {"inserted": 0, "filled": 0, "skipped_existing": 0, "skipped_obsolete": 0}
                continue
            po = polib.pofile(po_path)
            obsolete_msgstr: Dict[str, str] = {}
            obsolete_plural: Dict[str, dict] = {}
            for entry in po:
                if not entry.msgid or not entry.obsolete:
                    continue
                text = entry.msgstr or ""
                plural_map = None
                if getattr(entry, "msgstr_plural", None):
                    plural_map = {str(k): v for k, v in entry.msgstr_plural.items()}
                    if not text:
                        text = plural_map.get("0") or next(iter(plural_map.values()), "")
                if str(text).strip():
                    obsolete_msgstr[entry.msgid] = text
                    if plural_map:
                        obsolete_plural[entry.msgid] = plural_map
            inserted = 0
            skipped_existing = 0
            skipped_obsolete = 0
            recovered_obsolete = 0
            seen: set = set()
            for entry in po:
                if not entry.msgid:
                    continue
                if entry.obsolete:
                    skipped_obsolete += 1
                    continue
                if entry.msgid in seen:
                    continue
                seen.add(entry.msgid)
                msgstr = entry.msgstr or ""
                plural = None
                is_plural = False
                if getattr(entry, "msgstr_plural", None):
                    plural = {str(k): v for k, v in entry.msgstr_plural.items()}
                    is_plural = True
                    if not msgstr:
                        msgstr = plural.get("0") or next(iter(plural.values()), "")
                if not str(msgstr).strip() and entry.msgid in obsolete_msgstr:
                    msgstr = obsolete_msgstr[entry.msgid]
                    if entry.msgid in obsolete_plural:
                        plural = obsolete_plural[entry.msgid]
                        is_plural = True
                    recovered_obsolete += 1
                row = existing_rows.get((locale, entry.msgid))
                if row is not None:
                    skipped_existing += 1
                    if (
                        row.provenance != PROVENANCE_HUMAN
                        and not (row.msgstr or "").strip()
                        and str(msgstr).strip()
                    ):
                        row.msgstr = msgstr
                        row.is_plural = bool(is_plural)
                        if plural is not None:
                            row.msgstr_plural = plural
                        row.updated_at = utcnow()
                        filled += 1
                    continue
                pending.append(
                    TranslationString(
                        locale=locale,
                        msgid=entry.msgid,
                        msgid_hash=msgid_hash(entry.msgid),
                        msgstr=msgstr,
                        provenance=provenance,
                        status=STATUS_UNREVIEWED,
                        is_plural=is_plural,
                        msgstr_plural=plural,
                    )
                )
                existing_rows[(locale, entry.msgid)] = pending[-1]
                inserted += 1
            counts[locale] = {
                "inserted": inserted,
                "filled": 0,
                "skipped_existing": skipped_existing,
                "skipped_obsolete": skipped_obsolete,
                "recovered_from_obsolete": recovered_obsolete,
            }

    if pending:
        for i in range(0, len(pending), 500):
            db.session.add_all(pending[i : i + 500])
            db.session.commit()
    elif filled:
        db.session.commit()
    counts["_total_inserted"] = sum(v.get("inserted", 0) for v in counts.values() if isinstance(v, dict))
    counts["_total_filled"] = filled
    return counts


def recover_human_edits_from_audit() -> int:
    """Mark rows human-approved when admin_action_log has a matching msgid_hash."""
    from app.models.system import AdminActionLog
    from app.models.translation_quality import TranslationString

    logs = (
        AdminActionLog.query.filter_by(action_type="translation_review_edit")
        .order_by(AdminActionLog.timestamp.asc())
        .all()
    )
    updated = 0
    for log in logs:
        new_vals = log.new_values if isinstance(log.new_values, dict) else {}
        locale = (new_vals.get("locale") or "").strip().lower()
        hashed = (new_vals.get("msgid_hash") or "").strip()
        if not locale or not hashed:
            desc = log.target_description or ""
            if ":" in desc:
                locale, hashed = desc.split(":", 1)
        if not locale or not hashed:
            continue
        rows = TranslationString.query.filter_by(locale=locale, msgid_hash=hashed).all()
        for row in rows:
            if row.provenance == PROVENANCE_HUMAN:
                continue
            row.provenance = PROVENANCE_HUMAN
            row.status = STATUS_APPROVED
            row.actor_user_id = getattr(log, "admin_user_id", None)
            row.engine = None
            row.updated_at = utcnow()
            updated += 1
    if updated:
        db.session.commit()
    return updated


def record_entity_provenance(
    *,
    entity_type: str,
    entity_id: int,
    field_name: str,
    locale: str,
    provenance: str,
    engine: Optional[str] = None,
) -> None:
    from app.models.translation_quality import TranslationEntityProvenance

    row = TranslationEntityProvenance.query.filter_by(
        entity_type=entity_type,
        entity_id=int(entity_id),
        field_name=field_name,
        locale=locale,
    ).first()
    if row is None:
        db.session.add(
            TranslationEntityProvenance(
                entity_type=entity_type,
                entity_id=int(entity_id),
                field_name=field_name,
                locale=locale,
                provenance=provenance,
                engine=engine,
                actor_user_id=_actor_user_id(),
            )
        )
    else:
        row.provenance = provenance
        row.engine = engine
        row.actor_user_id = _actor_user_id()
        row.updated_at = utcnow()


def _sync_po_entry(
    locale: str,
    msgid: str,
    msgstr: str,
    *,
    is_plural: bool = False,
    msgstr_plural: Optional[dict] = None,
) -> None:
    """Keep the .po artifact in sync so Flask-Babel .mo compile stays unchanged."""
    from app.routes.admin.utilities.helpers import _translations_po_path
    from app.utils.po_persistence import save_po_locked

    po_path = _translations_po_path(locale)
    if not os.path.exists(po_path):
        return

    def mutator(po) -> bool:
        import polib

        entry = po.find(msgid)
        if entry is None:
            if not str(msgstr).strip() and not msgstr_plural:
                return False
            kwargs: dict = {"msgid": msgid, "msgstr": msgstr}
            if is_plural and msgstr_plural:
                kwargs["msgstr_plural"] = {int(k): v for k, v in msgstr_plural.items()}
            po.append(polib.POEntry(**kwargs))
            return True
        changed = False
        if entry.msgstr != msgstr:
            entry.msgstr = msgstr
            changed = True
        if is_plural and msgstr_plural:
            as_int = {int(k): v for k, v in msgstr_plural.items()}
            if getattr(entry, "msgstr_plural", None) != as_int:
                entry.msgstr_plural = as_int
                changed = True
        return changed

    save_po_locked(po_path, mutator)


def _sync_po_entries_bulk(locale: str, msgid_to_msgstr: Dict[str, str]) -> int:
    """Sync many msgid->msgstr updates into one .po file with a single load/save cycle.

    Used by upsert_batch to avoid the O(n) load-mutate-save-per-item cost that
    calling _sync_po_entry in a loop would incur.
    """
    from app.routes.admin.utilities.helpers import _translations_po_path
    from app.utils.po_persistence import save_po_locked

    po_path = _translations_po_path(locale)
    if not os.path.exists(po_path) or not msgid_to_msgstr:
        return 0

    applied = 0

    def mutator(po) -> bool:
        import polib

        nonlocal applied
        changed = False
        for msgid, msgstr in msgid_to_msgstr.items():
            entry = po.find(msgid)
            if entry is None:
                if not str(msgstr).strip():
                    continue
                po.append(polib.POEntry(msgid=msgid, msgstr=msgstr))
                applied += 1
                changed = True
                continue
            if entry.msgstr != msgstr:
                entry.msgstr = msgstr
                applied += 1
                changed = True
        return changed

    save_po_locked(po_path, mutator)
    return applied


def _read_po_fallback(msgid: str, locale: str) -> str:
    try:
        import polib

        from app.routes.admin.utilities.helpers import _translations_po_path

        po_path = _translations_po_path(locale)
        if not os.path.exists(po_path):
            return ""
        entry = polib.pofile(po_path).find(msgid)
        return (entry.msgstr or "") if entry else ""
    except Exception:
        logger.debug("PO fallback read failed", exc_info=True)
        return ""
