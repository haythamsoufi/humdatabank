"""
Resolve the effective request user for the AI brain.

Order of precedence:
1) Bearer token (Website/Mobile) via Authorization: Bearer <jwt>, when it is a valid AI token
2) Flask-Login cookie session (Backoffice web)
3) Anonymous (public)

A valid Bearer AI token wins over a cookie. The mobile app sends both (its stored session
cookie plus the AI token); classifying that request as ``cookie`` would subject it to the
browser CSRF check it cannot satisfy. A Bearer header is not an ambient credential, so a
cross-site request cannot forge it and no CSRF token is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from flask import request, current_app
from flask_login import current_user

import logging

from app.models import User
from app.utils.ai_tokens import decode_ai_token

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIRequestIdentity:
    is_authenticated: bool
    access_level: str  # "public" | "user" | "admin" | "system_manager"
    user: Optional[User]
    auth_source: str  # "cookie" | "bearer" | "anonymous"


def _bearer_token() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    if not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None


def _identity_for_user(user: User, auth_source: str) -> AIRequestIdentity:
    from app.services.organization.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        level = "system_manager"
    elif AuthorizationService.is_admin(user):
        level = "admin"
    else:
        level = "user"
    return AIRequestIdentity(
        is_authenticated=True,
        access_level=level,
        user=user,
        auth_source=auth_source,
    )


def bearer_identity_needs_login(identity: AIRequestIdentity) -> bool:
    """True when ``current_user`` must be bound to the Bearer-authenticated user.

    Also true when a different user's cookie session is present on the same request, so
    RBAC helpers that read ``current_user`` act for the user the token belongs to.
    """
    if identity.auth_source != "bearer" or identity.user is None:
        return False
    if not getattr(current_user, "is_authenticated", False):
        return True
    return getattr(current_user, "id", None) != getattr(identity.user, "id", None)


def resolve_ai_identity() -> AIRequestIdentity:
    # 1) Bearer token (Website/Mobile)
    token = _bearer_token()
    if token:
        try:
            claims = decode_ai_token(token)
            user = User.query.get(claims.user_id)
            if user and getattr(user, "active", True):
                return _identity_for_user(user, "bearer")
        except Exception as e:
            current_app.logger.warning("AI bearer token rejected: %s", str(e))

    # 2) Cookie session (Backoffice)
    try:
        if getattr(current_user, "is_authenticated", False):
            return _identity_for_user(current_user, "cookie")
    except Exception as e:
        logger.debug("Flask-Login session check failed: %s", e)

    # 3) Anonymous
    return AIRequestIdentity(is_authenticated=False, access_level="public", user=None, auth_source="anonymous")
