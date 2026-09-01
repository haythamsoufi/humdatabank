"""Shared utilities for form data processors."""
import base64
import re

from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


def get_english_field_name(form_item):
    """Get the English field name for fallback storage in activity logging."""
    return form_item.label


# Sanity bound on chunk count — a value needing more than this many chunks at
# MAX_CHUNK_BYTES-sized pieces (see matrix-field-chunking.js) would already be
# tens of KB and hitting a WAF *total* body/argument-size limit regardless of
# chunking, so there is nothing more to gain from scanning further.
_MAX_CHUNK_LOOKUPS = 256
_CHUNK_FIELD_RE = re.compile(r'__c\d+$')


def is_waf_chunk_field_name(field_name: str) -> bool:
    """True for sibling chunk keys emitted by matrix-field-chunking.js (``…__c1``)."""
    return bool(field_name and _CHUNK_FIELD_RE.search(field_name))


def get_possibly_chunked_form_value(form, field_name: str, default: str = '') -> str:
    """Read a form field's value, transparently reassembling WAF-safe chunks.

    Large matrix JSON values are base64-wrapped (see ``decode_b64_matrix_json``)
    to dodge WAF *content-signature* rules — but base64 inflates size by ~33%,
    which can trip OWASP CRS per-argument length limits (e.g. ``920370``
    "Argument value too long"). ``matrix-field-chunking.js`` splits any such
    value across ``field_name`` plus ``field_name__c1``, ``__c2``, ... This
    reassembles them into the exact original string. Unchunked values are
    returned exactly as ``form.get(field_name)`` would.
    """
    first = form.get(field_name)
    if first is None:
        return default
    parts = [first]
    index = 1
    while index <= _MAX_CHUNK_LOOKUPS:
        chunk = form.get(f'{field_name}__c{index}')
        if chunk is None:
            break
        parts.append(chunk)
        index += 1
    return ''.join(parts) if len(parts) > 1 else first


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


def read_waf_protected_form_value(form, field_name: str, default: str = ''):
    """Reassemble ``__cN`` chunks (if any), then decode a ``b64:`` prefix (if any).

    Missing fields return ``default``. Callers that distinguish "not submitted"
    from "submitted empty" should pass ``default=None``.
    """
    return decode_b64_matrix_json(get_possibly_chunked_form_value(form, field_name, default))
