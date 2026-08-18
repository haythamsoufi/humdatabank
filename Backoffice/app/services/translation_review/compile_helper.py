"""Compile gettext catalogs and refresh Flask-Babel caches."""

from __future__ import annotations

import logging
import os

from flask import current_app

from app.utils.po_lock import po_file_lock

logger = logging.getLogger(__name__)


def compile_locale_catalog(locale: str) -> bool:
    """Compile messages.po -> messages.mo for a single locale."""
    try:
        import polib  # type: ignore
    except ImportError:
        logger.warning('polib not available; cannot compile translations for %s', locale)
        return False

    from app.routes.admin.utilities.helpers import _translations_po_path

    po_path = _translations_po_path(locale)
    if not os.path.exists(po_path):
        logger.warning('PO file not found for locale %s: %s', locale, po_path)
        return False

    mo_path = po_path.replace('.po', '.mo')
    try:
        with po_file_lock(po_path):
            polib.pofile(po_path).save_as_mofile(mo_path)
        return True
    except Exception as exc:
        logger.error('Failed to compile translations for %s: %s', locale, exc)
        return False


def compile_and_refresh_locale(locale: str) -> bool:
    """Compile a locale catalog and refresh Flask-Babel in the current process."""
    from app.utils.po_persistence import finalize_translation_writes

    if not compile_locale_catalog(locale):
        return False
    finalize_translation_writes([locale], refresh=True)
    return True
