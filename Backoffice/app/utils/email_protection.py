from __future__ import annotations

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


def check_email_recipients_allowed(requested_emails: Iterable[str]) -> EmailProtectionResult:
    """
    Centralized email protection check used by admin notification/campaign endpoints.

    Recipient email protection is disabled: all requested emails are always allowed.
    """
    env = (current_app.config.get("FLASK_CONFIG") or "").lower()
    requested = _normalize_emails(requested_emails)
    return EmailProtectionResult(
        enabled=False,
        environment=env,
        allowed=[],
        requested=requested,
        allowed_requested=requested,
        blocked_requested=[],
        reason=None,
    )
