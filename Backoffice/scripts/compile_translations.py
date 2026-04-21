#!/usr/bin/env python3
"""
Simple script to compile PO files to MO files for Flask-Babel
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)
try:
    import polib  # type: ignore
except Exception as e:
    logger.debug("polib import failed: %s", e)
    raise SystemExit("polib is not installed. Run: py -m pip install -r Backoffice/requirements.txt")

# Ensure Backoffice/ is on sys.path so we can import the config package when
# running this file directly (e.g., py Backoffice/scripts/compile_translations.py)
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
BACKOFFICE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if BACKOFFICE_DIR not in sys.path:
    sys.path.insert(0, BACKOFFICE_DIR)

def compile_po_to_mo(po_file_path, mo_file_path):
    """Compile a PO file to MO file"""
    try:
        # Read the PO file
        po = polib.pofile(po_file_path)

        # Write the MO file
        po.save_as_mofile(mo_file_path)
        logger.info("Successfully compiled %s to %s", po_file_path, mo_file_path)
        return True
    except Exception as e:
        logger.error("Error compiling %s: %s", po_file_path, e)
        return False

def main():
    """Compile all PO files in the translations directory"""
    translations_dir = os.path.abspath(os.path.join(BACKOFFICE_DIR, 'translations'))
    try:
        locales = sorted(
            name for name in os.listdir(translations_dir)
            if os.path.isdir(os.path.join(translations_dir, name))
        )
    except Exception as e:
        logger.error("Could not list translations dir %s: %s", translations_dir, e)
        raise SystemExit(1)

    for lang in locales:
        po_file = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.po')
        mo_file = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.mo')

        if os.path.exists(po_file):
            compile_po_to_mo(po_file, mo_file)
        else:
            logger.warning("PO file not found: %s", po_file)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
