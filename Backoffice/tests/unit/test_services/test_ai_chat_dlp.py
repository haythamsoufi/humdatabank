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

from app.services.ai.chat.dlp import analyze_text, evaluate_ai_message, log_dlp_audit_event


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
        allowed, err, findings = evaluate_ai_message(
            message="email me at a@b.com", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert findings == []

    def test_clean_message_is_allowed(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        allowed, err, findings = evaluate_ai_message(
            message="What is the volunteer count for Kenya?", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert findings == []

    def test_warn_mode_allows_but_reports_findings(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "warn"
        allowed, err, findings = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is True
        assert err is None
        assert len(findings) == 1

    def test_block_mode_blocks_regardless_of_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        allowed, err, findings = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=True
        )
        assert allowed is False
        assert err["error_type"] == "dlp_blocked"
        assert findings

    def test_confirm_mode_blocks_without_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"
        assert findings

    def test_confirm_mode_allows_with_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=True
        )
        assert allowed is True
        assert err is None
        assert findings

    def test_invalid_mode_falls_back_to_confirm(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "not-a-real-mode"
        allowed, _err, findings = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is False
        assert findings

    def test_dlp_error_payload_never_contains_raw_message(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        secret_email = "very.secret.person@example.org"
        _allowed, err, _findings = evaluate_ai_message(
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
        allowed, err, findings = evaluate_ai_message(message=message, allow_sensitive=False)
        assert allowed is False
        assert findings
        assert err["error_type"] == "dlp_blocked"


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
