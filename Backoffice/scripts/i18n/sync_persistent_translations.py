#!/usr/bin/env python3
"""
Sync translations from the Docker image baseline to a persistent volume.

Designed to run during container startup (entrypoint.sh) when
TRANSLATIONS_PERSISTENT_PATH is set (Azure /home, Docker named volume, etc.).

Operations:
  1. Seed   – first boot: copy baseline translations to persistent path.
  2. Merge  – subsequent boots: add new msgids from the baseline while
              preserving existing msgstr values edited by admins.
  3. Compile – produce .mo from every .po in the persistent path.

Usage:
  python scripts/sync_persistent_translations.py <persistent_path>

  <persistent_path>  Directory backed by persistent storage.

The baseline translations are read from translations_base/ at the Backoffice
root (created by the Dockerfile).  This avoids conflicts when the live
translations/ dir is itself a volume mount or symlink.
"""

import logging
import os
import shutil
import sys

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
BACKOFFICE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if BACKOFFICE_DIR not in sys.path:
    sys.path.insert(0, BACKOFFICE_DIR)

logger = logging.getLogger(__name__)

try:
    import polib  # type: ignore
except Exception as exc:
    raise SystemExit(f"polib is required: {exc}")

# Baseline copy created by the Dockerfile (never shadowed by volume mounts).
# Falls back to translations/ for non-Docker usage (e.g. local testing).
_baseline = os.path.join(BACKOFFICE_DIR, "translations_base")
_app_trans = os.path.join(BACKOFFICE_DIR, "translations")
IMAGE_TRANSLATIONS_DIR = _baseline if os.path.isdir(_baseline) else _app_trans


# ------------------------------------------------------------------
# Seed
# ------------------------------------------------------------------

def _is_empty(path: str) -> bool:
    """Return True when *path* does not exist or contains no locale dirs."""
    if not os.path.isdir(path):
        return True
    for name in os.listdir(path):
        child = os.path.join(path, name)
        if os.path.isdir(child) and not name.startswith("."):
            return False
    # Also check for messages.pot at the root level
    if os.path.isfile(os.path.join(path, "messages.pot")):
        return False
    return True


def seed(persistent_path: str) -> None:
    """Copy the image's translations tree into *persistent_path*."""
    logger.info("Seeding persistent translations from %s", IMAGE_TRANSLATIONS_DIR)
    os.makedirs(persistent_path, exist_ok=True)

    for item in os.listdir(IMAGE_TRANSLATIONS_DIR):
        src = os.path.join(IMAGE_TRANSLATIONS_DIR, item)
        dst = os.path.join(persistent_path, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    logger.info("Seed complete (%s)", persistent_path)


# ------------------------------------------------------------------
# Merge
# ------------------------------------------------------------------

def _locale_dirs(base: str):
    """Yield (locale_code, abs_path) for each locale directory under *base*."""
    if not os.path.isdir(base):
        return
    for name in sorted(os.listdir(base)):
        child = os.path.join(base, name)
        if os.path.isdir(child) and not name.startswith("."):
            yield name, child


def merge(persistent_path: str) -> None:
    """Merge new msgids from the image into the persistent .po files."""
    logger.info("Merging image translations into %s", persistent_path)

    # Copy .pot catalogue so extract-update works from the persistent path.
    image_pot_path = os.path.join(IMAGE_TRANSLATIONS_DIR, "messages.pot")
    persistent_pot_path = os.path.join(persistent_path, "messages.pot")
    if os.path.isfile(image_pot_path):
        shutil.copy2(image_pot_path, persistent_pot_path)

    # Load the set of (msgctxt, msgid) keys from messages.pot as the authoritative
    # reference for which strings are currently active in the source code.
    # Using the POT rather than the image PO files prevents strings from being
    # wrongly obsoleted when an admin ran "Extract & Update" on the live server
    # after a deploy where PO files were not regenerated in the image — those
    # entries exist in Azure Files PO but not in the image PO, so comparing
    # against image PO would incorrectly mark them obsolete on the next deploy.
    pot_keys: set[tuple] = set()
    if os.path.isfile(persistent_pot_path):
        try:
            pot_po = polib.pofile(persistent_pot_path)
            for entry in pot_po:
                if not getattr(entry, "obsolete", False) and entry.msgid:
                    pot_keys.add((getattr(entry, "msgctxt", None) or None, entry.msgid))
            logger.info("  Loaded %d active keys from messages.pot", len(pot_keys))
        except Exception as exc:
            logger.warning("Could not load messages.pot for merge reference: %s", exc)

    for locale, image_locale_dir in _locale_dirs(IMAGE_TRANSLATIONS_DIR):
        image_po_path = os.path.join(image_locale_dir, "LC_MESSAGES", "messages.po")
        if not os.path.isfile(image_po_path):
            continue

        persistent_po_path = os.path.join(
            persistent_path, locale, "LC_MESSAGES", "messages.po"
        )

        if not os.path.isfile(persistent_po_path):
            # Locale added in a new release — copy wholesale.
            os.makedirs(os.path.dirname(persistent_po_path), exist_ok=True)
            shutil.copy2(image_po_path, persistent_po_path)
            logger.info("  %s: new locale copied from image", locale)
            continue

        _merge_locale(locale, image_po_path, persistent_po_path, pot_keys)

    # Handle locales present on persistent volume but removed from image:
    # leave them in place (admin may have added them manually).
    logger.info("Merge complete")


def _merge_locale(
    locale: str,
    image_po_path: str,
    persistent_po_path: str,
    pot_keys: set | None = None,
) -> None:
    """Merge a single locale's .po file.

    pot_keys, when supplied, is the set of (msgctxt, msgid) tuples extracted
    from messages.pot and used as the authoritative reference for which strings
    are still active in the source code.  This is more reliable than image_keys
    (the PO file's active entries) because it reflects what pybabel extract
    actually found in the source tree, even when PO files were not regenerated
    before the Docker image was built.  Falls back to image_keys when absent.
    """
    image_po = polib.pofile(image_po_path)
    persistent_po = polib.pofile(persistent_po_path)

    # Build lookup of currently-active persistent entries.
    persistent_map: dict[tuple, "polib.POEntry"] = {}
    for entry in persistent_po:
        if getattr(entry, "obsolete", False):
            continue
        key = (getattr(entry, "msgctxt", None) or None, entry.msgid)
        persistent_map[key] = entry

    # Index of previously-obsoleted entries so translations can be recovered
    # if the string is restored to active status (e.g. a string incorrectly
    # obsoleted by a prior deploy can be reactivated with its msgstr intact).
    obsolete_map: dict[tuple, "polib.POEntry"] = {}
    for entry in persistent_po.obsolete_entries():
        key = (getattr(entry, "msgctxt", None) or None, entry.msgid)
        if key not in obsolete_map:
            obsolete_map[key] = entry

    image_keys: set[tuple] = set()
    added = 0
    reactivated = 0
    preserved = 0
    backfilled = 0

    for img_entry in image_po:
        if getattr(img_entry, "obsolete", False):
            continue
        key = (getattr(img_entry, "msgctxt", None) or None, img_entry.msgid)
        image_keys.add(key)

        existing = persistent_map.get(key)
        if existing is None:
            # String is in the new image but not currently active in the
            # persistent PO.  Recover the translated msgstr from a previously-
            # obsoleted entry so we don't lose work done by translators.
            prev_obsolete = obsolete_map.get(key)
            recovered_msgstr = ""
            recovered_plural: dict | None = None
            if prev_obsolete:
                recovered_msgstr = (prev_obsolete.msgstr or "").strip()
                if getattr(prev_obsolete, "msgstr_plural", None):
                    recovered_plural = dict(prev_obsolete.msgstr_plural)

            new_entry = polib.POEntry(
                msgid=img_entry.msgid,
                msgstr=recovered_msgstr or img_entry.msgstr,
                msgctxt=getattr(img_entry, "msgctxt", None),
                msgid_plural=getattr(img_entry, "msgid_plural", None) or "",
                occurrences=img_entry.occurrences,
                comment=img_entry.comment,
                tcomment=img_entry.tcomment,
                flags=img_entry.flags,
            )
            if recovered_plural:
                new_entry.msgstr_plural = recovered_plural
            elif getattr(img_entry, "msgstr_plural", None):
                new_entry.msgstr_plural = dict(img_entry.msgstr_plural)
            persistent_po.append(new_entry)
            if prev_obsolete:
                reactivated += 1
            else:
                added += 1
        else:
            # Entry exists — keep persistent msgstr (admin edits).
            # Update metadata from image (occurrences, comments) so
            # tooling stays accurate, but never overwrite msgstr.
            existing.occurrences = img_entry.occurrences
            existing.comment = img_entry.comment
            existing.tcomment = img_entry.tcomment
            if not (existing.msgstr or "").strip() and (img_entry.msgstr or "").strip():
                existing.msgstr = img_entry.msgstr
                backfilled += 1
            if getattr(img_entry, "msgstr_plural", None):
                merged_plural = dict(getattr(existing, "msgstr_plural", None) or {})
                for form, image_value in img_entry.msgstr_plural.items():
                    if not (merged_plural.get(form) or "").strip() and (image_value or "").strip():
                        merged_plural[form] = image_value
                        backfilled += 1
                if merged_plural:
                    existing.msgstr_plural = merged_plural
            preserved += 1

    # Determine which strings are still active in the source code.
    # Prefer pot_keys (from messages.pot) over image_keys (from image PO) because
    # the POT reflects the actual source scan and is correct even when PO files
    # were not regenerated before the image was built.
    active_source_keys = pot_keys if pot_keys else image_keys

    # Mark entries that are no longer present in the source code as obsolete.
    obsoleted = 0
    for key, entry in persistent_map.items():
        if key not in active_source_keys:
            entry.obsolete = True
            obsoleted += 1

    from app.utils.po_lock import po_file_lock

    with po_file_lock(persistent_po_path):
        persistent_po.save()
    logger.info(
        "  %s: +%d new, %d reactivated, %d backfilled, %d preserved, %d obsoleted",
        locale, added, reactivated, backfilled, preserved, obsoleted,
    )


# ------------------------------------------------------------------
# Compile
# ------------------------------------------------------------------

def compile_all(translations_dir: str) -> None:
    """Compile every .po under *translations_dir* to .mo."""
    from app.utils.po_lock import po_file_lock

    logger.info("Compiling .mo files in %s", translations_dir)
    compiled = 0
    for locale, locale_dir in _locale_dirs(translations_dir):
        po_path = os.path.join(locale_dir, "LC_MESSAGES", "messages.po")
        mo_path = os.path.join(locale_dir, "LC_MESSAGES", "messages.mo")
        if not os.path.isfile(po_path):
            continue
        try:
            with po_file_lock(po_path):
                po = polib.pofile(po_path)
                po.save_as_mofile(mo_path)
            compiled += 1
        except Exception as exc:
            logger.error("  %s: compile failed: %s", locale, exc)
    logger.info("Compiled %d locale(s)", compiled)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <persistent_path>", file=sys.stderr)
        raise SystemExit(1)

    persistent_path = os.path.abspath(sys.argv[1])

    if not os.path.isdir(IMAGE_TRANSLATIONS_DIR):
        logger.error("Image translations not found at %s", IMAGE_TRANSLATIONS_DIR)
        raise SystemExit(1)

    if _is_empty(persistent_path):
        seed(persistent_path)
    else:
        merge(persistent_path)

    compile_all(persistent_path)

    from app.utils.po_lock import touch_translation_sentinel
    touch_translation_sentinel(persistent_path)

    logger.info("Translation sync finished (%s)", persistent_path)


if __name__ == "__main__":
    # Use stdout so Azure Log Stream does not color INFO as errors (stderr is red).
    logging.basicConfig(
        level=logging.INFO,
        format="[translations] %(message)s",
        stream=sys.stdout,
    )
    main()
