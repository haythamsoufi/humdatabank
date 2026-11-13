"""Shared primitives for values that end up in email headers or the address envelope.

Every value that is user-influenced (subject built from a template/entity name,
recipient addresses from user records or forms, attachment file names) must pass
through these helpers before it reaches ``services.email.client``. The outbound
gateway builds MIME headers from these fields, so a CR/LF (or a comma inside an
address, since recipients are joined into a comma-separated list) would allow
header injection or silent addition of recipients.
"""

from __future__ import annotations

import re
import unicodedata
from email.utils import parseaddr
from typing import Iterable, List, Optional, Tuple

MAX_HEADER_VALUE_LENGTH = 998
MAX_SUBJECT_LENGTH = 300
MAX_ADDRESS_LENGTH = 254
MAX_FILENAME_LENGTH = 200

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_WHITESPACE_RUN_RE = re.compile(r"[ \t]+")

_ADDR_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_ADDR_DOMAIN_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def sanitize_header_value(value: object, max_length: int = MAX_HEADER_VALUE_LENGTH) -> str:
    """Return ``value`` as a single-line header-safe string.

    CR, LF, NUL, other C0/C1 control characters and Unicode line/paragraph
    separators are replaced by a space (never dropped silently, so ``a\\r\\nb``
    does not become ``ab``), runs of spaces collapse, and the result is trimmed
    and truncated to ``max_length``.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL_CHARS_RE.sub(" ", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip()
    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def sanitize_subject(value: object) -> str:
    return sanitize_header_value(value, MAX_SUBJECT_LENGTH)


def sanitize_filename(value: object, default: str = "attachment") -> str:
    """Header-safe attachment file name without path components."""
    cleaned = sanitize_header_value(value, MAX_FILENAME_LENGTH)
    cleaned = cleaned.replace("\\", "/").rsplit("/", 1)[-1].replace('"', "'").strip()
    return cleaned or default


def _is_valid_domain(domain: str) -> bool:
    if not domain or len(domain) > 253 or domain.endswith("."):
        return False
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_domain.split(".")
    if len(labels) < 2:
        return False
    return all(_ADDR_DOMAIN_LABEL_RE.match(label) for label in labels)


def validate_email_address(value: object) -> Optional[str]:
    """Return the bare ``local@domain`` address, or ``None`` if ``value`` is not a plain address.

    Display names, comments, angle brackets, whitespace, commas, semicolons and
    control characters are all rejected: recipients are joined into
    comma-separated envelope fields, so anything richer than a bare address is
    an injection vector.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or len(raw) > MAX_ADDRESS_LENGTH:
        return None
    if _CONTROL_CHARS_RE.search(raw) or any(ch in raw for ch in ' \t<>,;:"()[]\\'):
        return None
    if raw.count("@") != 1:
        return None
    local, domain = raw.split("@", 1)
    if not local or len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    if not _ADDR_LOCAL_RE.match(local) or not _is_valid_domain(domain):
        return None
    return raw


def sanitize_sender(value: object) -> Optional[str]:
    """Validate a From address. ``Name <addr@x.org>`` is allowed; the name is sanitised.

    Returns the normalised sender string or ``None`` when the address part is invalid.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if _CONTROL_CHARS_RE.search(raw):
        return None
    name, addr = parseaddr(raw)
    bare = validate_email_address(addr)
    if not bare:
        return None
    safe_name = sanitize_header_value(name, 200).replace('"', "'").replace("<", "").replace(">", "")
    if not safe_name:
        return bare
    return f'"{safe_name}" <{bare}>'


def filter_valid_addresses(values: Iterable[object]) -> Tuple[List[str], List[str]]:
    """Split ``values`` into (valid bare addresses, rejected raw values as truncated reprs)."""
    valid: List[str] = []
    rejected: List[str] = []
    for item in values or []:
        addr = validate_email_address(item)
        if addr:
            valid.append(addr)
        else:
            rejected.append(repr(str(item)[:80]))
    return valid, rejected
