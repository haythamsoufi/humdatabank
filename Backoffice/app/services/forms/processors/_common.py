"""Shared utilities for form data processors."""
import base64

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


def get_possibly_chunked_form_value(form, field_name: str, default: str = '') -> str:
    """Read a form field's value, transparently reassembling WAF-safe chunks.

    Large matrix (and, in future, other) JSON values are base64-wrapped (see
    ``decode_b64_matrix_json``) to dodge WAF *content-signature* rules
    (``REQUEST-941-*``/``REQUEST-942-*``) — but base64 inflates size by ~33%,
    which can trip a *different* WAF rule family that signature-avoidance
    does nothing for: OWASP CRS's per-argument length limit (e.g. ``920370``
    "Argument value too long", documented example default
    ``tx.arg_length=400``). A real production save payload analyzed
    2026-09-01 contained a single 48-key matrix argument at 1384 bytes
    (b64-wrapped) — see the "Azure App Gateway WAF Rules the App Should
    Respect" section of ``waf-403-form-payload-refactor-guide.md``.

    ``matrix-field-chunking.js`` splits any such value, immediately before
    submission, across ``field_name`` (first chunk) and
    ``field_name__c1``, ``field_name__c2``, ... (remaining chunks), each
    individually well under any plausible per-argument length limit — the
    WAF then sees several small arguments instead of one large one. This
    reassembles them into the exact original string transparently, so
    ``decode_b64_matrix_json`` (and everything downstream of it) sees no
    difference from before chunking existed. Values that were never chunked
    (below the client's threshold, or a native/offline resubmit predating
    this feature) are returned exactly as ``form.get(field_name)`` would.
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
