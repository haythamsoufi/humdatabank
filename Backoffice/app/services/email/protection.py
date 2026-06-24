from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from flask import current_app


@dataclass(frozen=True)
class EmailProtectionResult:
    enabled: bool
    environment: str
    allowed: List[str]
    requested: List[str]
    allowed_requested: List[str]
    blocked_requested: List[str]
    reason: Optional[str]


def _normalize_emails(emails: Iterable[str]) -> List[str]:
    out: List[str] = []
    for e in emails or []:
        if not e:
            continue
        s = str(e).strip().lower()
        if s:
            out.append(s)
    return out


def _resolve_flask_config() -> str:
    """Resolve FLASK_CONFIG from app config first, then the process environment."""
    try:
        cfg = current_app.config.get("FLASK_CONFIG")
    except RuntimeError:
        cfg = None
    if cfg:
        return str(cfg).lower()
    return (os.environ.get("FLASK_CONFIG") or "").lower()


def _is_production_flask_config() -> bool:
    return _resolve_flask_config() == "production"


def _allowed_recipients_dev() -> List[str]:
    allowed = current_app.config.get("ALLOWED_EMAIL_RECIPIENTS_DEV") or []
    return [str(e).strip().lower() for e in allowed if e and str(e).strip()]


def check_email_recipients_allowed(requested_emails: Iterable[str]) -> EmailProtectionResult:
    """
    Centralized email protection check used by admin notification/campaign endpoints.

    In production (``FLASK_CONFIG=production``) protection is disabled. In development
    and staging, outbound mail to non-allowlisted addresses is blocked when
    ``ALLOWED_EMAIL_RECIPIENTS_DEV`` is configured; when the allowlist is empty,
    all recipients are blocked so misconfigured staging cannot email real users.
    """
    env = _resolve_flask_config()
    requested = _normalize_emails(requested_emails)

    if _is_production_flask_config():
        return EmailProtectionResult(
            enabled=False,
            environment=env,
            allowed=[],
            requested=requested,
            allowed_requested=requested,
            blocked_requested=[],
            reason=None,
        )

    allowed = _allowed_recipients_dev()
    if not allowed:
        return EmailProtectionResult(
            enabled=True,
            environment=env,
            allowed=[],
            requested=requested,
            allowed_requested=[],
            blocked_requested=requested,
            reason=(
                f"Email sending is restricted in {env or 'non-production'}; "
                "set ALLOWED_EMAIL_RECIPIENTS_DEV (comma-separated)."
            ),
        )

    allowed_set = set(allowed)
    allowed_requested = [e for e in requested if e in allowed_set]
    blocked_requested = [e for e in requested if e not in allowed_set]
    reason = None
    if blocked_requested:
        reason = f"Email sending is restricted in {env or 'non-production'}."

    return EmailProtectionResult(
        enabled=True,
        environment=env,
        allowed=allowed,
        requested=requested,
        allowed_requested=allowed_requested,
        blocked_requested=blocked_requested,
        reason=reason,
    )
