import os
import logging
from flask import current_app
from contextlib import suppress

logger = logging.getLogger(__name__)


def _translations_dir() -> str:
    """Absolute path to the translations directory (same tree Flask-Babel uses)."""
    configured = current_app.config.get("BACKOFFICE_TRANSLATIONS_DIR")
    if configured and os.path.isdir(configured):
        return configured
    return os.path.abspath(os.path.join(current_app.root_path, "..", "translations"))


def _translations_po_path(lang_code: str) -> str:
    import re as _re
    # Sanitize lang_code to only allow safe language code characters (prevents path traversal)
    safe_code = _re.sub(r'[^a-zA-Z0-9_\-]', '', str(lang_code or ''))[:20]
    if not safe_code:
        safe_code = 'unknown'
    return os.path.join(_translations_dir(), safe_code, "LC_MESSAGES", "messages.po")


def _translations_pot_path() -> str:
    return os.path.join(_translations_dir(), "messages.pot")


def _entry_to_display_msgstr(entry) -> str:
    try:
        if getattr(entry, "msgstr", None):
            return entry.msgstr or ""
        plural = getattr(entry, "msgstr_plural", None)
        if plural:
            if isinstance(plural, dict) and plural:
                if plural.get(0):
                    return plural.get(0) or ""
                return next(iter(plural.values()), "") or ""
    except Exception as e:
        logger.debug("plural extraction failed: %s", e)
    return ""


def _extract_page_name(source_path):
    """Return a concise page name from a PO source reference.

    Examples of inputs:
    - "app/templates/admin/api_management.html:100"
    - "app/routes/admin/utilities.py:716"

    Output should be only the base name without extension or line numbers.
    """
    if not source_path:
        return "Unknown"

    first_ref = str(source_path).strip().split()[0]
    last_segment = first_ref.replace('\\', '/').split('/')[-1]
    file_with_no_line = last_segment.split(':', 1)[0]

    if '.' in file_with_no_line:
        base_name = file_with_no_line.rsplit('.', 1)[0]
    else:
        base_name = file_with_no_line

    return base_name or "Unknown"
