"""
Lightweight DLP (data loss prevention) guard for AI chat requests.

Goals:
- Prevent accidental leakage of obvious sensitive identifiers to third-party LLM providers.
- Provide a confirmation flow ("send anyway") and a safer alternative ("private mode" / local-only).

This is intentionally best-effort and regex-based; it is NOT a full DLP system.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app, request


@dataclass
class DlpFinding:
    kind: str
    count: int


_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_RE_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_RE_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b")
_RE_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_RE_PASSWORD_ASSIGN = re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*[^\s]{4,}")
_RE_API_KEY_ASSIGN = re.compile(r"(?i)\b(api[_-]?key|secret|secret[_-]?key|access[_-]?key)\b\s*[:=]\s*[^\s]{6,}")
_RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

# 13-19 digits possibly spaced/hyphenated
_RE_PAN_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    s = 0
    alt = False
    for ch in reversed(digits):
        if not ch.isdigit():
            continue
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return (s % 10) == 0


def analyze_text(text: str) -> List[DlpFinding]:
    """
    Return a list of detected sensitive patterns (counts only; never return raw matches).
    """
    if not text:
        return []
    t = str(text)

    findings: List[DlpFinding] = []

    def add(kind: str, n: int) -> None:
        if n > 0:
            findings.append(DlpFinding(kind=kind, count=int(n)))

    add("email", len(_RE_EMAIL.findall(t)))
    # Require at least 9 actual digit characters to avoid false positives on
    # year ranges (e.g. "2020-2024" has 8 digits) and date strings.
    phone_hits = sum(
        1 for m in _RE_PHONE.finditer(t)
        if sum(c.isdigit() for c in m.group(0)) >= 9
    )
    add("phone", phone_hits)
    add("jwt", len(_RE_JWT.findall(t)))
    add("bearer_token", len(_RE_BEARER.findall(t)))
    add("private_key", 1 if _RE_PRIVATE_KEY.search(t) else 0)
    add("password", len(_RE_PASSWORD_ASSIGN.findall(t)))
    add("api_key_or_secret", len(_RE_API_KEY_ASSIGN.findall(t)))
    add("iban", len(_RE_IBAN.findall(t)))

    # Credit card numbers (PAN) – verify with Luhn to reduce false positives
    pan_hits = 0
    for m in _RE_PAN_CANDIDATE.finditer(t):
        cand = re.sub(r"[^0-9]", "", m.group(0) or "")
        if 13 <= len(cand) <= 19 and _luhn_ok(cand):
            pan_hits += 1
            if pan_hits >= 5:
                break
    add("payment_card", pan_hits)

    return findings


def _cfg_bool(key: str, default: bool) -> bool:
    v = current_app.config.get(key)
    if v is None:
        return default
    return bool(v)


def _cfg_str(key: str, default: str) -> str:
    v = current_app.config.get(key)
    if v is None:
        return default
    return str(v)


def evaluate_ai_message(
    *,
    message: str,
    allow_sensitive: bool,
) -> Tuple[bool, Optional[Dict[str, Any]], List[DlpFinding]]:
    """
    Evaluate a chat message and decide whether to allow it.

    Returns:
      (allowed, error_payload)
    """
    if not _cfg_bool("AI_DLP_ENABLED", True):
        return True, None, []

    # Bound scanning to avoid pathological payloads (we already cap message chars elsewhere).
    try:
        max_scan = int(current_app.config.get("AI_DLP_MAX_SCAN_CHARS", 12000))
    except Exception as e:
        logger.debug("AI_DLP_MAX_SCAN_CHARS parse failed: %s", e)
        max_scan = 12000
    text = (message or "")[: max(0, max_scan)]

    findings = analyze_text(text)
    if not findings:
        return True, None, []

    # Mode: warn | confirm | block
    mode = _cfg_str("AI_DLP_MODE", "confirm").strip().lower()
    if mode not in {"warn", "confirm", "block"}:
        mode = "confirm"

    if mode == "warn":
        return True, None, findings

    if mode == "block":
        return False, {
            "success": False,
            "error": "Sensitive information detected. Please remove it before sending.",
            "error_type": "dlp_blocked",
            "dlp": {"sensitive": True, "findings": [f.__dict__ for f in findings]},
        }, findings

    # confirm
    if allow_sensitive:
        return True, None, findings

    return False, {
        "success": False,
        "error": "Sensitive information detected. Confirm before sending to the AI provider.",
        "error_type": "dlp_requires_confirmation",
        "dlp": {
            "sensitive": True,
            "findings": [f.__dict__ for f in findings],
            "recommendation": "remove_or_confirm",
        },
    }, findings


def log_dlp_audit_event(
    *,
    user_id: Optional[int],
    action: str,
    transport: str,
    endpoint_path: str,
    client: str,
    conversation_id: Optional[str],
    client_message_id: Optional[str],
    allow_sensitive: bool,
    findings: List[DlpFinding],
) -> None:
    """
    Write an admin-visible audit log entry when DLP detects sensitive patterns.
    SECURITY: Never store the user message or any matched substrings.
    """
    if not findings:
        return
    try:
        from app.extensions import db
        from app.models import SecurityEvent
        from app.utils.datetime_helpers import utcnow
        from app.services.user_analytics_service import get_client_ip

        high_kinds = {"jwt", "bearer_token", "private_key", "password", "api_key_or_secret", "payment_card", "iban"}
        kinds = {f.kind for f in findings if getattr(f, "kind", None)}

        # Severity: conservative
        severity = "low"
        if kinds & high_kinds:
            severity = "high" if action in {"blocked", "confirm_required", "send_anyway"} else "medium"
        else:
            severity = "medium" if action in {"blocked", "confirm_required", "send_anyway"} else "low"

        # Ensure fields are short/stable
        action_s = (action or "detected").strip().lower()[:64]
        transport_s = (transport or "http").strip().lower()[:16]
        client_s = (client or "unknown").strip().lower()[:16]
        endpoint_s = (endpoint_path or "").strip()[:255] or (request.path[:255] if request else "unknown")

        context_data = {
            "action": action_s,
            "transport": transport_s,
            "client": client_s,
            "endpoint_path": endpoint_s,
            "conversation_id": (str(conversation_id)[:64] if conversation_id else None),
            "client_message_id": (str(client_message_id)[:64] if client_message_id else None),
            "allow_sensitive": bool(allow_sensitive),
            "findings": [f.__dict__ for f in findings],
        }

        ev = SecurityEvent(
            user_id=user_id,
            event_type="ai_dlp_sensitive_detected",
            severity=severity,
            description=f"AI DLP detected sensitive patterns (action={action_s}, transport={transport_s}).",
            timestamp=utcnow(),
            ip_address=(get_client_ip() or request.remote_addr or "unknown")[:45],
            user_agent=(request.user_agent.string if request and request.user_agent else "unknown")[:500],
            context_data=context_data,
        )
        db.session.add(ev)
        db.session.commit()
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning("Failed to write DLP audit SecurityEvent: %s", e, exc_info=True)
        except Exception as log_err:
            import logging
            logging.getLogger(__name__).debug("DLP audit log failed: %s", log_err)
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception as rb_err:
            import logging
            logging.getLogger(__name__).debug("DLP audit rollback failed: %s", rb_err)

