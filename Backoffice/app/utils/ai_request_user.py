"""
Resolve the effective request user for the AI brain.

Order of precedence:
1) Flask-Login cookie session (Backoffice web)
2) Bearer token (Website/Mobile) via Authorization: Bearer <jwt>
3) Anonymous (public)
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


def resolve_ai_identity() -> AIRequestIdentity:
    # 1) Cookie session (Backoffice)
    try:
        if getattr(current_user, "is_authenticated", False):
            from app.services.authorization_service import AuthorizationService
            if AuthorizationService.is_system_manager(current_user):
                level = "system_manager"
            elif AuthorizationService.is_admin(current_user):
                level = "admin"
            else:
                level = "user"
            return AIRequestIdentity(
                is_authenticated=True,
                access_level=level,
                user=current_user,
                auth_source="cookie",
            )
    except Exception as e:
        logger.debug("Flask-Login session check failed, falling through to bearer: %s", e)

    # 2) Bearer token (Website/Mobile)
    token = _bearer_token()
    if token:
        try:
            claims = decode_ai_token(token)
            user = User.query.get(claims.user_id)
            if user and getattr(user, "active", True):
                from app.services.authorization_service import AuthorizationService
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
                    auth_source="bearer",
                )
        except Exception as e:
            current_app.logger.warning("AI bearer token rejected: %s", str(e))

    # 3) Anonymous
    return AIRequestIdentity(is_authenticated=False, access_level="public", user=None, auth_source="anonymous")
