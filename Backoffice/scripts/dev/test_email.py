"""
Test script for email sending functionality.
Sends a test email to verify the email configuration is working correctly.

Usage:
  python scripts/test_email.py
  python scripts/test_email.py path/to/body.html
  TEST_EMAIL_HTML_FILE=path/to/body.html python scripts/test_email.py

Optional env:
  TEST_EMAIL_RECIPIENT, TEST_EMAIL_SUBJECT, FLASK_CONFIG
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils.email_client import send_email
import requests
import json
import base64


def _load_html_content(argv):
    """HTML body: CLI path, TEST_EMAIL_HTML_FILE, or built-in minimal default."""
    path = None
    if len(argv) > 1 and argv[1] and not argv[1].startswith("-"):
        path = argv[1]
    if not path:
        path = os.environ.get("TEST_EMAIL_HTML_FILE", "").strip()
    if path:
        p = os.path.abspath(path)
        if not os.path.isfile(p):
            logger.error("HTML file not found: %s", p)
            sys.exit(2)
        with open(p, encoding="utf-8") as f:
            return f.read()
    return None


def test_email_sending():
    """Test email sending to a configured recipient (set in script)."""

    # Create Flask app instance
    app = create_app(os.getenv('FLASK_CONFIG'))

    # Recipient email
    recipient = os.environ.get("TEST_EMAIL_RECIPIENT", "test@example.com")

    # Test email content
    subject = os.environ.get("TEST_EMAIL_SUBJECT", "Test Email - Humanitarian Databank")
    from_file = _load_html_content(sys.argv)
    if from_file is not None:
        html_content = from_file
        logger.info("Using HTML from file (%d chars)", len(html_content))
    else:
        html_content = """<html>
<body>
<h2>Email Test</h2>
<p>This is a test email from the Humanitarian Databank backend system.</p>
<p>If you received this email, the email sending functionality is working correctly.</p>
<hr>
<p><small>This is an automated test message.</small></p>
</body>
</html>"""
    text_content = """Email Test

This is a test email from the Humanitarian Databank backend system.
If you received this email, the email sending functionality is working correctly.

This is an automated test message."""

    with app.app_context():
        logger.info("=" * 60)
        logger.info("Email Test Script")
        logger.info("=" * 60)
        logger.info("Recipient: %s", recipient)
        logger.info("Subject: %s", subject)
        logger.info("")

        # Check configuration
        sender = app.config.get("MAIL_DEFAULT_SENDER")
        api_key = app.config.get("EMAIL_API_KEY")
        api_url = app.config.get("EMAIL_API_URL")
        flask_config = app.config.get("FLASK_CONFIG", "")

        logger.info("Configuration Check:")
        logger.info("  FLASK_CONFIG: %s", flask_config if flask_config else 'NOT SET (defaults to staging)')
        logger.info("  MAIL_DEFAULT_SENDER: %s", sender if sender else 'NOT SET')
        logger.info("  EMAIL_API_KEY: %s", 'SET' if api_key else 'NOT SET')
        if api_key:
            logger.info("    Key length: %d", len(api_key))
            logger.info("    Key prefix: %s...", api_key[:15])
        logger.info("  EMAIL_API_URL: %s", api_url if api_url else 'NOT SET')
        logger.info("")

        if not sender:
            logger.error("ERROR: MAIL_DEFAULT_SENDER is not configured!")
            logger.info("   Please set MAIL_DEFAULT_SENDER in your environment variables.")
            return False

        if not api_key:
            logger.error("ERROR: EMAIL_API_KEY is not configured!")
            logger.info("   Please set EMAIL_API_KEY or EMAIL_API_KEY_STG in your environment variables.")
            return False

        if not api_url:
            logger.error("ERROR: EMAIL_API_URL is not configured!")
            logger.info("   Please set EMAIL_API_URL_STG or EMAIL_API_URL_PROD in your environment variables.")
            return False

        logger.info("Attempting to send email...")
        logger.info("")
        logger.info("Trying with HTML only (no text field)...")

        try:
            # Try first without text field - some APIs don't accept it
            success = send_email(
                subject=subject,
                recipients=[recipient],
                html=html_content
                # text=text_content  # Try without text field first
            )

            if not success:
                logger.info("First attempt failed. Trying with text field...")
                success = send_email(
                    subject=subject,
                    recipients=[recipient],
                    html=html_content,
                    text=text_content
                )

            if not success:
                logger.info("Standard send_email failed. Trying direct API call with different formats...")
                success = test_direct_api_call(app, sender, recipient, subject, html_content)

            if success:
                logger.info("SUCCESS: Email sent successfully!")
                logger.info("   Check the inbox for: %s", recipient)
                return True
            else:
                logger.error("FAILED: Email sending returned False")
                logger.info("   Check the application logs for more details.")
                return False

        except Exception as e:
            logger.error("ERROR: Exception occurred while sending email: %s", e)
            import traceback
            traceback.print_exc()
            return False


def test_direct_api_call(app, sender, recipient, subject, html_content):
    """Test direct API calls with different payload formats and auth methods"""
    api_key = app.config.get("EMAIL_API_KEY")
    api_url_base = app.config.get("EMAIL_API_URL", "")

    # Clean the base URL (remove any existing query params)
    from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
    parsed = urlparse(api_url_base)
    # Remove apiKey if present
    query_params = parse_qs(parsed.query)
    if 'apiKey' in query_params:
        del query_params['apiKey']
    clean_query = urlencode(query_params, doseq=True) if query_params else ''
    clean_base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', clean_query, ''))

    # Base64-encoded payload (matching the actual API format)
    base64_payload = {
        "FromAsBase64": str(base64.b64encode(sender.encode("utf-8")), "utf-8"),
        "ToAsBase64": str(base64.b64encode(recipient.encode("utf-8")), "utf-8"),
        "CcAsBase64": "",
        "BccAsBase64": "",
        "SubjectAsBase64": str(base64.b64encode(subject.encode("utf-8")), "utf-8"),
        "BodyAsBase64": str(base64.b64encode(html_content.encode("utf-8")), "utf-8"),
        "IsBodyHtml": True,
        "TemplateName": "",
        "TemplateLanguage": "",
    }

    # Try query parameter only (API requires query parameter, not headers)
    test_cases = [
        {
            "name": "API key in query parameter (base64 format)",
            "url": f"{clean_base}?apiKey={api_key}",
            "headers": {"Content-Type": "application/json"},
            "payload": base64_payload
        },
    ]

    for test_case in test_cases:
        logger.info("  Trying: %s", test_case['name'])
        try:
            resp = requests.post(
                test_case['url'],
                headers=test_case['headers'],
                json=test_case['payload'],
                timeout=15
            )
            logger.info("    Status: %s", resp.status_code)
            if resp.text:
                logger.info("    Response: %s", resp.text[:200])

            if 200 <= resp.status_code < 300:
                logger.info("  SUCCESS with %s!", test_case['name'])
                return True
        except Exception as e:
            logger.error("    Error: %s", e)

    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    success = test_email_sending()
    sys.exit(0 if success else 1)
