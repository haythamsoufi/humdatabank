"""Single-use authorization codes for the mobile Azure sign-in hand-off.

The app opens ``/login/azure`` in a browser tab with a PKCE ``code_challenge``. After the
Azure round trip the server redirects to ``humdatabank://oauth-success?code=...`` (a short
opaque value, valid once, ~60 s). The app then POSTs the code plus its ``code_verifier`` to
``/api/mobile/v1/auth/oauth/exchange`` and receives the JWT pair in the response body.
JWTs therefore never appear in a URL, browser history, or an intercepted deep link, and an
intercepted code is useless without the verifier that never left the device.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from typing import Optional

from flask import current_app

from app.utils.auth_state import (
    NS_OAUTH_CODE,
    decode_value,
    encode_value,
    get_auth_state,
)

_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


def is_valid_code_challenge(value: Optional[str]) -> bool:
    """RFC 7636 S256 challenge: unpadded base64url of a SHA-256 digest (43 chars)."""
    return bool(value) and bool(_CHALLENGE_RE.match(value or ""))


def _challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _store_key(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_oauth_code(user_id: int, session_id: Optional[str], code_challenge: str) -> str:
    """Store a one-time code bound to the user, session and PKCE challenge.

    Raises ``AuthStateUnavailable`` when shared storage is down.
    """
    code = secrets.token_urlsafe(32)
    ttl = int(current_app.config.get("MOBILE_OAUTH_CODE_TTL_SECONDS", 60))
    get_auth_state().put(
        NS_OAUTH_CODE,
        _store_key(code),
        encode_value({"uid": int(user_id), "sid": session_id, "cc": code_challenge}),
        max(1, ttl),
    )
    return code


def redeem_oauth_code(code: str, code_verifier: str) -> Optional[dict]:
    """Consume ``code`` and return ``{"user_id", "session_id"}`` when the verifier matches.

    The code is deleted on first presentation whether or not the verifier matches, so a
    guessed verifier cannot be retried against the same code. ``None`` means "reject".
    Raises ``AuthStateUnavailable`` when shared storage is down.
    """
    if not code or not code_verifier or not _VERIFIER_RE.match(code_verifier):
        if code:
            get_auth_state().delete(NS_OAUTH_CODE, _store_key(code))
        return None
    record = decode_value(get_auth_state().pop(NS_OAUTH_CODE, _store_key(code)))
    if not isinstance(record, dict):
        return None
    if not hmac.compare_digest(str(record.get("cc") or ""), _challenge_for(code_verifier)):
        return None
    return {"user_id": int(record["uid"]), "session_id": record.get("sid")}
