#!/usr/bin/env python3
"""
Extract translatable strings from source code/templates and update PO files.

This is the canonical i18n workflow for Backoffice:
1) Extract to a POT file (source of truth): translations/messages.pot
2) Update all locales in translations/*/LC_MESSAGES/messages.po
   - Removed msgids are marked as obsolete (#~) by Babel during update.
3) (Optional) Compile PO -> MO (already handled by scripts/compile_translations.py)

Usage (from Backoffice/):
  py scripts/extract_update_translations.py
  py scripts/extract_update_translations.py --compile
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import polib  # type: ignore
except Exception as e:
    logger.debug("polib import fallback: %s", e)
    polib = None


KEYWORDS = [
    "_",
    "gettext",
    "ngettext",
    "lazy_gettext",
    # Common aliases used in this codebase (avoid missing strings in extraction)
    "_gettext",
    "_ngettext",
    "babel_",
    "babel_ngettext",
    # app.utils.notifications.translate_notification_message — dict literals are NOT extracted
    "_notification_msgid:1",
]


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            "Command failed:\n"
            f"  {' '.join(cmd)}\n\n"
            f"stdout:\n{proc.stdout}\n\n"
            f"stderr:\n{proc.stderr}\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and update Flask-Babel translations.")
    parser.add_argument("--compile", action="store_true", help="Compile PO -> MO after updating")
    args = parser.parse_args()

    backoffice_dir = Path(__file__).resolve().parent.parent
    babel_cfg = backoffice_dir / "config" / "babel.cfg"
    babel_ignore = backoffice_dir / "config" / ".babelignore"
    translations_dir = backoffice_dir / "translations"
    pot_file = translations_dir / "messages.pot"

    if not babel_cfg.exists():
        raise SystemExit(f"Missing Babel config: {babel_cfg}")
    if not translations_dir.exists():
        raise SystemExit(f"Missing translations dir: {translations_dir}")

    # Prefer calling pybabel directly (installed via Babel dependency).
    # On Windows, this should exist once the venv deps are installed.
    extract_cmd = [
        "pybabel",
        "extract",
        "-F",
        str(babel_cfg),
        "-o",
        str(pot_file),
        "-c",
        "NOTE:",
        "--sort-output",
    ]

    # Parse .babelignore and convert to --ignore-dirs
    # Babel doesn't support -X flag, so we parse the ignore file ourselves
    if babel_ignore.exists():
        ignore_dirs = []
        with open(babel_ignore, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Convert .gitignore-style patterns to Babel directory ignores
                # Patterns like **/node_modules/** or node_modules/ become directory ignores
                if line.endswith("/**") or line.endswith("/*"):
                    # Directory pattern: remove trailing /** or /*
                    dir_pattern = line.rstrip("/*")
                elif line.endswith("/"):
                    # Directory pattern: remove trailing /
                    dir_pattern = line.rstrip("/")
                elif "/" not in line and not line.startswith("*"):
                    # Simple directory name (no slashes, not a glob)
                    dir_pattern = line
                else:
                    # Skip complex glob patterns that don't map well to --ignore-dirs
                    continue

                # Remove leading **/ if present
                if dir_pattern.startswith("**/"):
                    dir_pattern = dir_pattern[3:]

                if dir_pattern:
                    ignore_dirs.append(dir_pattern)

        # Add all ignore dirs as a single space-separated argument
        if ignore_dirs:
            extract_cmd.extend(["--ignore-dirs", " ".join(ignore_dirs)])

    for kw in KEYWORDS:
        extract_cmd.extend(["-k", kw])
    extract_cmd.append(".")

    update_cmd = [
        "pybabel",
        "update",
        "-i",
        str(pot_file),
        "-d",
        str(translations_dir),
        "-D",
        "messages",
        "--no-fuzzy-matching",  # Disable fuzzy matching - we want exact matches only
    ]

    # Snapshot the current POT's occurrences before extraction so we can tag
    # entries that become obsolete with their original source location.
    old_pot_occurrences: dict[str, list[tuple[str, str]]] = {}
    if polib is not None and pot_file.exists():
        try:
            _old_pot = polib.pofile(str(pot_file))
            for _e in _old_pot:
                if _e.msgid and _e.occurrences and not _e.obsolete:
                    old_pot_occurrences[_e.msgid] = _e.occurrences
        except Exception as _ex:
            logger.warning("Could not snapshot old POT for obsolete tagging: %s", _ex)

    logger.info("[i18n] Extracting -> %s", pot_file.relative_to(backoffice_dir))
    _run(extract_cmd, cwd=backoffice_dir)

    logger.info("[i18n] Updating locales under %s", translations_dir.relative_to(backoffice_dir))
    _run(update_cmd, cwd=backoffice_dir)

    # Populate English msgstr fields and clear fuzzy flags in all languages
    if polib is not None:
        logger.info("[i18n] Fixing translations in all locales...")

        # Process English first (special handling - msgstr = msgid)
        en_po_path = translations_dir / "en" / "LC_MESSAGES" / "messages.po"
        if en_po_path.exists():
            logger.info("  - Processing English (en)...")
            try:
                po = polib.pofile(str(en_po_path))
                updated_count = 0
                for entry in po:
                    if entry.obsolete:
                        continue

                    # Handle plural forms
                    if entry.msgid_plural:
                        needs_update = False
                        if 'fuzzy' in entry.flags:
                            entry.flags.remove('fuzzy')
                            needs_update = True

                        if len(entry.msgstr_plural) == 0:
                            entry.msgstr_plural[0] = entry.msgid
                            entry.msgstr_plural[1] = entry.msgid_plural
                            updated_count += 1
                        else:
                            if entry.msgstr_plural.get(0) != entry.msgid or entry.msgstr_plural.get(1) != entry.msgid_plural:
                                entry.msgstr_plural[0] = entry.msgid
                                entry.msgstr_plural[1] = entry.msgid_plural
                                needs_update = True
                            if needs_update:
                                updated_count += 1
                    else:
                        needs_update = False
                        if not entry.msgstr or entry.msgstr != entry.msgid:
                            needs_update = True
                        if 'fuzzy' in entry.flags:
                            entry.flags.remove('fuzzy')
                            needs_update = True
                        if needs_update:
                            entry.msgstr = entry.msgid
                            updated_count += 1

                if updated_count > 0:
                    po.save(str(en_po_path))
                    logger.info("    Updated %d English translation entries", updated_count)
                else:
                    logger.info("    English translations already up to date")
            except Exception as e:
                logger.warning("Could not update English translations: %s", e)

        # Process all other languages (clear fuzzy flags, mark incorrect translations for review)
        for locale_dir in sorted(translations_dir.iterdir()):
            if locale_dir.name == "en" or not locale_dir.is_dir():
                continue

            po_path = locale_dir / "LC_MESSAGES" / "messages.po"
            if not po_path.exists():
                continue

            logger.info("  - Processing %s...", locale_dir.name)
            try:
                po = polib.pofile(str(po_path))
                fuzzy_cleared = 0
                incorrect_cleared = 0

                for entry in po:
                    if entry.obsolete:
                        continue

                    # Clear fuzzy flags (fuzzy matches are unreliable)
                    if 'fuzzy' in entry.flags:
                        entry.flags.remove('fuzzy')
                        fuzzy_cleared += 1

                        # For fuzzy entries, if the translation seems wrong (same as msgid for non-English),
                        # clear it so it can be properly translated
                        # Note: Some languages might legitimately have msgstr == msgid for certain terms,
                        # so we'll be conservative and only clear obviously problematic ones
                        if entry.msgid_plural:
                            # For plurals, if both forms match msgid exactly, it's likely wrong
                            if (entry.msgstr_plural.get(0) == entry.msgid and
                                entry.msgstr_plural.get(1) == entry.msgid_plural):
                                # Clear the translation so it can be retranslated
                                entry.msgstr_plural.clear()
                                incorrect_cleared += 1
                        else:
                            # For singular, if msgstr exactly matches msgid (and it's not English),
                            # it's likely a copy-paste error from fuzzy matching
                            if entry.msgstr == entry.msgid:
                                entry.msgstr = ""
                                incorrect_cleared += 1

                if fuzzy_cleared > 0 or incorrect_cleared > 0:
                    po.save(str(po_path))
                    if fuzzy_cleared > 0:
                        logger.info("    Cleared %d fuzzy flags", fuzzy_cleared)
                    if incorrect_cleared > 0:
                        logger.info("    Cleared %d incorrect translations (marked for retranslation)", incorrect_cleared)
                else:
                    logger.info("    No issues found")
            except Exception as e:
                logger.warning("Could not process %s: %s", locale_dir.name, e)

    # Sync missing #: source references from POT to PO files.
    # Entries added manually (e.g. via the UI) or from older PO states may lack
    # occurrence comments, which causes the management page to show "Unknown" source.
    if polib is not None:
        logger.info("[i18n] Syncing source references (#:) from POT to PO files...")
        try:
            pot = polib.pofile(str(pot_file))
            pot_occurrences = {e.msgid: e.occurrences for e in pot if e.msgid and e.occurrences}
        except Exception as e:
            logger.warning("Could not load POT for occurrence sync: %s", e)
            pot_occurrences = {}

        if pot_occurrences:
            for locale_dir in sorted(translations_dir.iterdir()):
                if not locale_dir.is_dir():
                    continue
                po_path = locale_dir / "LC_MESSAGES" / "messages.po"
                if not po_path.exists():
                    continue
                try:
                    po = polib.pofile(str(po_path))
                    synced = 0
                    for entry in po:
                        if entry.obsolete or not entry.msgid:
                            continue
                        if not entry.occurrences and entry.msgid in pot_occurrences:
                            entry.occurrences = pot_occurrences[entry.msgid]
                            synced += 1
                    if synced > 0:
                        po.save(str(po_path))
                        logger.info("  - %s: synced %d source references", locale_dir.name, synced)
                except Exception as e:
                    logger.warning("Could not sync occurrences for %s: %s", locale_dir.name, e)

    # Tag obsolete entries with their original source location so the management
    # UI can display where each removed string came from instead of "Unknown".
    # Format: "#. [Removed] was: app/templates/admin/foo.html:123"
    if polib is not None and old_pot_occurrences:
        logger.info("[i18n] Tagging obsolete entries with original source references...")
        for locale_dir in sorted(translations_dir.iterdir()):
            if not locale_dir.is_dir():
                continue
            po_path = locale_dir / "LC_MESSAGES" / "messages.po"
            if not po_path.exists():
                continue
            try:
                po = polib.pofile(str(po_path))
                tagged = 0
                for entry in po:
                    if not entry.obsolete or not entry.msgid:
                        continue
                    if entry.tcomment and "[Removed]" in entry.tcomment:
                        continue  # already tagged from a previous run
                    occ = old_pot_occurrences.get(entry.msgid)
                    if occ:
                        src_file, src_line = occ[0]
                        src_ref = f"{src_file}:{src_line}" if src_line else src_file
                        entry.tcomment = f"[Removed] was: {src_ref}"
                        tagged += 1
                if tagged > 0:
                    po.save(str(po_path))
                    logger.info("  - %s: tagged %d obsolete entries", locale_dir.name, tagged)
            except Exception as e:
                logger.warning("Could not tag obsolete entries for %s: %s", locale_dir.name, e)

    # Report obsolete entries (removed msgids) per locale, if polib is available.
    if polib is not None:
        logger.info("[i18n] Obsolete entries report (removed msgids marked as #~):")
        for locale_dir in sorted(translations_dir.iterdir()):
            po_path = locale_dir / "LC_MESSAGES" / "messages.po"
            if not po_path.exists():
                continue
            try:
                po = polib.pofile(str(po_path))
                obsolete = len([e for e in po if getattr(e, "obsolete", False)])
                total = len(po)
                if obsolete:
                    logger.info("  - %s: %d obsolete / %d total", locale_dir.name, obsolete, total)
            except Exception as e:
                logger.debug("PO parse skip %s: %s", po_path, e)
                # Don't hard-fail extraction if a locale has a malformed PO; compilation will surface it too.
                continue

    if args.compile:
        logger.info("[i18n] Compiling PO → MO")
        compile_script = backoffice_dir / "scripts" / "compile_translations.py"
        _run([sys.executable, str(compile_script)], cwd=backoffice_dir)

    logger.info("[i18n] Done.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
