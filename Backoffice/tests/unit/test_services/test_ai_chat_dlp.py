"""Unit tests for app.services.ai.chat.dlp — the regex-based AI chat DLP guard.

Focus areas:
- analyze_text() / mask_sensitive_text(): each finding kind, the credential formats people
  paste (env files, JSON, connection strings, PEM blocks), and the numeric text this
  databank's chat is full of (years, figures, tables, dates) staying unflagged.
- Masking is idempotent: masked text rescans clean, so an edited or re-sent message is not
  challenged over its own placeholders.
- evaluate_ai_message(): warn/confirm/block modes, contact details auto-masked in confirm
  mode, the form-builder contact-detail exemption, and the enabled toggle.
- Regression: the scan window (AI_DLP_MAX_SCAN_CHARS) must cover the full range of messages
  the form-builder panel is allowed to send (AI_FORM_BUILDER_MAX_MESSAGE_CHARS).
- screen_ai_message() / log_dlp_audit_event(): the audit event records the action taken and
  never persists the raw message or matched substrings.
- mask_conversation_history(): client-supplied history is masked on user turns only.
"""

import time

import pytest

from app.services.ai.chat.dlp import (
    analyze_text,
    evaluate_ai_message,
    log_dlp_audit_event,
    mask_conversation_history,
    mask_sensitive_text,
    screen_ai_message,
)

_DLP_CONFIG_KEYS = ("AI_DLP_ENABLED", "AI_DLP_MODE", "AI_DLP_AUTO_MASK_KINDS", "AI_DLP_MAX_SCAN_CHARS")

# Split so repository secret scanners don't flag these fixtures as leaked credentials.
AWS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
GOOGLE_KEY = "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
SLACK_TOKEN = "xoxb-" + "1234567890-abcdefghij"
STRIPE_KEY = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"

# (text, kind, a substring of the secret that must not survive masking)
CREDENTIAL_CASES = [
    pytest.param(
        "OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012",
        "api_key_or_secret",
        "abc123def456",
        id="env-provider-key",
    ),
    pytest.param("CLIENT_SECRET=Zq8vR2xL9mN4pT7w", "api_key_or_secret", "Zq8vR2xL9mN4pT7w", id="env-client-secret"),
    pytest.param('{"api_key": "a1b2c3d4e5f6g7h8"}', "api_key_or_secret", "a1b2c3d4e5f6g7h8", id="json-api-key"),
    pytest.param(
        '{"password": "correct horse battery staple"}', "password", "battery staple", id="json-passphrase"
    ),
    pytest.param(
        "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=abc123DEF456ghi789==;"
        "EndpointSuffix=core.windows.net",
        "api_key_or_secret",
        "abc123DEF456ghi789",
        id="azure-connection-string",
    ),
    pytest.param(
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\nMIIFHzBJBgkqhkiG9w0BBQ0w\n-----END ENCRYPTED PRIVATE KEY-----",
        "private_key",
        "MIIFHzBJBgkqhkiG9w0BBQ0w",
        id="encrypted-private-key",
    ),
    pytest.param(
        "here:\n-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
        "private_key",
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
        id="private-key-without-end-marker",
    ),
    pytest.param("passphrase: correct horse battery staple", "password", "battery staple", id="passphrase"),
    pytest.param("postgresql://app:S3cr3tPass@db.internal:5432/prod", "password", "S3cr3tPass", id="database-url"),
    pytest.param("rediss://:hunter2pass@cache.example.net:6380", "password", "hunter2pass", id="redis-url"),
    pytest.param(
        "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==", "password", "dXNlcjpwYXNzd29yZDEyMw", id="basic-auth"
    ),
    pytest.param(f"key id {AWS_KEY_ID} in the config", "api_key_or_secret", AWS_KEY_ID, id="aws-key-id"),
    pytest.param(f"token {GITHUB_TOKEN} here", "api_key_or_secret", GITHUB_TOKEN, id="github-token"),
    pytest.param(STRIPE_KEY, "api_key_or_secret", STRIPE_KEY, id="stripe-key"),
    pytest.param(SLACK_TOKEN, "api_key_or_secret", SLACK_TOKEN, id="slack-token"),
    pytest.param(f"maps key {GOOGLE_KEY}", "api_key_or_secret", GOOGLE_KEY, id="google-key"),
    pytest.param("sk-ant-api03-abcdefghij1234567890", "api_key_or_secret", "abcdefghij1234567890", id="anthropic"),
]

NOT_SENSITIVE = [
    pytest.param("How many volunteers are there in Kenya this year?", id="plain-question"),
    pytest.param("Volunteers in 2019 2020 2021 2022 2023", id="year-list"),
    pytest.param("Coverage for the period 2020-2024 was strong.", id="year-range"),
    pytest.param("Population 1 234 567 890 in total", id="space-grouped-figure"),
    pytest.param("Population 1\u00a0234\u00a0567\u00a0890 in total", id="nbsp-grouped-figure"),
    pytest.param("Budget of 125.000.000 CHF", id="dot-grouped-figure"),
    pytest.param("The total was 123456789012 people", id="big-integer"),
    pytest.param("Kenya\t120000\t135000\t150000", id="tab-separated-row"),
    pytest.param("2019 120 000 2020 135 000", id="year-labelled-figures"),
    pytest.param("Accounts 1200 1500 1800", id="four-digit-figures"),
    pytest.param("Branches 3 5 2 0 1 4 2 0 1", id="row-of-small-figures"),
    pytest.param("Kenya 12 50 30 70 100 120", id="row-of-figures"),
    pytest.param("120  135  150  165", id="column-aligned-figures"),
    pytest.param("0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0", id="row-of-zeros"),
    pytest.param("Between 01.02.2024 - 05.02.2024", id="date-range"),
    pytest.param("Server 192.168.100.200", id="ipv4"),
    pytest.param("Reference number: 1234 5678 9012 3456", id="luhn-invalid-16-digits"),
    pytest.param("The secret to success is volunteers", id="prose-secret"),
    pytest.param("my password is too weak to share", id="prose-password"),
    pytest.param("password is required to sign in", id="prose-password-required"),
    pytest.param("secret: volunteers", id="secret-label-prose-value"),
    pytest.param("Set password: <your password>", id="placeholder-angle-brackets"),
    pytest.param("api_key=${OPENAI_API_KEY}", id="placeholder-env-var"),
    pytest.param("password: ****", id="placeholder-stars"),
    pytest.param("api_key: xxxxxxxxxxxx", id="placeholder-x"),
]

PHONE_NUMBERS = [
    "+41 22 730 42 22",
    "0041 22 730 42 22",
    "022 730 42 22",
    "(555) 123-4567",
    "555-123-4567",
    "06 12 34 56 78",
    "+1 (555) 123-4567",
    "8 (495) 123-45-67",
]

MASKED_TEXTS = [p.values[0] for p in CREDENTIAL_CASES] + [
    "Contact me at jane.doe@example.org please",
    "Call +41 22 730 42 22 tomorrow",
    "Here is my token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abcdefghij",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    "password: SuperSecret123",
    "IBAN DE89 3704 0044 0532 0130 00 BIC COBADEFFXXX",
    "Card 4111 1111 1111 1111 expires soon",
]


@pytest.fixture
def app_ctx(app):
    """The session-scoped app, with its DLP settings restored after the test."""
    saved = {k: app.config[k] for k in _DLP_CONFIG_KEYS if k in app.config}
    with app.app_context():
        yield app
    for k in _DLP_CONFIG_KEYS:
        if k in saved:
            app.config[k] = saved[k]
        else:
            app.config.pop(k, None)


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

    def test_counts_each_occurrence(self):
        findings = analyze_text("a@b.com and c@d.org")
        assert [(f.kind, f.count) for f in findings] == [("email", 2)]

    def test_skip_kinds_ignores_those_kinds_only(self):
        findings = analyze_text("mail a@b.com, password: SuperSecret123", skip_kinds=("email", "phone"))
        assert [f.kind for f in findings] == ["password"]


class TestCredentialFormats:
    @pytest.mark.parametrize("text, kind, secret", CREDENTIAL_CASES)
    def test_credential_is_detected_and_masked(self, text, kind, secret):
        assert kind in {f.kind for f in analyze_text(text)}
        assert secret not in mask_sensitive_text(text)

    def test_unterminated_private_key_is_masked_to_the_end_of_the_text(self):
        """A paste cut off before its END marker is key material all the way down."""
        text = "here:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\nb3BlbnNzaC1rZXktdjEAAAAA"
        assert mask_sensitive_text(text) == "here:\n[REDACTED_PRIVATE_KEY]"

    def test_password_stated_in_a_sentence_is_masked(self):
        assert mask_sensitive_text("my password is qweqwe2123") == "my password is [REDACTED_PASSWORD]"

    def test_whole_passphrase_is_masked_not_just_its_first_word(self):
        assert mask_sensitive_text("passphrase: correct horse battery staple") == "passphrase: [REDACTED_PASSWORD]"

    def test_only_the_value_of_an_assignment_is_masked(self):
        text = "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=abc123DEF456ghi789==;EndpointSuffix=x"
        assert mask_sensitive_text(text) == (
            "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=[REDACTED_API_KEY];EndpointSuffix=x"
        )

    def test_url_credentials_keep_the_rest_of_the_url(self):
        out = mask_sensitive_text("postgresql://app:S3cr3tPass@db.internal:5432/prod")
        assert out == "postgresql://app:[REDACTED_PASSWORD]@db.internal:5432/prod"


class TestNotSensitive:
    """Numbers and prose the databank chat sees all the time must pass through untouched."""

    @pytest.mark.parametrize("text", NOT_SENSITIVE)
    def test_is_not_flagged_or_changed(self, text):
        assert analyze_text(text) == []
        assert mask_sensitive_text(text) == text


class TestPhoneNumbers:
    @pytest.mark.parametrize("number", PHONE_NUMBERS)
    def test_phone_number_is_masked(self, number):
        assert mask_sensitive_text(f"Call {number} today") == "Call [REDACTED_PHONE] today"


class TestMaskingIsIdempotent:
    """The masked text is what the user sees, edits and re-sends: it must rescan clean."""

    @pytest.mark.parametrize("text", MASKED_TEXTS)
    def test_masked_text_rescans_clean(self, text):
        masked = mask_sensitive_text(text)
        assert masked != text
        assert analyze_text(masked) == []
        assert mask_sensitive_text(masked) == masked


class TestScanPerformance:
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("a." * 32000, id="email-local-part"),
            pytest.param("a@" * 32000, id="at-signs"),
            pytest.param("1 " * 32000, id="digit-groups"),
            pytest.param("password: " * 6400, id="password-labels"),
        ],
    )
    def test_long_adversarial_input_scans_quickly(self, text):
        start = time.perf_counter()
        mask_sensitive_text(text)
        assert time.perf_counter() - start < 2.0


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

    @pytest.mark.parametrize("value", ["false", "0", "no", "off"])
    def test_disabled_by_string_config_value(self, app_ctx, value):
        """Settings read from the environment arrive as strings; "false" is not truthy."""
        app_ctx.config["AI_DLP_ENABLED"] = value
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=False
        )
        assert (allowed, err, findings) == (True, None, [])
        assert safe_message == "password: SuperSecret123"

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

    def test_warn_mode_masks_credentials_too(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "warn"
        allowed, err, _findings, safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=False
        )
        assert (allowed, err) == (True, None)
        assert safe_message == "password: [REDACTED_PASSWORD]"

    def test_block_mode_blocks_regardless_of_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=True
        )
        assert allowed is False
        assert err["error_type"] == "dlp_blocked"
        assert findings

    def test_confirm_mode_requires_confirmation_for_credentials(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"
        assert findings

    def test_confirm_mode_allows_with_allow_sensitive(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=True
        )
        assert allowed is True
        assert err is None
        assert findings
        assert safe_message == "password: [REDACTED_PASSWORD]"

    def test_confirm_mode_with_allow_sensitive_masks_instead_of_sending_raw(self, app_ctx):
        """Regression: confirming past the DLP dialog used to send the raw message
        as-is ("send anyway"). It must now mask every flagged span instead."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="my email is a@b.com, call me on 555-123-4567, password: SuperSecret123",
            allow_sensitive=True,
        )
        assert allowed is True
        assert err is None
        assert findings
        assert "a@b.com" not in safe_message
        assert "555-123-4567" not in safe_message
        assert "SuperSecret123" not in safe_message
        assert "[REDACTED_EMAIL]" in safe_message
        assert "[REDACTED_PHONE]" in safe_message
        assert "[REDACTED_PASSWORD]" in safe_message
        # Surrounding non-sensitive text is preserved verbatim.
        assert "my email is" in safe_message
        assert "call me on" in safe_message

    def test_confirm_mode_auto_masks_contact_details_without_asking(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, findings, safe_message = evaluate_ai_message(
            message="my email is a@b.com, call me on 555-123-4567", allow_sensitive=False
        )
        assert (allowed, err) == (True, None)
        assert {f.kind for f in findings} == {"email", "phone"}
        assert safe_message == "my email is [REDACTED_EMAIL], call me on [REDACTED_PHONE]"

    def test_confirm_mode_asks_when_contact_details_come_with_a_credential(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, err, _findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com, password: SuperSecret123", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"

    def test_auto_mask_kinds_is_configurable(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        app_ctx.config["AI_DLP_AUTO_MASK_KINDS"] = ()
        allowed, err, _findings, _safe_message = evaluate_ai_message(
            message="my email is a@b.com", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"

        app_ctx.config["AI_DLP_AUTO_MASK_KINDS"] = "email, password"
        allowed, err, _findings, safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=False
        )
        assert (allowed, err) == (True, None)
        assert safe_message == "password: [REDACTED_PASSWORD]"

    def test_form_builder_assistant_keeps_contact_details_even_in_block_mode(self, app_ctx):
        """Regression: the form-builder panel routinely appends the full extracted text
        of an *imported* questionnaire to the user's message (see
        form-builder-ai.js's _appendAttachmentBlockToMessage) — e.g. real staff names,
        emails, and reference numbers that are part of the *source document*, not a
        secret the user is pasting into chat. DLP must not block/mask its contact details,
        the same way AIChatEngine already exempts form-builder messages from PII scrubbing
        before the LLM call (_scrub_message_for_llm)."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        message = (
            "Build a form template from this attached questionnaire.\n\n"
            '--- Imported questionnaire text from "NSD investment monitoring.pdf" ---\n\n'
            "NS Focal Person: Dr. Jane Doe, jane.doe@example.org, +41 22 730 42 22, "
            "reporting period 17/03/2025-16/09/2026"
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

    def test_form_builder_assistant_still_screens_credentials(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        message = "Focal point jane.doe@example.org, api_key=Zq8vR2xL9mN4pT7w"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message=message, allow_sensitive=False, form_builder_assistant=True
        )
        assert allowed is False
        assert err["error_type"] == "dlp_blocked"
        assert [f.kind for f in findings] == ["api_key_or_secret"]

        app_ctx.config["AI_DLP_MODE"] = "confirm"
        allowed, _err, _findings, safe_message = evaluate_ai_message(
            message=message, allow_sensitive=True, form_builder_assistant=True
        )
        assert allowed is True
        assert safe_message == "Focal point jane.doe@example.org, api_key=[REDACTED_API_KEY]"

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
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=False
        )
        assert allowed is False
        assert err["error_type"] == "dlp_requires_confirmation"
        assert findings

    @pytest.mark.parametrize("secret", ["very.secret.person@example.org", "SuperSecret123"])
    def test_dlp_error_payload_never_contains_raw_message(self, app_ctx, secret):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        _allowed, err, _findings, _safe_message = evaluate_ai_message(
            message="my email is very.secret.person@example.org, password: SuperSecret123",
            allow_sensitive=False,
        )
        assert secret not in str(err)

    def test_error_payload_names_the_finding_kinds(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        _allowed, err, _findings, _safe_message = evaluate_ai_message(
            message="password: SuperSecret123, mail a@b.com", allow_sensitive=False
        )
        assert err["error"] == (
            "Sensitive information detected (password, email address). Remove it and send your message again."
        )
        assert err["dlp"] == {
            "sensitive": True,
            "findings": [{"kind": "password", "count": 1}, {"kind": "email", "count": 1}],
            "recommendation": "remove_or_confirm",
        }

    def test_block_payload_has_no_confirm_recommendation(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        _allowed, err, _findings, _safe_message = evaluate_ai_message(
            message="password: SuperSecret123", allow_sensitive=True
        )
        assert err["error_type"] == "dlp_blocked"
        assert err["dlp"] == {"sensitive": True, "findings": [{"kind": "password", "count": 1}]}

    def test_scan_window_covers_full_form_builder_message_length(self, app_ctx):
        """Regression: AI_DLP_MAX_SCAN_CHARS previously defaulted to 12000 while the
        form-builder panel allows messages up to AI_FORM_BUILDER_MAX_MESSAGE_CHARS (16000
        by default) — sensitive content placed after char 12000 was silently invisible to
        DLP. Form-builder messages are only exempt from contact details, so a credential at
        the tail of a max-length one must still be caught."""
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "block"
        max_scan = int(app_ctx.config.get("AI_DLP_MAX_SCAN_CHARS", 16000))
        form_builder_cap = int(app_ctx.config.get("AI_FORM_BUILDER_MAX_MESSAGE_CHARS", 16000))
        assert max_scan >= form_builder_cap

        padding = "x" * (form_builder_cap - 40)
        message = f"{padding} api_key=Zq8vR2xL9mN4pT7w"
        allowed, err, findings, _safe_message = evaluate_ai_message(
            message=message, allow_sensitive=False, form_builder_assistant=True
        )
        assert allowed is False
        assert [f.kind for f in findings] == ["api_key_or_secret"]
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
        """Masking must remove the whole armored block, or the key material right after
        a redacted BEGIN line would sail through untouched."""
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

    def test_masks_spaced_iban_but_not_the_word_after_it(self):
        out = mask_sensitive_text("IBAN DE89 3704 0044 0532 0130 00 BIC COBADEFFXXX")
        assert out == "IBAN [REDACTED_IBAN] BIC COBADEFFXXX"

    def test_does_not_mask_iban_shape_with_a_bad_checksum(self):
        assert mask_sensitive_text("DE00 3704 0044 0532 0130 00") == "DE00 3704 0044 0532 0130 00"

    def test_masks_valid_luhn_card_number(self):
        out = mask_sensitive_text("Card number: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in out
        assert "[REDACTED_CARD]" in out

    def test_card_mask_keeps_the_following_space(self):
        assert mask_sensitive_text("Card 4111 1111 1111 1111 expires soon") == "Card [REDACTED_CARD] expires soon"

    def test_leaves_luhn_invalid_reference_number_alone(self):
        # Card-length but fails Luhn, and too long and evenly grouped for a phone number.
        text = "Reference number: 1234 5678 9012 3456"
        assert mask_sensitive_text(text) == text

    def test_masks_multiple_kinds_in_one_message(self):
        out = mask_sensitive_text("Email jane@example.org or call 555-987-6543")
        assert "jane@example.org" not in out
        assert "555-987-6543" not in out
        assert "[REDACTED_EMAIL]" in out
        assert "[REDACTED_PHONE]" in out

    def test_skip_kinds_leaves_those_kinds_unmasked(self):
        out = mask_sensitive_text("mail a@b.com, password: SuperSecret123", skip_kinds=("email",))
        assert out == "mail a@b.com, password: [REDACTED_PASSWORD]"

    def test_plain_text_is_unchanged(self):
        text = "How many volunteers are there in Kenya this year?"
        assert mask_sensitive_text(text) == text


class TestMaskConversationHistory:
    def test_masks_user_turns_in_both_history_shapes(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        history = [
            {"isUser": True, "message": "password: SuperSecret123"},
            {"isUser": False, "message": "Noted, I will not repeat jane@example.org"},
            {"role": "user", "content": "mail jane@example.org"},
            {"role": "assistant", "content": "ok"},
        ]
        out = mask_conversation_history(history)
        assert out == [
            {"isUser": True, "message": "password: [REDACTED_PASSWORD]"},
            history[1],
            {"role": "user", "content": "mail [REDACTED_EMAIL]"},
            history[3],
        ]
        assert history[0]["message"] == "password: SuperSecret123"

    def test_keeps_other_fields_and_passes_non_dict_entries_through(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        history = [{"isUser": True, "message": "a@b.com", "timestamp": 1}, "junk", None]
        assert mask_conversation_history(history) == [
            {"isUser": True, "message": "[REDACTED_EMAIL]", "timestamp": 1},
            "junk",
            None,
        ]

    def test_form_builder_keeps_contact_details_but_masks_credentials(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = True
        history = [{"isUser": True, "message": "Focal point jane@example.org, api_key=Zq8vR2xL9mN4pT7w"}]
        out = mask_conversation_history(history, form_builder_assistant=True)
        assert out == [{"isUser": True, "message": "Focal point jane@example.org, api_key=[REDACTED_API_KEY]"}]

    def test_disabled_dlp_returns_history_unchanged(self, app_ctx):
        app_ctx.config["AI_DLP_ENABLED"] = False
        history = [{"isUser": True, "message": "password: SuperSecret123"}]
        assert mask_conversation_history(history) == history

    def test_empty_history(self, app_ctx):
        assert mask_conversation_history(None) == []
        assert mask_conversation_history([]) == []


class TestScreenAiMessage:
    @staticmethod
    def _screen(message, *, allow_sensitive=False):
        return screen_ai_message(
            message=message,
            allow_sensitive=allow_sensitive,
            form_builder_assistant=False,
            user_id=None,
            transport="http",
            endpoint_path="/api/ai/v1/chat",
            client="backoffice",
            conversation_id="conv-123",
            client_message_id="client-msg-1",
        )

    @staticmethod
    def _events():
        from app.models import SecurityEvent

        return SecurityEvent.query.filter_by(event_type="ai_dlp_sensitive_detected").all()

    @pytest.mark.parametrize(
        "mode, message, allow_sensitive, action, severity",
        [
            ("confirm", "my email is a@b.com", False, "auto_masked", "low"),
            ("confirm", "password: SuperSecret123", False, "confirm_required", "high"),
            ("confirm", "password: SuperSecret123", True, "sent_masked", "high"),
            ("warn", "password: SuperSecret123", False, "auto_masked", "medium"),
            ("block", "my email is a@b.com", False, "blocked", "medium"),
        ],
    )
    def test_audit_event_records_the_action_taken(
        self, app_ctx, db_session, mode, message, allow_sensitive, action, severity
    ):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = mode
        with app_ctx.test_request_context():
            self._screen(message, allow_sensitive=allow_sensitive)
            events = self._events()
        assert len(events) == 1
        assert events[0].context_data["action"] == action
        assert events[0].severity == severity
        assert "SuperSecret123" not in str(events[0].context_data)

    def test_returns_the_evaluate_ai_message_verdict(self, app_ctx, db_session):
        app_ctx.config["AI_DLP_ENABLED"] = True
        app_ctx.config["AI_DLP_MODE"] = "confirm"
        with app_ctx.test_request_context():
            allowed, err, findings, safe_message = self._screen("password: SuperSecret123", allow_sensitive=True)
        assert (allowed, err) == (True, None)
        assert [f.kind for f in findings] == ["password"]
        assert safe_message == "password: [REDACTED_PASSWORD]"

    def test_clean_message_writes_no_event(self, app_ctx, db_session):
        app_ctx.config["AI_DLP_ENABLED"] = True
        with app_ctx.test_request_context():
            allowed, _err, _findings, _safe_message = self._screen("How many volunteers are there in Kenya?")
            assert allowed is True
            assert self._events() == []


class TestLogDlpAuditEvent:
    def test_no_findings_is_a_no_op(self, app, db_session):
        with app.test_request_context():
            log_dlp_audit_event(
                user_id=None,
                action="allowed",
                transport="http",
                endpoint_path="/api/ai/v1/chat",
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
                endpoint_path="/api/ai/v1/chat",
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
                endpoint_path="/api/ai/v1/chat",
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
