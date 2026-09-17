"""Unit tests for app.services.ai.chat.dlp — the regex-based AI chat DLP guard.

This module previously had zero direct test coverage. Focus areas:
- analyze_text() pattern detection for each finding kind.
- evaluate_ai_message() mode behavior (warn/confirm/block) and the enabled toggle.
- Regression: the scan window (AI_DLP_MAX_SCAN_CHARS) must cover the full range of
  messages the form-builder panel is allowed to send (AI_FORM_BUILDER_MAX_MESSAGE_CHARS),
  otherwise sensitive content past the scan cutoff is invisible to DLP.
- log_dlp_audit_event() never persists the raw message/matched substrings.
"""

import pytest

from app.services.ai.chat.dlp import (
    analyze_text,
    evaluate_ai_message,
    log_dlp_audit_event,
    mask_sensitive_text,
)


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


class TestAnalyzeText:
    def test_empty_text_returns_no_findings(self):
        assert analyze_text("") == []
        assert analyze_text(None) == []

    def test_detects_email(self):
        findings = analyze_text("Contact me at jane.doe@example.org please")
        kinds = {f.kind for f in findings}
        assert "email" in kinds

    def test_detects_phone_with_enough_digits(self):
        findings = analyze_text("Call me at +1 (555) 123-4567 tomorrow")
        kinds = {f.kind for f in findings}
        assert "phone" in kinds

    def test_does_not_flag_year_range_as_phone(self):
        """8-digit year ranges like 2020-2024 must not false-positive as phone numbers."""
        findings = analyze_text("Coverage for the period 2020-2024 was strong.")
        kinds = {f.kind for f in findings}
        assert "phone" not in kinds

    def test_detects_jwt(self):
        fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abcdefghij"
        findings = analyze_text(f"Here is my token: {fake_jwt}")
        kinds = {f.kind for f in findings}
        assert "jwt" in kinds

    def test_detects_bearer_token(self):
        findings = analyze_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")
        kinds = {f.kind for f in findings}
        assert "bearer_token" in kinds

    def test_detects_private_key_header(self):
        findings = analyze_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEow...")
        kinds = {f.kind for f in findings}
        assert "private_key" in kinds

    def test_detects_password_assignment(self):
        findings = analyze_text("password: SuperSecret123")
        kinds = {f.kind for f in findings}
        assert "password" in kinds

    def test_detects_api_key_assignment(self):
        findings = analyze_text("api_key=sk_live_abcdefghijklmnop")
        kinds = {f.kind for f in findings}
        assert "api_key_or_secret" in kinds

    def test_detects_iban(self):
        findings = analyze_text("My IBAN is DE89370400440532013000 for the transfer")
        kinds = {f.kind for f in findings}
        assert "iban" in kinds

    def test_detects_valid_luhn_card_number(self):
        # 4111111111111111 is a well-known Luhn-valid test Visa PAN.
        findings = analyze_text("Card number: 4111 1111 1111 1111")
        kinds = {f.kind for f in findings}
        assert "payment_card" in kinds

    def test_does_not_flag_luhn_invalid_digit_string(self):
        # Same length as a PAN but fails the Luhn checksum.
        findings = analyze_text("Reference number: 1234 5678 9012 3456")
        kinds = {f.kind for f in findings}
        assert "payment_card" not in kinds

    def test_plain_text_has_no_findings(self):
        findings = analyze_text("How many volunteers are there in Kenya this year?")
        assert findings == []


class TestEvaluateAiMessage:
    def test_disabled_always_allows(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = False
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="email me at a@b.com", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert findings == []
        assert safe_message == "email me at a@b.com"

    def test_clean_message_is_allowed(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="What is the volunteer count for Kenya?", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert findings == []
        assert safe_message == "What is the volunteer count for Kenya?"

    def test_warn_mode_allows_but_reports_findings(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "warn"
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert len(findings) == 1
        # Warn mode isn't gated by a confirmation click, but must still mask before the
        # message is allowed to proceed to the LLM/persistence — no raw passthrough.
        assert "a@b.com" not in safe_message
        assert "[REDACTED_EMAIL]" in safe_message

    def test_block_mode_blocks_regardless_of_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=True
        )
        assert allowed is False
        assert err["error_type"] == "dlp_blocked"
        assert findings

    def test_confirm_mode_blocks_without_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"
        assert findings

    def test_confirm_mode_allows_with_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=True
        )
        assert allowed is True
        assert err is None
        assert findings

    def test_confirm_mode_with_allow_sensitive_masks_instead_of_sending_raw(self, app_ctx):
        """Regression: confirming past the DLP dialog used to send the raw message
        as-is ("send anyway"). It must now mask every flagged span instead."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="my email is a@b.com, call me on 555-123-4567", allow_sensitive=True
        )
        assert allowed is True
        assert err is None
        assert findings
        assert "a@b.com" not in safe_message
        assert "555-123-4567" not in safe_message
        assert "[REDACTED_EMAIL]" in safe_message
        assert "[REDACTED_PHONE]" in safe_message
        # Surrounding non-sensitive text is preserved verbatim.
        assert "my email is" in safe_message
        assert "call me on" in safe_message

    def test_form_builder_assistant_skips_dlp_even_in_block_mode(self, app_ctx):
        """Regression: the form-builder panel routinely appends the full extracted text
        of an *imported* questionnaire to the user's message (see
        form-builder-ai.js's _appendAttachmentBlockToMessage) — e.g. real staff names,
        emails, and reference numbers that are part of the *source document*, not a
        secret the user is pasting into chat. DLP must not block/mask that content, the
        same way AIChatEngine already exempts form-builder messages from PII scrubbing
        before the LLM call (_scrub_message_for_llm)."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        message = (
            "Build a form template from this attached questionnaire.\n\n"
            '--- Imported questionnaire text from "NSD investment monitoring.pdf" ---\n\n'
            "NS Focal Person: Dr. Jane Doe, jane.doe@example.org, reporting period 17/03/2025-16/09/2026"
        )
        allowed, err, findings, safe_message = evaluate_ai_message(
            message=message, allow_sensitive=False, form_builder_assistant=True
        )
        assert allowed is True
        assert err is None
        assert findings == []
        # Not just "allowed" — the imported document text must survive completely
        # unmasked, or the AI would transcribe "[REDACTED_EMAIL]" into the new form.
        assert safe_message == message
        assert "jane.doe@example.org" in safe_message

    def test_form_builder_assistant_false_is_a_no_op(self, app_ctx):
        """The new parameter must default to today's behavior when omitted/False."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False, form_builder_assistant=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_blocked"
        assert findings

    def test_invalid_mode_falls_back_to_confirm(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "not-a-real-mode"
        allowed, _err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is False
        assert findings

    def test_dlp_error_payload_never_contains_raw_message(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        secret_email = "very.secret.person@example.org"
        _allowed, err, _findings, _safe_message = evaluate_ai_message(
            message=f"my email is {secret_email}", allow_sensitive=False
        )
        assert secret_email not in str(err)

    def test_scan_window_covers_full_form_builder_message_length(self, app_ctx):
        """Regression: AI_DLP_MAX_SCAN_CHARS previously defaulted to 12000 while the
        form-builder panel allows messages up to AI_FORM_BUILDER_MAX_MESSAGE_CHARS (16000
        by default) — sensitive content placed after char 12000 was silently invisible to
        DLP. The scan window must cover at least a 16000-char form-builder message."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        max_scan = int(app_ctx.config.get("AI_DLP_MAX_SCAN_CHARS", 12000))
        form_builder_cap = int(app_ctx.config.get("AI_FORM_BUILDER_MAX_MESSAGE_CHARS", 16000))
        assert max_scan >= form_builder_cap

        # Place a sensitive email right at the tail of a max-length form-builder message.
        padding = "x" * (form_builder_cap - 40)
        message = f"{padding} contact secret.person@example.org"
        allowed, err, findings, _safe_message = evaluate_ai_message(message=message, allow_sensitive=False)
        assert allowed is False
        assert findings
        assert err["error_type"] == "dlp_blocked"


class TestMaskSensitiveText:
    """mask_sensitive_text() must cover every kind analyze_text() can flag — see the
    "same patterns" contract documented on both functions in dlp.py."""

    def test_empty_text_is_a_no_op(self):
        assert mask_sensitive_text("") == ""
        assert mask_sensitive_text(None) is None

    def test_masks_email(self):
        out = mask_sensitive_text("Contact me at jane.doe@example.org please")
        assert "jane.doe@example.org" not in out
        assert "[REDACTED_EMAIL]" in out
        assert "Contact me at" in out and "please" in out

    def test_masks_phone_with_enough_digits(self):
        out = mask_sensitive_text("Call me at +1 (555) 123-4567 tomorrow")
        assert "123-4567" not in out
        assert "[REDACTED_PHONE]" in out

    def test_does_not_mask_year_range_as_phone(self):
        out = mask_sensitive_text("Coverage for the period 2020-2024 was strong.")
        assert out == "Coverage for the period 2020-2024 was strong."

    def test_masks_jwt(self):
        fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abcdefghij"
        out = mask_sensitive_text(f"Here is my token: {fake_jwt}")
        assert fake_jwt not in out
        assert "[REDACTED_TOKEN]" in out

    def test_masks_bearer_token(self):
        out = mask_sensitive_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")
        assert "abcdefghijklmnopqrstuvwxyz012345" not in out
        assert "[REDACTED_TOKEN]" in out

    def test_masks_full_private_key_block_not_just_begin_marker(self):
        """The detection regex only checks for the BEGIN marker (cheap presence check),
        but masking must remove the whole armored block, or the key material right
        after a redacted BEGIN line would sail through untouched."""
        key_body = "MIIEowIBAAKCAQEA1234567890abcdefEXAMPLEKEYMATERIALONLY=="
        text = f"here you go:\n-----BEGIN RSA PRIVATE KEY-----\n{key_body}\n-----END RSA PRIVATE KEY-----\nthanks"
        out = mask_sensitive_text(text)
        assert key_body not in out
        assert "-----BEGIN" not in out
        assert "[REDACTED_PRIVATE_KEY]" in out
        assert "here you go:" in out and "thanks" in out

    def test_masks_password_assignment_but_keeps_keyword(self):
        out = mask_sensitive_text("password: SuperSecret123")
        assert "SuperSecret123" not in out
        assert "[REDACTED_PASSWORD]" in out
        assert "password" in out.lower()

    def test_masks_api_key_assignment_but_keeps_keyword(self):
        out = mask_sensitive_text("api_key=sk_live_abcdefghijklmnop")
        assert "sk_live_abcdefghijklmnop" not in out
        assert "[REDACTED_API_KEY]" in out
        assert "api_key" in out.lower()

    def test_masks_iban(self):
        out = mask_sensitive_text("My IBAN is DE89370400440532013000 for the transfer")
        assert "DE89370400440532013000" not in out
        assert "[REDACTED_IBAN]" in out

    def test_masks_valid_luhn_card_number(self):
        out = mask_sensitive_text("Card number: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in out
        assert "[REDACTED_CARD]" in out

    def test_does_not_label_luhn_invalid_digit_string_as_a_card(self):
        # Same length as a PAN but fails the Luhn checksum, so it must never get the
        # card-specific placeholder. It's still a 16-digit run though, which the
        # (deliberately broad) phone heuristic also matches — analyze_text has this
        # same overlap, flagging it as "phone" too — so it IS masked, just not as a card.
        text = "Reference number: 1234 5678 9012 3456"
        out = mask_sensitive_text(text)
        assert "[REDACTED_CARD]" not in out
        assert "1234 5678 9012 3456" not in out
        assert "[REDACTED_PHONE]" in out

    def test_masks_multiple_kinds_in_one_message(self):
        out = mask_sensitive_text("Email jane@example.org or call 555-987-6543")
        assert "jane@example.org" not in out
        assert "555-987-6543" not in out
        assert "[REDACTED_EMAIL]" in out
        assert "[REDACTED_PHONE]" in out

    def test_plain_text_is_unchanged(self):
        text = "How many volunteers are there in Kenya this year?"
        assert mask_sensitive_text(text) == text


class TestLogDlpAuditEvent:
    def test_no_findings_is_a_no_op(self, app, db_session):
        with app.test_request_context():
            log_dlp_audit_event(
                user_id=None,
                action="allowed",
                transport="http",
                endpoint_path="/api/ai/v2/chat",
                client="backoffice",
                conversation_id=None,
                client_message_id=None,
                allow_sensitive=False,
                findings=[],
            )
            from app.models import SecurityEvent

            assert SecurityEvent.query.filter_by(event_type="ai_dlp_sensitive_detected").count() == 0

    def test_writes_security_event_without_raw_message(self, app, db_session):
        secret_email = "totally.secret@example.org"
        with app.test_request_context():
            findings = analyze_text(f"contact {secret_email}")
            log_dlp_audit_event(
                user_id=None,
                action="blocked",
                transport="http",
                endpoint_path="/api/ai/v2/chat",
                client="backoffice",
                conversation_id="conv-123",
                client_message_id="client-msg-1",
                allow_sensitive=False,
                findings=findings,
            )
            from app.models import SecurityEvent

            event = SecurityEvent.query.filter_by(event_type="ai_dlp_sensitive_detected").first()
            assert event is not None
            assert event.severity in {"low", "medium", "high"}
            # SECURITY: raw message content must never be persisted in the audit trail.
            assert secret_email not in str(event.context_data)
            assert secret_email not in (event.description or "")

    def test_high_severity_kind_marks_event_high_when_blocked(self, app, db_session):
        with app.test_request_context():
            findings = analyze_text("password: SuperSecret123")
            log_dlp_audit_event(
                user_id=None,
                action="blocked",
                transport="http",
                endpoint_path="/api/ai/v2/chat",
                client="backoffice",
                conversation_id=None,
                client_message_id=None,
                allow_sensitive=False,
                findings=findings,
            )
            from app.models import SecurityEvent

            event = SecurityEvent.query.filter_by(event_type="ai_dlp_sensitive_detected").first()
            assert event is not None
            assert event.severity == "high"
