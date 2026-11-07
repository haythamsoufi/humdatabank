"""Optional encryption at rest for secret-looking values in plugin configuration.

Enabled by setting ``PLUGIN_SECRETS_KEY`` (a Fernet key, or any passphrase which is hashed into
one). Without it nothing changes. Values are stored as ``enc:v1:<token>``; plaintext values keep
reading fine, so turning the key on migrates gradually as settings are saved. Losing or changing
the key makes encrypted values unreadable (they are returned as stored and an error is logged).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import logging
import re
from typing import Any, Optional

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
REDACTED_PLACEHOLDER = "********"

SECRET_KEY_NAME_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key)", re.IGNORECASE
)


def is_secret_key(name: Any) -> bool:
    return isinstance(name, str) and bool(SECRET_KEY_NAME_RE.search(name))


def _fernet():
    if not has_app_context():
        return None
    raw = current_app.config.get("PLUGIN_SECRETS_KEY")
    if not raw:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error("PLUGIN_SECRETS_KEY is set but the 'cryptography' package is not installed")
        return None
    raw_bytes = str(raw).encode("utf-8")
    try:
        return Fernet(raw_bytes)
    except Exception:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw_bytes).digest()))


def encryption_enabled() -> bool:
    return _fernet() is not None


def _walk(node: Any, transform) -> Any:
    if isinstance(node, dict):
        return {
            key: (transform(value) if is_secret_key(key) and isinstance(value, str) else _walk(value, transform))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_walk(item, transform) for item in node]
    return node


def encrypt_secrets(data: Any) -> Any:
    """Copy of ``data`` with secret-looking string values encrypted (no-op without a key)."""
    fernet = _fernet()
    if fernet is None:
        return copy.deepcopy(data)

    def encrypt(value: str) -> str:
        if not value or value == REDACTED_PLACEHOLDER or value.startswith(PREFIX):
            return value
        return PREFIX + fernet.encrypt(value.encode("utf-8")).decode("ascii")

    return _walk(data, encrypt)


def decrypt_secrets(data: Any) -> Any:
    """Copy of ``data`` with encrypted values decrypted. Unreadable values are left as stored."""
    if not _contains_encrypted(data):
        return data
    fernet = _fernet()
    if fernet is None:
        logger.error("Plugin config holds encrypted values but PLUGIN_SECRETS_KEY is not usable")
        return data

    def decrypt(value: str) -> str:
        if not value.startswith(PREFIX):
            return value
        try:
            return fernet.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
        except Exception:
            logger.error("Could not decrypt a plugin config value; was PLUGIN_SECRETS_KEY changed?")
            return value

    return _walk(data, decrypt)


def _contains_encrypted(node: Any) -> bool:
    if isinstance(node, dict):
        return any(_contains_encrypted(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_encrypted(v) for v in node)
    return isinstance(node, str) and node.startswith(PREFIX)
