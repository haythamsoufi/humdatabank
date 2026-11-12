"""
Lightweight DLP (data loss prevention) guard for AI chat requests.

Goals:
- Prevent accidental leakage of obvious sensitive identifiers to third-party LLM providers.
- Never forward or store a flagged span raw: whatever is allowed through has each one
  replaced by a "[REDACTED_*]" placeholder. In "confirm" mode contact details
  (AI_DLP_AUTO_MASK_KINDS) are masked without asking, while credentials and financial
  identifiers need the user's "Mask & send"; "block" mode rejects any finding.

This is intentionally best-effort and regex-based; it is NOT a full DLP system.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple

from flask import current_app, request

from app.utils.ai.ai_utils import is_user_history_entry

logger = logging.getLogger(__name__)


@dataclass
class DlpFinding:
    kind: str
    count: int


@dataclass
class _Verdict:
    allowed: bool
    error: Optional[Dict[str, Any]]
    findings: List[DlpFinding]
    safe_message: str
    action: str


# "confirm" mode masks these without asking (overridable via AI_DLP_AUTO_MASK_KINDS).
_DEFAULT_AUTO_MASK_KINDS: FrozenSet[str] = frozenset({"email", "phone"})
# The form-builder panel is exempt from these: its messages carry the extracted text of an
# imported questionnaire, whose contact details belong to the source document and must reach
# the generated form verbatim. Credentials and financial identifiers are still screened.
_FORM_BUILDER_EXEMPT_KINDS: FrozenSet[str] = frozenset({"email", "phone"})
_HIGH_RISK_KINDS: FrozenSet[str] = frozenset(
    {"jwt", "bearer_token", "private_key", "password", "api_key_or_secret", "payment_card", "iban"}
)
_KIND_LABELS: Dict[str, str] = {
    "email": "email address",
    "phone": "phone number",
    "jwt": "access token",
    "bearer_token": "bearer token",
    "private_key": "private key",
    "password": "password",
    "api_key_or_secret": "API key or secret",
    "iban": "bank account number",
    "payment_card": "payment card number",
}
_TRUE_STRINGS = frozenset({"1", "true", "yes", "y", "on"})
# Assignment values that are not a literal secret: template placeholders and our own masks.
_PLACEHOLDER_PREFIXES = ("[REDACTED_", "<", "${", "{{", "%")

# Length-bounded: with an unbounded local part, a long run of word characters without an
# "@" took quadratic time to scan.
_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,253}\.[A-Z]{2,63}\b", re.IGNORECASE)
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_RE_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b")
_RE_BASIC_AUTH = re.compile(r"\bBasic\s+(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{16,}={0,2}")
# Any PEM/PGP private key label (RSA, EC, OPENSSH, ENCRYPTED, "PGP ... KEY BLOCK", ...). A paste
# cut off before its END marker is key material through to the end of the text.
_PRIVATE_KEY_LABEL = r"(?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?"
_RE_PRIVATE_KEY_BLOCK = re.compile(
    rf"-----BEGIN {_PRIVATE_KEY_LABEL}-----(?:.*?-----END {_PRIVATE_KEY_LABEL}-----|.*)",
    re.DOTALL,
)
# scheme://user:password@host — database/broker connection strings and basic-auth URLs.
_RE_URL_CREDENTIALS = re.compile(
    r"(?i)\b(?:https?|s?ftps?|postgres(?:ql)?|mysql|mariadb|mssql|sqlserver|oracle|mongodb(?:\+srv)?"
    r"|rediss?|amqps?|smtps?)://[^\s:/@]*:(?P<value>[^\s@/]+)@"
)
# Provider key formats recognisable without a "key=" label.
_RE_PROVIDER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"sk-(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{20,}"  # OpenAI, Anthropic
    r"|[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"  # Stripe
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"  # AWS access key id
    r"|gh[oprsu]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}"  # GitHub
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"  # Slack
    r"|AIza[A-Za-z0-9_-]{35}"  # Google
    r")(?![A-Za-z0-9_-])"
)
# Credential names written as an assignment: env files (OPENAI_API_KEY=...), JSON
# ("client_secret": "..."), YAML, connection strings (AccountKey=...;). The name may sit
# inside a longer identifier, so the guards are alphanumeric-only (\b fails next to "_").
# Only the value is masked; a password value runs to the end of the line, so a passphrase
# is masked whole.
_RE_PASSWORD_ASSIGN = re.compile(
    r"(?i)(?<![a-z0-9])(?:password|passwd|passphrase|pwd)(?![a-z0-9])[\"']?[ \t]*[:=][ \t]*"
    r"(?:\"(?P<dq>[^\"\n]+)\"|'(?P<sq>[^'\n]+)'|(?P<bare>[^\s\"',;](?:[^\n\"',;]*[^\s\"',;])?))"
)
_RE_SECRET_ASSIGN = re.compile(
    r"(?i)(?<![a-z0-9])(?:api[_-]?key|secret(?:[_-]?key)?|client[_-]?secret|private[_-]?key"
    r"|access[_-]?key|account[_-]?key|(?:auth|access)[_-]?token|shared[_-]?access[_-]?(?:key|signature))"
    r"(?![a-z0-9])[\"']?[ \t]*[:=][ \t]*[\"']?(?P<value>[^\s\"',;]{6,})"
)
# Optionally space-grouped; _mask_iban() requires a valid ISO 13616 checksum.
_RE_IBAN_CANDIDATE = re.compile(r"\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]){10,30}\b")
# 13-19 digits, optionally single space/hyphen separated; _mask_payment_card() requires Luhn.
_RE_PAN_CANDIDATE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
# Digit groups joined by short runs of " ", "-", ".", "(" or ")" — never a newline or tab, so
# the figures in a pasted table are not read as one long number. The same shape also fits
# years, grouped figures, dates and IP addresses; _is_phone_number() tells them apart.
_RE_PHONE_CANDIDATE = re.compile(r"(?<![\w+])(?:\+|\(\+?)?\d(?:[ ().\-]{0,3}\d)+(?!\w)")
_RE_DIGIT_GROUP = re.compile(r"\d+")
_RE_DIGIT_SEPARATOR = re.compile(r"(?<=\d)\D+(?=\d)")


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


def _iban_checksum_ok(compact: str) -> bool:
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(ch, 36)) for ch in rearranged)) % 97 == 1


def _is_literal_value(value: str) -> bool:
    """False for placeholders such as "<API_KEY>", "${TOKEN}", "****" or "xxxx"."""
    if value.startswith(_PLACEHOLDER_PREFIXES):
        return False
    return len({c.lower() for c in value if c.isalnum()}) > 1


def _is_year(group: str) -> bool:
    return len(group) == 4 and 1900 <= int(group) <= 2099


def _is_date_run(groups: List[str]) -> bool:
    """True for one or more d.m.yyyy / yyyy-mm-dd dates, e.g. "01.02.2024 - 05.02.2024"."""
    if not groups or len(groups) % 3:
        return False
    for i in range(0, len(groups), 3):
        a, b, c = groups[i : i + 3]
        day_first = len(a) <= 2 and len(b) <= 2 and _is_year(c) and 0 < int(a) <= 31 and 0 < int(b) <= 31
        year_first = _is_year(a) and len(b) <= 2 and len(c) <= 2 and 0 < int(b) <= 12 and 0 < int(c) <= 31
        if not (day_first or year_first):
            return False
    return True


def _is_phone_number(span: str) -> bool:
    groups = _RE_DIGIT_GROUP.findall(span)
    digits = "".join(groups)
    significant = len(digits) - 2 if digits.startswith("00") else len(digits)
    if significant < 9 or _is_date_run(groups):
        return False
    # International ("+41 ...", "0041 ...") and trunk-prefixed ("022 ...") numbers.
    if span.startswith(("+", "(+")) or (len(groups[0]) > 1 and groups[0].startswith("0")):
        return True
    # Otherwise it must be grouped like a phone number and not read as figures.
    if significant > 15 or not 3 <= len(groups) <= 5 or sum(_is_year(g) for g in groups) > 1:
        return False
    if sum(len(g) == 1 for g in groups) > 1:
        return False  # a row of small figures: "3 12 5 0 140"
    seps = _RE_DIGIT_SEPARATOR.findall(span)
    if any("  " in s for s in seps):
        return False  # column-aligned text, not a dialable number
    if _is_year(groups[0]):  # a year label in front of a figure: "2019 120 000"
        groups, seps = groups[1:], seps[1:]
        if len(groups) < 3:
            return False
    if all(len(g) >= 4 for g in groups):  # "1200 1500 1800"
        return False
    if len(set(seps)) == 1 and seps[0] in (" ", "."):
        if len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:]):
            return False  # thousands-grouped figure: "1 234 567 890", "125.000.000"
        if seps[0] == "." and len(groups) == 4 and all(int(g) <= 255 for g in groups):
            return False  # IPv4 address
    return True


_Masker = Callable[["re.Match[str]"], Optional[str]]


def _fixed(placeholder: str) -> _Masker:
    return lambda m: placeholder


def _mask_group(m: "re.Match[str]", group: str, placeholder: str) -> str:
    start, end = m.start(group) - m.start(), m.end(group) - m.start()
    whole = m.group(0)
    return whole[:start] + placeholder + whole[end:]


def _mask_url_credentials(m: "re.Match[str]") -> Optional[str]:
    if not _is_literal_value(m.group("value")):
        return None
    return _mask_group(m, "value", "[REDACTED_PASSWORD]")


def _mask_password_assignment(m: "re.Match[str]") -> Optional[str]:
    group = next(g for g in ("dq", "sq", "bare") if m.group(g) is not None)
    value = m.group(group)
    if len(value) < 4 or not _is_literal_value(value):
        return None
    return _mask_group(m, group, "[REDACTED_PASSWORD]")


def _mask_secret_assignment(m: "re.Match[str]") -> Optional[str]:
    value = m.group("value")
    # Real key material has a digit or symbol; this leaves prose such as
    # "the secret: volunteers ..." alone.
    if not _is_literal_value(value) or not any(c.isdigit() or c in "_+/=-" for c in value):
        return None
    return _mask_group(m, "value", "[REDACTED_API_KEY]")


def _mask_iban(m: "re.Match[str]") -> Optional[str]:
    span = m.group(0)
    # Longest checksum-valid prefix, so a trailing word ("... 00 BIC") is not swallowed.
    for end in range(len(span), 14, -1):
        if span[end - 1] == " ":
            continue
        compact = span[:end].replace(" ", "")
        if 15 <= len(compact) <= 34 and _iban_checksum_ok(compact):
            return "[REDACTED_IBAN]" + span[end:]
    return None


def _mask_payment_card(m: "re.Match[str]") -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", m.group(0))
    # No card network issues numbers starting with 0 (and runs of zeros pass Luhn).
    if not (13 <= len(digits) <= 19) or digits.startswith("0") or not _luhn_ok(digits):
        return None
    return "[REDACTED_CARD]"


def _mask_phone(m: "re.Match[str]") -> Optional[str]:
    return "[REDACTED_PHONE]" if _is_phone_number(m.group(0)) else None


# Applied in order, each to the output of the previous one, so a span gets the most specific
# label: a URL password sits right before an "@" (email shape), a card number is also
# phone-shaped, a provider key is often the value of a "key=" assignment.
_DETECTORS: Tuple[Tuple[str, "re.Pattern[str]", _Masker], ...] = (
    ("private_key", _RE_PRIVATE_KEY_BLOCK, _fixed("[REDACTED_PRIVATE_KEY]")),
    ("password", _RE_URL_CREDENTIALS, _mask_url_credentials),
    ("jwt", _RE_JWT, _fixed("[REDACTED_TOKEN]")),
    ("bearer_token", _RE_BEARER, _fixed("Bearer [REDACTED_TOKEN]")),
    ("password", _RE_BASIC_AUTH, _fixed("Basic [REDACTED_PASSWORD]")),
    ("api_key_or_secret", _RE_PROVIDER_TOKEN, _fixed("[REDACTED_API_KEY]")),
    ("password", _RE_PASSWORD_ASSIGN, _mask_password_assignment),
    ("api_key_or_secret", _RE_SECRET_ASSIGN, _mask_secret_assignment),
    ("email", _RE_EMAIL, _fixed("[REDACTED_EMAIL]")),
    ("iban", _RE_IBAN_CANDIDATE, _mask_iban),
    ("payment_card", _RE_PAN_CANDIDATE, _mask_payment_card),
    ("phone", _RE_PHONE_CANDIDATE, _mask_phone),
)


def _sub_counted(pattern: "re.Pattern[str]", mask: _Masker, text: str) -> Tuple[str, int]:
    hits = 0

    def _replace(m: "re.Match[str]") -> str:
        nonlocal hits
        masked = mask(m)
        if masked is None:
            return m.group(0)
        hits += 1
        return masked

    return pattern.sub(_replace, text), hits


def _scan(text: str, skip_kinds: FrozenSet[str]) -> Tuple[str, Dict[str, int]]:
    """Mask every detected span; return the masked text and the hit count per kind.

    Detection and masking are the same pass, so anything counted is also removed, and a
    placeholder never matches again (masking is idempotent).
    """
    counts: Dict[str, int] = {}
    for kind, pattern, mask in _DETECTORS:
        if kind in skip_kinds:
            continue
        text, hits = _sub_counted(pattern, mask, text)
        if hits:
            counts[kind] = counts.get(kind, 0) + hits
    return text, counts


def analyze_text(text: str, *, skip_kinds: Iterable[str] = ()) -> List[DlpFinding]:
    """
    Return a list of detected sensitive patterns (counts only; never return raw matches).
    """
    if not text:
        return []
    _, counts = _scan(str(text), frozenset(skip_kinds))
    return [DlpFinding(kind=kind, count=n) for kind, n in counts.items()]


def mask_sensitive_text(text: str, *, skip_kinds: Iterable[str] = ()) -> str:
    """
    Replace every span analyze_text() flags with a fixed "[REDACTED_*]" placeholder.

    Callers forwarding a flagged message anyway must send/persist the returned text instead
    of the original. Like analyze_text(), this never returns or logs the matched substrings.
    """
    if not text:
        return text
    masked, _ = _scan(str(text), frozenset(skip_kinds))
    return masked


def _cfg_bool(key: str, default: bool) -> bool:
    v = current_app.config.get(key)
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_STRINGS
    return bool(v)


def _cfg_str(key: str, default: str) -> str:
    v = current_app.config.get(key)
    if v is None:
        return default
    return str(v)


def _cfg_kinds(key: str, default: FrozenSet[str]) -> FrozenSet[str]:
    v = current_app.config.get(key)
    if v is None:
        return default
    if isinstance(v, str):
        v = v.split(",")
    try:
        return frozenset(str(k).strip().lower() for k in v if str(k).strip())
    except TypeError:
        logger.debug("%s is not a list of finding kinds; using the default", key)
        return default


def _scan_limit() -> int:
    try:
        return max(0, int(current_app.config.get("AI_DLP_MAX_SCAN_CHARS", 16000)))
    except (TypeError, ValueError) as e:
        logger.debug("AI_DLP_MAX_SCAN_CHARS parse failed: %s", e)
        return 16000


def _dlp_mode() -> str:
    mode = _cfg_str("AI_DLP_MODE", "confirm").strip().lower()
    return mode if mode in {"warn", "confirm", "block"} else "confirm"


def _error_payload(error_type: str, findings: List[DlpFinding]) -> Dict[str, Any]:
    labels = ", ".join(_KIND_LABELS.get(f.kind, f.kind) for f in findings)
    dlp: Dict[str, Any] = {"sensitive": True, "findings": [asdict(f) for f in findings]}
    if error_type == "dlp_requires_confirmation":
        dlp["recommendation"] = "remove_or_confirm"
    return {
        "success": False,
        "error": f"Sensitive information detected ({labels}). Remove it and send your message again.",
        "error_type": error_type,
        "dlp": dlp,
    }


def _decide(*, message: str, allow_sensitive: bool, form_builder_assistant: bool) -> _Verdict:
    if not _cfg_bool("AI_DLP_ENABLED", True):
        return _Verdict(True, None, [], message, "disabled")
    skip = _FORM_BUILDER_EXEMPT_KINDS if form_builder_assistant else frozenset()
    findings = analyze_text((message or "")[: _scan_limit()], skip_kinds=skip)
    if not findings:
        return _Verdict(True, None, [], message, "clean")
    mode = _dlp_mode()
    if mode == "block":
        return _Verdict(False, _error_payload("dlp_blocked", findings), findings, message, "blocked")
    masked = mask_sensitive_text(message, skip_kinds=skip)
    if mode == "warn":
        return _Verdict(True, None, findings, masked, "auto_masked")
    if allow_sensitive:
        return _Verdict(True, None, findings, masked, "sent_masked")
    if {f.kind for f in findings} <= _cfg_kinds("AI_DLP_AUTO_MASK_KINDS", _DEFAULT_AUTO_MASK_KINDS):
        return _Verdict(True, None, findings, masked, "auto_masked")
    error = _error_payload("dlp_requires_confirmation", findings)
    return _Verdict(False, error, findings, message, "confirm_required")


def evaluate_ai_message(
    *,
    message: str,
    allow_sensitive: bool,
    form_builder_assistant: bool = False,
) -> Tuple[bool, Optional[Dict[str, Any]], List[DlpFinding], str]:
    """
    Evaluate a chat message and decide whether to allow it.

    Returns:
      (allowed, error_payload, findings, safe_message)

      `safe_message` is `message` unchanged when nothing was flagged (or DLP is
      disabled). Whenever the message is allowed through *with* findings — "warn" mode,
      "confirm" mode with `allow_sensitive=True`, or "confirm" mode when every finding is
      an AI_DLP_AUTO_MASK_KINDS kind — it has every flagged span replaced by a
      "[REDACTED_*]" placeholder. Callers MUST use `safe_message` in place of the original
      for everything downstream (LLM call, DB persistence, conversation title, ...).
      When not allowed (blocked / confirmation still required), `safe_message` is just the
      original `message`; the caller must reject the request and never forward or store it.

    `form_builder_assistant=True` skips the contact-detail kinds (email, phone) only. The
    form-builder message is often a short instruction plus the full extracted text of an
    *imported* questionnaire, whose names, emails and phone numbers belong to the source
    document; masking them would bake "[REDACTED_*]" placeholders into the generated form.
    Credentials, keys and financial identifiers in it are still confirmed/blocked as usual.
    """
    verdict = _decide(
        message=message,
        allow_sensitive=allow_sensitive,
        form_builder_assistant=form_builder_assistant,
    )
    return verdict.allowed, verdict.error, verdict.findings, verdict.safe_message


def screen_ai_message(
    *,
    message: str,
    allow_sensitive: bool,
    form_builder_assistant: bool,
    user_id: Optional[int],
    transport: str,
    endpoint_path: str,
    client: str,
    conversation_id: Optional[str],
    client_message_id: Optional[str],
) -> Tuple[bool, Optional[Dict[str, Any]], List[DlpFinding], str]:
    """evaluate_ai_message() plus the audit event for any finding, recording the action taken.

    The single DLP entry point for the chat transports (HTTP, SSE, WebSocket).
    """
    verdict = _decide(
        message=message,
        allow_sensitive=allow_sensitive,
        form_builder_assistant=form_builder_assistant,
    )
    if verdict.findings:
        log_dlp_audit_event(
            user_id=user_id,
            action=verdict.action,
            transport=transport,
            endpoint_path=endpoint_path,
            client=client,
            conversation_id=conversation_id,
            client_message_id=client_message_id,
            allow_sensitive=allow_sensitive,
            findings=verdict.findings,
        )
    return verdict.allowed, verdict.error, verdict.findings, verdict.safe_message


def mask_conversation_history(
    history: Optional[Iterable[Any]],
    *,
    form_builder_assistant: bool = False,
) -> List[Any]:
    """
    Mask the user turns of a client-supplied conversation history.

    The client's copy of the transcript holds what the user typed before DLP ran (and
    messages they cancelled at the DLP dialog). It is persisted on edit/retry
    ("branch_from_edit") and sent to the LLM for anonymous callers, so neither goes through
    the per-message gate. Assistant turns are provider output and stay as they are.
    No-op when DLP is disabled; contact details are kept for the form-builder panel, as in
    evaluate_ai_message().
    """
    entries = list(history or [])
    if not entries or not _cfg_bool("AI_DLP_ENABLED", True):
        return entries
    skip = _FORM_BUILDER_EXEMPT_KINDS if form_builder_assistant else frozenset()
    masked: List[Any] = []
    for entry in entries:
        if is_user_history_entry(entry):
            entry = {
                k: mask_sensitive_text(v, skip_kinds=skip) if k in ("message", "content") and isinstance(v, str) else v
                for k, v in entry.items()
            }
        masked.append(entry)
    return masked


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
    from app.extensions import db

    try:
        from app.models import SecurityEvent
        from app.utils.common.datetime_helpers import utcnow
        from app.services.platform.user_analytics_service import get_client_ip

        # Ensure fields are short/stable
        action_s = (action or "detected").strip().lower()[:64]
        transport_s = (transport or "http").strip().lower()[:16]
        client_s = (client or "unknown").strip().lower()[:16]
        endpoint_s = (endpoint_path or "").strip()[:255] or (request.path[:255] if request else "unknown")

        # Escalated = the user was stopped, or chose to send past the warning.
        kinds = {f.kind for f in findings if getattr(f, "kind", None)}
        escalated = action_s in {"blocked", "confirm_required", "sent_masked"}
        if kinds & _HIGH_RISK_KINDS:
            severity = "high" if escalated else "medium"
        else:
            severity = "medium" if escalated else "low"

        context_data = {
            "action": action_s,
            "transport": transport_s,
            "client": client_s,
            "endpoint_path": endpoint_s,
            "conversation_id": (str(conversation_id)[:64] if conversation_id else None),
            "client_message_id": (str(client_message_id)[:64] if client_message_id else None),
            "allow_sensitive": bool(allow_sensitive),
            "findings": [asdict(f) for f in findings],
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
        logger.warning("Failed to write DLP audit SecurityEvent: %s", e, exc_info=True)
        try:
            db.session.rollback()
        except Exception as rb_err:
            logger.debug("DLP audit rollback failed: %s", rb_err)
