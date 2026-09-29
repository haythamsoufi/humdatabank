"""
Shared redaction policy for anything that is logged or persisted from request data.

One policy, three entry points:

* :func:`is_sensitive_key` - decides whether a field/header/query-parameter *name* is sensitive.
* :func:`redact_sensitive` - recursive, size-bounded redaction of dicts/lists/scalars.
* :func:`redact_payload_for_storage` - :func:`redact_sensitive` plus a hard cap on the
  serialized size, for JSON columns such as ``APIUsage.request_data``.

Key matching is separator- and case-insensitive, so ``newPassword``, ``new_password``,
``NEW-PASSWORD`` and ``X-Api-Key`` are all recognised. Value scanning additionally masks
bearer tokens, JWTs and credentials embedded in URLs inside free-text strings.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REDACTED = "***REDACTED***"
_MASK = "***MASKED***"

# Matched against the lowercased key with every non-alphanumeric character removed,
# so "api_key", "apiKey" and "X-Api-Key" all normalise to something containing "apikey".
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "apikey",
    "accesskey",
    "authorization",
    "cookie",
    "csrf",
    "xsrf",
    "credential",
    "privatekey",
    "signingkey",
    "creditcard",
    "cardnumber",
    "cvv",
    "socialsecurity",
    "recoverycode",
    "sessionid",
    "sessionkey",
    "connectionstring",
)

# Short words that only count when they are a whole word of the key ("otp_code", "userSSN"),
# otherwise substrings such as "footprint" or "business_name" ("...ssn...") would be dropped.
_SENSITIVE_WORDS: frozenset[str] = frozenset({"otp", "ssn", "pwd", "jwt", "bearer"})

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_STRING_LENGTH = 500
DEFAULT_MAX_ITEMS = 100
DEFAULT_MAX_STORED_BYTES = 8 * 1024


def is_sensitive_key(key: Any) -> bool:
    """True if a field, header or query-parameter name should never be logged or stored."""
    if key is None:
        return False
    raw = str(key)
    if not raw:
        return False
    words = [w for w in _NON_ALNUM.split(_CAMEL_BOUNDARY.sub("_", raw).lower()) if w]
    if any(w in _SENSITIVE_WORDS for w in words):
        return True
    collapsed = "".join(words)
    return any(s in collapsed for s in _SENSITIVE_SUBSTRINGS)


_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")
_URL_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_KV_RE = re.compile(
    r"(?i)((?:pass(?:word|wd)|api[_-]?key|(?:access|refresh|id|auth|csrf|secret)[_-]?(?:token|key)|token|secret)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s&\"'<>,;}]+)"
)
_SESSION_COOKIE_RE = re.compile(r"(?i)(\bsession\s*=\s*)([^;,\s]+)")


def sanitize_for_logging(value: Any, max_length: int = 200) -> str:
    """Stringify ``value`` for a log line, masking credentials and truncating."""
    if value is None:
        return "None"

    text = str(value)
    text = _KV_RE.sub(rf"\1{_MASK}", text)
    text = _SESSION_COOKIE_RE.sub(rf"\1{_MASK}", text)
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)} {_MASK}", text)
    text = _JWT_RE.sub(_MASK, text)
    text = _URL_USERINFO_RE.sub(rf"\1{_MASK}@", text)

    if len(text) > max_length:
        text = f"{text[:max_length]}... [TRUNCATED {len(text) - max_length} chars]"
    return text


def redact_sensitive(
    value: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    max_items: int = DEFAULT_MAX_ITEMS,
    _depth: int = 0,
) -> Any:
    """
    Return a JSON-safe copy of ``value`` with sensitive data removed.

    * Mapping entries whose key satisfies :func:`is_sensitive_key` become ``"***REDACTED***"``
      regardless of nesting depth or value type.
    * Lists/tuples/sets and mappings are recursed into; collections longer than ``max_items``
      are cut and marked, and nesting deeper than ``max_depth`` is replaced by a marker.
    * Strings are scanned for bearer tokens/JWTs/inline credentials and truncated.
    * The input is never mutated.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str):
        return sanitize_for_logging(value, max_length=max_string_length)
    if _depth >= max_depth:
        return "<max depth exceeded>"

    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["_truncated_items"] = len(value) - max_items
                break
            str_key = str(key)
            if is_sensitive_key(str_key):
                out[str_key] = REDACTED
            else:
                out[str_key] = redact_sensitive(
                    item,
                    max_depth=max_depth,
                    max_string_length=max_string_length,
                    max_items=max_items,
                    _depth=_depth + 1,
                )
        return out

    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        redacted = [
            redact_sensitive(
                item,
                max_depth=max_depth,
                max_string_length=max_string_length,
                max_items=max_items,
                _depth=_depth + 1,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            redacted.append(f"<{len(items) - max_items} more items>")
        return redacted

    return sanitize_for_logging(value, max_length=max_string_length)


def redact_payload_for_storage(
    payload: Any,
    *,
    max_bytes: int = DEFAULT_MAX_STORED_BYTES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> Optional[Any]:
    """
    Redact ``payload`` and guarantee the serialized result fits in ``max_bytes``.

    Oversized payloads are replaced by a values-free summary (top-level key names and the
    original size) so persisted rows stay small and cannot leak bulk data.
    Returns ``None`` for empty payloads so JSON columns store SQL NULL.
    """
    if payload is None or payload == {} or payload == []:
        return None

    redacted = redact_sensitive(
        payload,
        max_depth=max_depth,
        max_string_length=max_string_length,
        max_items=max_items,
    )
    try:
        size = len(json.dumps(redacted, default=str, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return {"_truncated": True, "_reason": "unserializable"}
    if size <= max_bytes:
        return redacted

    summary: Dict[str, Any] = {"_truncated": True, "_size_bytes": size}
    if isinstance(redacted, dict):
        summary["keys"] = [str(k) for k in list(redacted.keys())[:50]]
    return summary


def redact_url(url: Optional[str]) -> Optional[str]:
    """Drop URL userinfo and mask the values of sensitive query parameters."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return sanitize_for_logging(url, max_length=2000)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    query = _redact_query(parts.query)
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def _redact_query(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    return "&".join(f"{k}={_MASK if is_sensitive_key(k) else v}" for k, v in pairs)


_QUERY_PARAM_RE = re.compile(r"([?&])([^=&\s\"#]+)=([^&\s\"#]*)")


def redact_query_params_in_text(text: str) -> str:
    """Mask sensitive query-parameter values inside an arbitrary log line (e.g. an access-log request line)."""
    if not text or "=" not in text:
        return text

    def _mask(match: "re.Match[str]") -> str:
        name = match.group(2)
        if is_sensitive_key(name):
            return f"{match.group(1)}{name}={_MASK}"
        return match.group(0)

    return _QUERY_PARAM_RE.sub(_mask, text)


def sanitize_headers_for_logging(headers: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> Dict[str, Any]:
    """Header mapping safe to log: sensitive header values are masked, the rest truncated."""
    items = headers.items() if isinstance(headers, Mapping) else headers
    return {
        str(name): REDACTED if is_sensitive_key(name) else sanitize_for_logging(value, max_length=200)
        for name, value in items
    }


def sanitize_dict_for_logging(data: Dict[str, Any], sensitive_keys: Optional[list] = None) -> Dict[str, Any]:
    """
    Sanitize a dictionary for safe logging.

    Kept for existing callers. With no ``sensitive_keys`` it applies the shared policy
    (:func:`redact_sensitive`); an explicit list keeps the legacy substring semantics.
    """
    if sensitive_keys is None:
        result = redact_sensitive(data)
        return result if isinstance(result, dict) else {}

    sanitized: Dict[str, Any] = {}
    for key, value in data.items():
        key_lower = str(key).lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = _MASK
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_for_logging(value, sensitive_keys)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [
                sanitize_dict_for_logging(item, sensitive_keys) if isinstance(item, dict)
                else sanitize_for_logging(item)
                for item in value
            ]
        else:
            sanitized[key] = sanitize_for_logging(value)
    return sanitized
