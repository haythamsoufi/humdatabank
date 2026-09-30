"""
Mobile JWT utilities -- access and refresh tokens for the Flutter app.

Design:
- Access tokens are short-lived (configurable, default 30 min).
- Refresh tokens are longer-lived (configurable, default 30 days).
- Both are HS256-signed with ``MOBILE_JWT_SECRET`` (a key separate from ``SECRET_KEY``
  in production/staging; see ``app/utils/security_startup.py``). Verification also
  accepts ``MOBILE_JWT_SECRET_PREVIOUS`` and, during the split transition,
  ``SECRET_KEY`` (``MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY``).
- Refresh tokens are single-use and belong to a *family* (the ``fam`` claim, constant
  across rotations of one login). Consumed ``jti`` values and revoked families live in
  shared storage (``app/utils/auth_state.py``: Redis or the database) so every worker
  agrees. Presenting an already-consumed refresh token revokes the whole family.
- ``mobile_auth_required`` accepts a session cookie or a valid
  ``Authorization: Bearer <access_token>`` JWT.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional

import jwt
from flask import current_app

from app.utils.auth_state import (
    NS_REFRESH_FAMILY_REVOKED,
    NS_REFRESH_JTI_USED,
    NS_SESSION_REVOKED,
    get_auth_state,
)
from app.utils.datetime_helpers import utcnow

MOBILE_TOKEN_AUDIENCE = "hum-databank-mobile"
MOBILE_TOKEN_ISSUER = "hum-databank-backoffice"
MOBILE_TOKEN_ALGORITHM = "HS256"
MOBILE_TOKEN_VERSION = 1

DEFAULT_ACCESS_TTL_MINUTES = 30
DEFAULT_REFRESH_TTL_DAYS = 30
_MARKER_TTL_GRACE_SECONDS = 300


@dataclass(frozen=True)
class MobileTokenClaims:
    user_id: int
    token_type: str   # "access" or "refresh"
    exp: int
    iat: int
    aud: str = MOBILE_TOKEN_AUDIENCE
    iss: str = MOBILE_TOKEN_ISSUER
    ver: int = MOBILE_TOKEN_VERSION
    sid: Optional[str] = None   # session ID — used for admin force-logout blacklisting
    jti: Optional[str] = None   # JWT ID — used for refresh token one-time-use rotation
    fam: Optional[str] = None   # refresh-token family — constant across rotations of one login

    @property
    def family_id(self) -> Optional[str]:
        return self.fam or self.sid


def _signing_secret() -> str:
    secret = current_app.config.get("MOBILE_JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("MOBILE_JWT_SECRET or SECRET_KEY is required for mobile JWT signing")
    return secret


def _jwt_secret() -> str:
    return _signing_secret()


def _verification_secrets() -> List[str]:
    """Signing key first, then verify-only keys (rotation + legacy SECRET_KEY transition)."""
    signing = _signing_secret()
    keys = [signing]
    for previous in current_app.config.get("MOBILE_JWT_SECRET_PREVIOUS") or []:
        if previous and previous not in keys:
            keys.append(previous)
    legacy = current_app.config.get("SECRET_KEY")
    if legacy and legacy not in keys and current_app.config.get("MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY", True):
        keys.append(legacy)
    return keys


def _decode(token: str, *, verify_exp: bool = True) -> dict:
    options = {"require": ["exp", "iat", "sub", "type"]}
    if not verify_exp:
        options["verify_exp"] = False
    last_error: Optional[Exception] = None
    for index, secret in enumerate(_verification_secrets()):
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[MOBILE_TOKEN_ALGORITHM],
                audience=MOBILE_TOKEN_AUDIENCE,
                issuer=MOBILE_TOKEN_ISSUER,
                options=options,
            )
        except jwt.InvalidSignatureError as exc:
            last_error = exc
            continue
        if index > 0:
            current_app.logger.info("Mobile JWT verified with a non-primary (rotation/legacy) key")
        return payload
    raise last_error or jwt.InvalidTokenError("Invalid mobile token")


def _claims_from_payload(payload: dict) -> MobileTokenClaims:
    return MobileTokenClaims(
        user_id=int(payload["sub"]),
        token_type=payload["type"],
        exp=int(payload["exp"]),
        iat=int(payload["iat"]),
        aud=payload.get("aud", MOBILE_TOKEN_AUDIENCE),
        iss=payload.get("iss", MOBILE_TOKEN_ISSUER),
        ver=int(payload.get("ver", 1)),
        sid=payload.get("sid"),
        jti=payload.get("jti"),
        fam=payload.get("fam"),
    )


def issue_access_token(
    user_id: int,
    ttl_minutes: Optional[int] = None,
    session_id: Optional[str] = None,
) -> str:
    ttl = int(
        ttl_minutes
        or current_app.config.get("MOBILE_ACCESS_TOKEN_TTL_MINUTES", DEFAULT_ACCESS_TTL_MINUTES)
    )
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "aud": MOBILE_TOKEN_AUDIENCE,
        "iss": MOBILE_TOKEN_ISSUER,
        "ver": MOBILE_TOKEN_VERSION,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, _signing_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)


def issue_refresh_token(
    user_id: int,
    ttl_days: Optional[int] = None,
    session_id: Optional[str] = None,
    family_id: Optional[str] = None,
) -> str:
    ttl = int(
        ttl_days
        or current_app.config.get("MOBILE_REFRESH_TOKEN_TTL_DAYS", DEFAULT_REFRESH_TTL_DAYS)
    )
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_urlsafe(24),
        "fam": family_id or session_id or secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl)).timestamp()),
        "aud": MOBILE_TOKEN_AUDIENCE,
        "iss": MOBILE_TOKEN_ISSUER,
        "ver": MOBILE_TOKEN_VERSION,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, _signing_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)


def decode_mobile_token(token: str, *, expected_type: str = "access") -> MobileTokenClaims:
    """
    Decode and validate a mobile JWT.

    Raises ``jwt.InvalidTokenError`` subclasses on any validation failure.
    """
    payload = _decode(token)
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )
    return _claims_from_payload(payload)


def decode_mobile_token_ignoring_expiry(token: str) -> MobileTokenClaims:
    """Decode a mobile JWT without verifying the expiry time.

    Used exclusively for the logout endpoint: we need the ``sid`` claim to
    blacklist the session even when the access token has just expired.
    The token signature (HS256) is still verified so the endpoint cannot
    be abused to blacklist arbitrary sessions with a forged token.
    """
    return _claims_from_payload(_decode(token, verify_exp=False))


def issue_token_pair(
    user_id: int,
    session_id: Optional[str] = None,
    family_id: Optional[str] = None,
) -> dict:
    """Issue both access and refresh tokens for a user.

    ``session_id`` is embedded in both tokens as the ``sid`` claim and is used
    by the admin force-logout blacklist so that revoking the session also
    invalidates any outstanding JWTs from that login. ``family_id`` links the
    refresh token to its rotation chain (new login: omitted, defaults to the sid).
    """
    access_ttl = int(
        current_app.config.get("MOBILE_ACCESS_TOKEN_TTL_MINUTES", DEFAULT_ACCESS_TTL_MINUTES)
    )
    return {
        "access_token": issue_access_token(user_id, session_id=session_id),
        "refresh_token": issue_refresh_token(user_id, session_id=session_id, family_id=family_id),
        "token_type": "Bearer",
        "expires_in": access_ttl * 60,
    }


def _refresh_ttl_seconds() -> int:
    days = int(current_app.config.get("MOBILE_REFRESH_TOKEN_TTL_DAYS", DEFAULT_REFRESH_TTL_DAYS))
    return days * 86400 + _MARKER_TTL_GRACE_SECONDS


def _marker_ttl_for(claims: MobileTokenClaims) -> int:
    remaining = int(claims.exp - utcnow().timestamp())
    return max(remaining, 0) + _MARKER_TTL_GRACE_SECONDS


def consume_refresh_token(claims: MobileTokenClaims) -> bool:
    """Atomically mark a refresh token as used. True only for the first presentation.

    Raises ``AuthStateUnavailable`` when shared storage is down (caller must deny).
    """
    if not claims.jti:
        return False
    return get_auth_state().add_once(
        NS_REFRESH_JTI_USED, claims.jti, _marker_ttl_for(claims), value=claims.family_id or "",
    )


def blacklist_refresh_jti(jti: str) -> None:
    """Mark a refresh token JTI as consumed (kept for callers that consume outside a claim)."""
    get_auth_state().add_once(NS_REFRESH_JTI_USED, jti, _refresh_ttl_seconds())


def is_refresh_jti_used(jti: str) -> bool:
    """Return True if the JTI has already been consumed."""
    return get_auth_state().exists(NS_REFRESH_JTI_USED, jti)


def revoke_token_family(family_id: Optional[str]) -> None:
    """Reject every refresh token in ``family_id`` (e.g. after reuse is detected)."""
    if family_id:
        get_auth_state().put(NS_REFRESH_FAMILY_REVOKED, family_id, "1", _refresh_ttl_seconds())


def is_token_family_revoked(family_id: Optional[str]) -> bool:
    return bool(family_id) and get_auth_state().exists(NS_REFRESH_FAMILY_REVOKED, family_id)


def revoke_session_id(session_id: Optional[str]) -> None:
    """Record a revoked login/session id in shared storage (visible to all workers)."""
    if session_id:
        ttl = max(
            _refresh_ttl_seconds(),
            int(current_app.permanent_session_lifetime.total_seconds()) + _MARKER_TTL_GRACE_SECONDS,
        )
        get_auth_state().put(NS_SESSION_REVOKED, session_id, "1", ttl)


def is_session_id_revoked(session_id: Optional[str]) -> bool:
    return bool(session_id) and get_auth_state().exists(NS_SESSION_REVOKED, session_id)
