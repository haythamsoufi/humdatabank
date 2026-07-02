"""Idempotent OAuth callback handling to prevent duplicate user sessions."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from flask import current_app

from app import db
from app.models import UserSessionLog
from app.utils.constants import DEFAULT_OAUTH_CALLBACK_LOCK_ID_BASE
from app.utils.datetime_helpers import utcnow
from app.utils.pg_advisory_lock import acquire_transaction_advisory_lock

if TYPE_CHECKING:
    from app.models import User

logger = logging.getLogger(__name__)


def _oauth_callback_lock_id(user_id: int) -> int:
    return DEFAULT_OAUTH_CALLBACK_LOCK_ID_BASE + (int(user_id) % 1_000_000)


def _dedup_window() -> timedelta:
    seconds = int(current_app.config.get('OAUTH_LOGIN_DEDUP_SECONDS', 90))
    return timedelta(seconds=max(1, seconds))


def _recent_active_session_id(
    user_id: int,
    *,
    ip_address: str | None,
    browser: str | None,
    device_type: str | None,
) -> str | None:
    """Return a recent active session for the same user on the same device, if any."""
    cutoff = utcnow() - _dedup_window()
    query = UserSessionLog.query.filter(
        UserSessionLog.user_id == user_id,
        UserSessionLog.is_active.is_(True),
        UserSessionLog.session_start >= cutoff,
    )
    if ip_address:
        query = query.filter(UserSessionLog.ip_address == ip_address)
    if browser:
        query = query.filter(UserSessionLog.browser == browser)
    if device_type:
        query = query.filter(UserSessionLog.device_type == device_type)

    row = (
        query.order_by(UserSessionLog.session_start.desc())
        .with_entities(UserSessionLog.session_id)
        .first()
    )
    return row[0] if row else None


def resolve_azure_b2c_login_session(
    *,
    user: User,
    ip_address: str | None,
    browser: str | None = None,
    device_type: str | None = None,
) -> tuple[str, bool]:
    """Return ``(session_id, created_new_session)`` for an Azure B2C callback.

    When the user already has a recent active ``UserSessionLog`` row from the
    same device (IP + browser + device type), that session is reused instead of
    creating a duplicate. A per-user PostgreSQL transaction advisory lock
    serializes concurrent callbacks so two parallel requests cannot both miss
    the existing row.
    """
    acquire_transaction_advisory_lock(db.session, _oauth_callback_lock_id(user.id))

    recent_session_id = _recent_active_session_id(
        user.id,
        ip_address=ip_address,
        browser=browser,
        device_type=device_type,
    )
    if recent_session_id:
        logger.info(
            "Azure B2C callback: reusing recent session for user %s on same device (session %s…)",
            user.id,
            recent_session_id[:8],
        )
        return recent_session_id, False

    return str(uuid.uuid4()), True
