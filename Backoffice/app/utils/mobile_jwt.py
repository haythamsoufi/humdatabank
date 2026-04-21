"""
Mobile JWT utilities -- access and refresh tokens for the Flutter app.

Design:
- Access tokens are short-lived (configurable, default 30 min).
- Refresh tokens are longer-lived (configurable, default 30 days).
- Both are HS256-signed with the application SECRET_KEY.
- Refresh tokens include a ``jti`` (JWT ID) for one-time-use rotation.
  When a refresh token is used, the caller should blacklist its ``jti``
  via ``blacklist_refresh_jti`` and issue a new pair.
- The ``mobile_auth_required`` decorator will accept either a session cookie or
  a valid ``Authorization: Bearer <access_token>`` JWT, so mobile can migrate
  from cookies to tokens gradually.
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Set

import jwt
from flask import current_app

from app.utils.datetime_helpers import utcnow

# In-memory set of consumed refresh token JTIs.
# Prevents replay of previously used refresh tokens (rotation enforcement).
_used_refresh_jtis: Set[str] = set()
_used_refresh_jtis_lock = threading.Lock()
_MAX_USED_JTIS = 50_000  # cap to prevent unbounded memory growth


def blacklist_refresh_jti(jti: str) -> None:
    """Mark a refresh token JTI as consumed so it cannot be replayed."""
    with _used_refresh_jtis_lock:
        if len(_used_refresh_jtis) >= _MAX_USED_JTIS:
            # Evict ~25% of the oldest entries (set is unordered, but pruning
            # a random subset is acceptable — expired JTIs fail decoding anyway).
            to_remove = list(_used_refresh_jtis)[:_MAX_USED_JTIS // 4]
            for item in to_remove:
                _used_refresh_jtis.discard(item)
        _used_refresh_jtis.add(jti)


def is_refresh_jti_used(jti: str) -> bool:
    """Return True if the JTI has already been consumed."""
    with _used_refresh_jtis_lock:
        return jti in _used_refresh_jtis


MOBILE_TOKEN_AUDIENCE = "hum-databank-mobile"
MOBILE_TOKEN_ISSUER = "hum-databank-backoffice"
MOBILE_TOKEN_ALGORITHM = "HS256"
MOBILE_TOKEN_VERSION = 1

DEFAULT_ACCESS_TTL_MINUTES = 30
DEFAULT_REFRESH_TTL_DAYS = 30


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


def _jwt_secret() -> str:
    secret = current_app.config.get("MOBILE_JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("MOBILE_JWT_SECRET or SECRET_KEY is required for mobile JWT signing")
    return secret


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
    return jwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)


def issue_refresh_token(
    user_id: int,
    ttl_days: Optional[int] = None,
    session_id: Optional[str] = None,
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
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl)).timestamp()),
        "aud": MOBILE_TOKEN_AUDIENCE,
        "iss": MOBILE_TOKEN_ISSUER,
        "ver": MOBILE_TOKEN_VERSION,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)


def decode_mobile_token(token: str, *, expected_type: str = "access") -> MobileTokenClaims:
    """
    Decode and validate a mobile JWT.

    Raises ``jwt.InvalidTokenError`` subclasses on any validation failure.
    """
    payload = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[MOBILE_TOKEN_ALGORITHM],
        audience=MOBILE_TOKEN_AUDIENCE,
        issuer=MOBILE_TOKEN_ISSUER,
        options={"require": ["exp", "iat", "sub", "type"]},
    )

    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )

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
    )


def decode_mobile_token_ignoring_expiry(token: str) -> MobileTokenClaims:
    """Decode a mobile JWT without verifying the expiry time.

    Used exclusively for the logout endpoint: we need the ``sid`` claim to
    blacklist the session even when the access token has just expired.
    The token signature (HS256) is still verified so the endpoint cannot
    be abused to blacklist arbitrary sessions with a forged token.
    """
    payload = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[MOBILE_TOKEN_ALGORITHM],
        audience=MOBILE_TOKEN_AUDIENCE,
        issuer=MOBILE_TOKEN_ISSUER,
        options={
            "require": ["exp", "iat", "sub", "type"],
            "verify_exp": False,
        },
    )
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
    )


def issue_token_pair(user_id: int, session_id: Optional[str] = None) -> dict:
    """Issue both access and refresh tokens for a user.

    ``session_id`` is embedded in both tokens as the ``sid`` claim and is used
    by the admin force-logout blacklist so that revoking the session also
    invalidates any outstanding JWTs from that login.
    """
    access_ttl = int(
        current_app.config.get("MOBILE_ACCESS_TOKEN_TTL_MINUTES", DEFAULT_ACCESS_TTL_MINUTES)
    )
    return {
        "access_token": issue_access_token(user_id, session_id=session_id),
        "refresh_token": issue_refresh_token(user_id, session_id=session_id),
        "token_type": "Bearer",
        "expires_in": access_ttl * 60,
    }
