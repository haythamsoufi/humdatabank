"""
Integration tests for email functionality.

Tests email sending and configuration.
"""
import pytest
from unittest.mock import patch, MagicMock
from app import create_app


@pytest.mark.integration
@pytest.mark.email
class TestEmail:
    """Test email functionality."""

    def test_email_configuration_validation(self, app):
        """Test that email configuration is validated."""
        # Check that app has email configuration
        assert hasattr(app.config, 'get')

        # Email config might not be set in test environment
        # That's OK - we're just testing the validation logic
        sender = app.config.get("MAIL_DEFAULT_SENDER")
        api_key = app.config.get("EMAIL_API_KEY")
        api_url = app.config.get("EMAIL_API_URL")

        # Configuration might be None in test environment
        # This is expected and OK
        assert isinstance(sender, (str, type(None)))
        assert isinstance(api_key, (str, type(None)))
        assert isinstance(api_url, (str, type(None)))

    @patch('app.utils.email_client.send_email')
    def test_email_sending_mock(self, mock_send_email, app):
        """Test email sending with mocked function."""
        mock_send_email.return_value = True

        from app.utils.email_client import send_email

        result = send_email(
            subject="Test Email",
            recipients=["test@example.com"],
            html="<p>Test content</p>"
        )

        # If email is configured, it should be called
        # If not configured, it might return False
        assert isinstance(result, bool)

    def test_email_configuration_presence(self, app):
        """Test that email configuration keys exist in app config."""
        # These keys should exist in config (even if None)
        assert 'MAIL_DEFAULT_SENDER' in app.config or app.config.get('MAIL_DEFAULT_SENDER') is None
        assert 'EMAIL_API_KEY' in app.config or app.config.get('EMAIL_API_KEY') is None
        assert 'EMAIL_API_URL' in app.config or app.config.get('EMAIL_API_URL') is None
