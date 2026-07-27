"""Centralized PO/MO persistence: lock → save → compile → notify workers."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from app.utils.po_lock import po_file_lock, touch_translation_sentinel

logger = logging.getLogger(__name__)


def compile_po_to_mo(po_path: str) -> bool:
    """Compile a single messages.po → messages.mo under lock."""
    try:
        import polib  # type: ignore
    except ImportError:
        logger.warning("polib not available; cannot compile %s", po_path)
        return False

    if not os.path.exists(po_path):
        return False

    mo_path = po_path.replace(".po", ".mo")
    try:
        with po_file_lock(po_path):
            polib.pofile(po_path).save_as_mofile(mo_path)
        return True
    except Exception as exc:
        logger.error("Failed to compile %s: %s", po_path, exc)
        return False


def compile_locales(locales: list[str]) -> list[str]:
    """Compile MO files for *locales*. Returns locales successfully compiled."""
    from app.routes.admin.utilities.helpers import _translations_po_path

    compiled: list[str] = []
    for locale in locales:
        po_path = _translations_po_path(locale)
        if compile_po_to_mo(po_path):
            compiled.append(locale)
    return compiled


def finalize_translation_writes(
    locales: list[str] | None = None,
    *,
    refresh: bool = True,
) -> None:
    """Compile MO for affected locales, refresh Babel on this worker, notify peers.

    Call once after any batch of PO mutations (imports, grid edits, auto-translate).
    """
    if locales:
        compile_locales(list(dict.fromkeys(locales)))

    if refresh:
        try:
            from flask_babel import refresh

            refresh()
        except Exception as exc:
            logger.warning("flask_babel.refresh failed: %s", exc)

    try:
        from app.routes.admin.utilities.helpers import _translations_dir

        touch_translation_sentinel(_translations_dir())
    except Exception as exc:
        logger.debug("touch_translation_sentinel failed: %s", exc)


def save_po_locked(po_path: str, mutator: Callable[[Any], bool]) -> bool:
    """Load PO under lock, call *mutator(po)* → bool (changed?), save if True."""
    try:
        import polib  # type: ignore
    except ImportError:
        return False

    if not os.path.exists(po_path):
        return False

    try:
        with po_file_lock(po_path):
            po = polib.pofile(po_path)
            if mutator(po):
                po.save(po_path)
                return True
    except Exception as exc:
        logger.error("save_po_locked failed for %s: %s", po_path, exc)
    return False
