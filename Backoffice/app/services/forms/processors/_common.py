"""Shared utilities for form data processors."""
import base64

from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


def get_english_field_name(form_item):
    """Get the English field name for fallback storage in activity logging."""
    return form_item.label


class MatrixJsonDecodeError(Exception):
    """A ``b64:``-prefixed field value could not be base64/UTF-8 decoded.

    Callers MUST NOT treat this the same as "no data submitted" — silently
    coercing it to an empty value would overwrite previously-saved data with
    nothing. The most likely cause is a client/server version mismatch (e.g. a
    browser tab holding new JS that emits ``b64:`` while mid-rollout the
    request lands on an app instance still running the old decoder), so the
    save must fail loudly instead of quietly wiping data. See the "field-level
    b64:" section of ``waf-403-form-payload-refactor-guide.md``.
    """


def decode_b64_matrix_json(value: str) -> str:
    """Decode a base64-encoded JSON field value posted by the browser.

    The JS serialisers (matrix cells, plugin fields) prefix encoded payloads
    with ``b64:`` so the WAF does not inspect the raw JSON content (keys like
    ``4_Total Funding`` and numeric values trigger OWASP 942-* SQL-injection
    rules). Values without the prefix are returned unchanged for backwards
    compatibility with older cached JS / offline draft resubmits.

    Raises:
        MatrixJsonDecodeError: if the value has the ``b64:`` prefix but cannot
            be decoded. Callers must let this propagate to their existing
            per-field error handling (which reports a validation error and
            returns *before* touching the stored value) rather than catching
            it and continuing — see class docstring.
    """
    if value and value.startswith('b64:'):
        try:
            return base64.b64decode(value[4:]).decode('utf-8')
        except Exception as exc:
            raise MatrixJsonDecodeError(f'Failed to base64-decode field value: {exc}') from exc
    return value
