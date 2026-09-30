"""Shared login-abuse controls: account lockout counters and constant-time credential checks.

Failure counters live in the shared auth-state store (Redis or ``auth_state_entry``), not in
``UserLoginLog`` rows: the transaction middleware rolls back every >= 400 response, so a
mobile ``401`` used to discard its own failure record and the lockout never engaged. The
store also makes the counter visible to every worker.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from flask import current_app

from app.utils.auth_state import NS_LOGIN_FAILURES, AuthStateUnavailable, get_auth_state

logger = logging.getLogger(__name__)

ACCOUNT_LOCKOUT_THRESHOLD = 10
ACCOUNT_LOCKOUT_WINDOW_SECONDS = 15 * 60

_dummy_password_hash: Optional[str] = None


def _email_key(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def is_login_locked_out(email: str) -> bool:
    """True once ``ACCOUNT_LOCKOUT_THRESHOLD`` failures were recorded inside the window.

    Fails closed: if the shared store cannot be read the login is refused.
    """
    try:
        raw = get_auth_state().get_counter(NS_LOGIN_FAILURES, _email_key(email))
    except AuthStateUnavailable as exc:
        current_app.logger.error("SECURITY: login lockout check failed; denying login: %s", exc)
        return True
    return raw >= ACCOUNT_LOCKOUT_THRESHOLD


def record_login_failure(email: str) -> None:
    try:
        get_auth_state().incr(NS_LOGIN_FAILURES, _email_key(email), ACCOUNT_LOCKOUT_WINDOW_SECONDS)
    except AuthStateUnavailable as exc:
        current_app.logger.error("SECURITY: could not record login failure: %s", exc)


def clear_login_failures(email: str) -> None:
    try:
        get_auth_state().delete(NS_LOGIN_FAILURES, _email_key(email))
    except AuthStateUnavailable as exc:
        current_app.logger.error("SECURITY: could not clear login failures: %s", exc)


def burn_password_check(password: str) -> None:
    """Spend the time of one password hash verification when no user matched.

    Without it, "unknown email" answers measurably faster than "wrong password",
    which is an account-enumeration oracle.
    """
    global _dummy_password_hash
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import VerificationError, InvalidHashError

        hasher = PasswordHasher()
        if _dummy_password_hash is None:
            _dummy_password_hash = hasher.hash("dummy-password-for-timing-equalisation")
        try:
            hasher.verify(_dummy_password_hash, password or "")
        except (VerificationError, InvalidHashError):
            pass
    except ImportError:
        from werkzeug.security import check_password_hash, generate_password_hash

        if _dummy_password_hash is None:
            _dummy_password_hash = generate_password_hash(
                "dummy-password-for-timing-equalisation", method="pbkdf2:sha256"
            )
        check_password_hash(_dummy_password_hash, password or "")
