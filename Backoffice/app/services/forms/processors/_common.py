"""Shared utilities for form data processors."""
import base64

from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


def get_english_field_name(form_item):
    """Get the English field name for fallback storage in activity logging."""
    return form_item.label


def decode_b64_matrix_json(value: str) -> str:
    """Decode a base64-encoded matrix JSON field value posted by the browser.

    The JS serialiser prefixes encoded payloads with ``b64:`` so the WAF does
    not inspect the raw JSON content (keys like ``4_Total Funding`` and numeric
    values trigger OWASP 942-* SQL-injection rules).  Values without the prefix
    are returned unchanged for backwards compatibility.
    """
    if value and value.startswith('b64:'):
        try:
            return base64.b64decode(value[4:]).decode('utf-8')
        except Exception:
            logger.warning('Failed to base64-decode matrix field value; treating as empty.')
            return ''
    return value
