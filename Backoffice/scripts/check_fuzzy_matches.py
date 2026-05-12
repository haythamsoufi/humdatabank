#!/usr/bin/env python3
"""
Check for fuzzy matches with incorrect translations in English PO file.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import polib
except ImportError:
    logger.error("polib is not installed. Install with: pip install polib")
    sys.exit(1)

def main():
    backoffice_dir = Path(__file__).resolve().parent.parent
    en_po_path = backoffice_dir / "app" / "translations" / "en" / "LC_MESSAGES" / "messages.po"

    if not en_po_path.exists():
        logger.error("English PO file not found: %s", en_po_path)
        sys.exit(1)

    po = polib.pofile(str(en_po_path))

    # Find fuzzy entries with incorrect translations
    wrong_translations = []
    for entry in po:
        if entry.obsolete:
            continue
        if 'fuzzy' not in entry.flags:
            continue
        if entry.msgid_plural:
            continue  # Skip plurals for now

        # Check if msgstr is different from msgid
        if entry.msgstr and entry.msgstr != entry.msgid:
            wrong_translations.append((entry.msgid, entry.msgstr))

    output_file = backoffice_dir / "fuzzy_matches_report.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Found {len(wrong_translations)} fuzzy entries with incorrect English translations:\n\n")
        f.write("=" * 80 + "\n\n")

        for i, (msgid, msgstr) in enumerate(sorted(wrong_translations), 1):
            f.write(f"{i}. WRONG TRANSLATION:\n")
            f.write(f"   msgid:  \"{msgid}\"\n")
            f.write(f"   msgstr: \"{msgstr}\"\n")
            f.write(f"   Should be: \"{msgid}\"\n\n")

        f.write(f"\n\nTotal: {len(wrong_translations)} incorrect fuzzy translations found.\n")
        f.write("\nThese will be automatically fixed when you run:\n")
        f.write("  py scripts/extract_update_translations.py\n")

    logger.info("Found %d fuzzy entries with incorrect English translations.", len(wrong_translations))
    logger.info("Report saved to: %s", output_file.relative_to(backoffice_dir))
    logger.info("These will be automatically fixed when you run:")
    logger.info("  py scripts/extract_update_translations.py")

    # Also show first 20 to console
    logger.info("\n\nFirst 20 examples:")
    logger.info("=" * 80)
    for i, (msgid, msgstr) in enumerate(sorted(wrong_translations)[:20], 1):
        logger.info("\n%d. %s...", i, msgid[:60])
        logger.info("   Current: %s...", msgstr[:60])

if __name__ == "__main__":
    main()
