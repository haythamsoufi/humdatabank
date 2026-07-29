#!/usr/bin/env python3
"""
Simple script to compile PO files to MO files for Flask-Babel
"""

import logging
import os

from pathlib import Path

logger = logging.getLogger(__name__)
try:
    import polib  # type: ignore
except Exception as e:
    logger.debug("polib import failed: %s", e)
    raise SystemExit("polib is not installed. Run: py -m pip install -r Backoffice/requirements.txt")

BACKOFFICE_DIR = Path(__file__).resolve().parents[2]

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
    translations_dir = BACKOFFICE_DIR / "translations"
    try:
        locales = sorted(
            name for name in os.listdir(translations_dir)
            if (translations_dir / name).is_dir()
        )
    except Exception as e:
        logger.error("Could not list translations dir %s: %s", translations_dir, e)
        raise SystemExit(1)

    for lang in locales:
        po_file = translations_dir / lang / "LC_MESSAGES" / "messages.po"
        mo_file = translations_dir / lang / "LC_MESSAGES" / "messages.mo"

        if po_file.is_file():
            compile_po_to_mo(str(po_file), str(mo_file))
        else:
            logger.warning("PO file not found: %s", po_file)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
