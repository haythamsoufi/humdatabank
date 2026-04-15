"""
AI token utilities (JWT) for Website/Mobile clients.

Design goals:
- Support both cookie-session auth (Backoffice web) and Bearer token auth (Website/Mobile).
- Keep tokens short-lived and derivable from server-side user record (RBAC enforced server-side).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import jwt
from flask import current_app

from app.utils.datetime_helpers import utcnow


# Default to a shorter TTL; can be overridden by AI_TOKEN_TTL_MINUTES in config/env.
DEFAULT_AI_TOKEN_TTL_MINUTES = 120  # 2 hours
AI_TOKEN_AUDIENCE = "hum-databank-ai"
AI_TOKEN_ISSUER = "hum-databank-backoffice"
AI_TOKEN_ALGORITHM = "HS256"
AI_TOKEN_VERSION = 1


@dataclass(frozen=True)
class AITokenClaims:
    user_id: int
    role: str
    exp: int
    iat: int
    aud: str = AI_TOKEN_AUDIENCE
    iss: str = AI_TOKEN_ISSUER
    ver: int = AI_TOKEN_VERSION


def _jwt_secret() -> str:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY is required for AI token signing")
    return secret


def issue_ai_token(*, user_id: int, role: str, ttl_minutes: Optional[int] = None) -> str:
    ttl = int(ttl_minutes or current_app.config.get("AI_TOKEN_TTL_MINUTES", DEFAULT_AI_TOKEN_TTL_MINUTES))
    now = utcnow()
    exp = now + timedelta(minutes=ttl)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "aud": AI_TOKEN_AUDIENCE,
        "iss": AI_TOKEN_ISSUER,
        "ver": AI_TOKEN_VERSION,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=AI_TOKEN_ALGORITHM)


def decode_ai_token(token: str) -> AITokenClaims:
    payload = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[AI_TOKEN_ALGORITHM],
        audience=AI_TOKEN_AUDIENCE,
        issuer=AI_TOKEN_ISSUER,
        options={"require": ["exp", "iat", "sub"]},
    )

    return AITokenClaims(
        user_id=int(payload["sub"]),
        role=str(payload.get("role", "user")),
        exp=int(payload["exp"]),
        iat=int(payload["iat"]),
        aud=str(payload.get("aud", AI_TOKEN_AUDIENCE)),
        iss=str(payload.get("iss", AI_TOKEN_ISSUER)),
        ver=int(payload.get("ver", AI_TOKEN_VERSION)),
    )
