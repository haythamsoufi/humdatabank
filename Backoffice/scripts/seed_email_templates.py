#!/usr/bin/env python
"""
Seed script: populate email & notification templates (unified).

The same templates are used for both system emails and the Notifications Center.
Run from the Backoffice directory:

    python scripts/seed_email_templates.py          # seed everything
    python scripts/seed_email_templates.py --force   # overwrite existing values

Alternatively, via Flask CLI (from Backoffice/):

    flask seed-email-templates
    flask seed-email-templates --force
"""

import argparse
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure the Backoffice package is importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ═══════════════════════════════════════════════════════════════════════
# Default email templates (Jinja2 HTML used by the email service).
# These are the same defaults that live as inline fallbacks in
# app/utils/email_service.py; storing them in the DB lets admins
# customise them via System Configuration → Emails.
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_EMAIL_TEMPLATES = {

    # ── Indicator Suggestion Confirmation ────────────────────────────
    "email_template_suggestion_confirmation": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Indicator Suggestion Confirmation</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #1976d2; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
        .highlight { background-color: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; margin: 15px 0; }
        .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ org_name }}</h1>
            <h2>Indicator Suggestion Confirmation</h2>
        </div>
        <div class="content">
            <p>Dear {{ submitter_name }},</p>
            <p>Thank you for submitting your indicator suggestion to {{ org_name }}. We have received your submission and it is currently under review.</p>
            <div class="highlight">
                <strong>Submission Details:</strong><br>
                <strong>Type:</strong> {{ suggestion_type_display }}<br>
                <strong>Indicator Name:</strong> {{ indicator_name }}<br>
                <strong>Submitted:</strong> {{ submitted_date }}
            </div>
            <div class="details">
                <h3>Suggestion Details:</h3>
                {{ suggestion_details | safe }}
            </div>
            <div class="details">
                <h3>What happens next?</h3>
                <ul>
                    <li>Our team will review your suggestion within 5-7 business days</li>
                    <li>If approved, the indicator will be added to our database</li>
                    <li>If we need additional information, we'll contact you at this email address</li>
                    <li>You'll receive a final notification once the review is complete</li>
                </ul>
            </div>
            <p>If you have any questions about your submission, please don't hesitate to contact us.</p>
            <p>Best regards,<br>The {{ org_name }} Team</p>
        </div>
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>"""
    },

    # ── Admin Notification (new suggestion) ──────────────────────────
    "email_template_admin_notification": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>New Indicator Suggestion</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #1976d2; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
        .highlight { background-color: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; margin: 15px 0; }
        .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
        .action-button { display: inline-block; background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ org_name }}</h1>
            <h2>New Indicator Suggestion</h2>
        </div>
        <div class="content">
            <p>A new indicator suggestion has been submitted and requires review.</p>
            <div class="highlight">
                <strong>Submission Details:</strong><br>
                <strong>Submitter:</strong> {{ submitter_name }} ({{ submitter_email }})<br>
                <strong>Type:</strong> {{ suggestion_type_display }}<br>
                <strong>Indicator Name:</strong> {{ indicator_name }}<br>
                <strong>Submitted:</strong> {{ submitted_date }}
            </div>
            <div class="details">
                <h3>Suggestion Details:</h3>
                {{ suggestion_details | safe }}
                <p><strong>Reason:</strong> {{ reason }}</p>
                {% if additional_notes %}
                <p><strong>Additional Notes:</strong> {{ additional_notes }}</p>
                {% endif %}
            </div>
            <p><a href="{{ admin_url }}" class="action-button">Review Suggestion</a></p>
        </div>
        <div class="footer">
            <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>"""
    },

    # ── Security Alert ───────────────────────────────────────────────
    "email_template_security_alert": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Security Alert</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #dc2626; color: white; padding: 20px; text-align: center; }
        .header.low { background-color: #f59e0b; }
        .header.medium { background-color: #f97316; }
        .header.high { background-color: #dc2626; }
        .header.critical { background-color: #7f1d1d; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
        .alert-box { padding: 15px; border-radius: 5px; margin: 15px 0; }
        .alert-box.low { background-color: #fef3c7; border-left: 4px solid #f59e0b; }
        .alert-box.medium { background-color: #fff7ed; border-left: 4px solid #f97316; }
        .alert-box.high { background-color: #fef2f2; border-left: 4px solid #dc2626; }
        .alert-box.critical { background-color: #fef2f2; border-left: 4px solid #7f1d1d; }
        .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
        .details-table { width: 100%; border-collapse: collapse; }
        .details-table td { padding: 8px; border-bottom: 1px solid #eee; }
        .details-table td:first-child { font-weight: bold; width: 30%; color: #666; }
        .action-button { display: inline-block; background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header {{ severity|lower }}">
            <h1>&#9888;&#65039; Security Alert</h1>
            <h2>{{ event_type|replace('_', ' ')|title }}</h2>
        </div>
        <div class="content">
            <div class="alert-box {{ severity|lower }}">
                <strong>Severity:</strong> {{ severity|upper }}<br>
                <strong>Time:</strong> {{ timestamp|datetimeformat if timestamp else 'N/A' }}
            </div>
            <div class="details">
                <h3>Event Details</h3>
                <table class="details-table">
                    <tr><td>Event Type:</td><td>{{ event_type|replace('_', ' ')|title if event_type else 'N/A' }}</td></tr>
                    <tr><td>Description:</td><td>{{ description or 'No description provided' }}</td></tr>
                    {% if ip_address %}<tr><td>IP Address:</td><td>{{ ip_address }}</td></tr>{% endif %}
                    {% if user_email %}<tr><td>User:</td><td>{{ user_email }} (ID: {{ user_id }})</td></tr>
                    {% elif user_id %}<tr><td>User ID:</td><td>{{ user_id }}</td></tr>{% endif %}
                    {% if timestamp %}<tr><td>Timestamp:</td><td>{{ timestamp }}</td></tr>{% endif %}
                </table>
            </div>
            <p><a href="{{ admin_url }}" class="action-button">View Security Dashboard</a></p>
            <p style="color: #666; font-size: 12px; margin-top: 20px;">
                This is an automated security alert. Please review the security dashboard for more details.
            </p>
        </div>
        <div class="footer">
            <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            <p>This is an automated security monitoring alert.</p>
        </div>
    </div>
</body>
</html>"""
    },

    # ── Welcome Email ────────────────────────────────────────────────
    "email_template_welcome": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Welcome to {{ org_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #dc2626; color: white; padding: 30px; text-align: center; }
        .content { padding: 30px; background-color: #f9fafb; }
        .section { background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; border-left: 4px solid #2563eb; }
        .section h3 { margin-top: 0; color: #111827; }
        .section p { margin: 10px 0; color: #4b5563; }
        .button { display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .footer { text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }
        .highlight { background-color: #eff6ff; padding: 15px; border-left: 4px solid #2563eb; margin: 15px 0; }
        ul, ol { margin: 10px 0; padding-left: 20px; }
        li { margin: 5px 0; color: #4b5563; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to {{ org_name }}!</h1>
        </div>
        <div class="content">
            <p>Hello {{ user_name }},</p>
            <p>Welcome to {{ org_name }}! We're excited to have you on board.</p>
            <div class="section">
                <h3>Getting Started</h3>
                <p>Your account has been successfully created. To get started:</p>
                <ul>
                    <li>Log in to access your dashboard</li>
                    <li>Explore the system and familiarize yourself with the interface</li>
                    <li>Request access to countries, National Societies, or other entities you need to work with</li>
                </ul>
                <a href="{{ dashboard_url }}" class="button">Go to Dashboard</a>
            </div>
            <div class="section">
                <h3>Requesting Access to Entities</h3>
                <p>To work with specific countries, National Societies, or other entities, you'll need to request access:</p>
                <ol>
                    <li>Go to your dashboard</li>
                    <li>Select the entity (country, National Society, etc.) you want to access</li>
                    <li>Click &ldquo;Request Access&rdquo; if you don't have permission yet</li>
                    <li>An administrator will review your request and notify you when it's approved</li>
                </ol>
                <div class="highlight">
                    <strong>Note:</strong> You'll receive an email notification when your access request is approved.
                </div>
            </div>
            <div class="section">
                <h3>Notification Preferences</h3>
                <p>You can customize how you receive notifications:</p>
                <ul>
                    <li>Choose between instant, daily, or weekly email digests</li>
                    <li>Enable or disable specific notification types</li>
                    <li>Configure push notifications for mobile devices</li>
                </ul>
                <a href="{{ notifications_url }}" class="button">Manage Notifications</a>
            </div>
            <div class="section">
                <h3>Need Help?</h3>
                <p>If you have any questions or need assistance, please don't hesitate to contact your system administrator or support team.</p>
            </div>
            <p>We look forward to working with you!</p>
            <p>Best regards,<br>{{ org_name }} Team</p>
        </div>
        <div class="footer">
            <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            <p>This is an automated welcome email.</p>
        </div>
    </div>
</body>
</html>"""
    },

    # ── Notification Email Wrapper (used by Notifications Center) ────
    "email_template_notification": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #e31e24; color: white; padding: 20px; text-align: center; }
        .header h1 { margin: 0; font-size: 22px; }
        .content { background-color: #f9f9f9; padding: 20px; margin-top: 0; }
        .message { background-color: white; padding: 15px; border-left: 4px solid #e31e24; margin: 15px 0; white-space: pre-wrap; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ title }}</h1>
        </div>
        <div class="content">
            <div class="message">{{ message }}</div>
        </div>
        <div class="footer">
            <p>This is an automated message from {{ org_name }}.</p>
        </div>
    </div>
</body>
</html>"""
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Metadata for the same templates (Notifications Center pre-fill).
# Keys must match EMAIL_TEMPLATE_KEYS; each template is used for both
# emails and the Notifications Center dropdown.
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_TEMPLATE_METADATA = {
    "email_template_suggestion_confirmation": {
        "label": "Indicator Suggestion Confirmation",
        "notification_title": "Indicator Suggestion Received",
        "notification_message": (
            "Thank you for your indicator suggestion. We have received it "
            "and it is under review. We will notify you once the review is complete."
        ),
        "priority": "normal",
    },
    "email_template_admin_notification": {
        "label": "Admin Notification (New Suggestion)",
        "notification_title": "New Suggestion for Review",
        "notification_message": (
            "A new suggestion has been submitted and requires your review. "
            "Please check the admin panel for details."
        ),
        "priority": "high",
    },
    "email_template_security_alert": {
        "label": "Security Alert",
        "notification_title": "Security Alert",
        "notification_message": (
            "A security-related event has been detected. "
            "Please review the security dashboard for details."
        ),
        "priority": "high",
    },
    "email_template_welcome": {
        "label": "Welcome Message",
        "notification_title": "Welcome to {{org_name}}!",
        "notification_message": (
            "Welcome to {{org_name}}! We're excited to have you on board. "
            "Your account has been successfully created. To get started, "
            "explore your dashboard and familiarize yourself with the system. "
            "If you need access to specific countries, National Societies, or "
            "other entities, you can request access from your dashboard. "
            "We look forward to working with you!"
        ),
        "priority": "normal",
    },
    "email_template_notification": {
        "label": "Notification (generic)",
        "notification_title": "Notification from {{org_name}}",
        "notification_message": (
            "This is an automated message from {{org_name}}. "
            "Please review the content above for details."
        ),
        "priority": "normal",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Seed logic
# ═══════════════════════════════════════════════════════════════════════

def seed_templates(force: bool = False) -> dict:
    """Seed email + notification templates into the database.

    Each template is stored once and used for both emails and the
    Notifications Center (same template, same storage).

    Args:
        force: If True, overwrite existing values. Otherwise skip
               templates that already have content.

    Returns:
        ``{"email": {"seeded": N, "skipped": N}, "metadata": {"seeded": N, "skipped": N}}``
    """
    from app.utils.app_settings import (
        get_all_email_templates,
        get_template_metadata,
        set_all_email_templates,
    )

    stats = {
        "email": {"seeded": 0, "skipped": 0},
        "metadata": {"seeded": 0, "skipped": 0},
    }

    existing_email = get_all_email_templates()
    existing_meta = get_template_metadata()
    merged_email = dict(existing_email)
    merged_meta = dict(existing_meta)

    for key in DEFAULT_EMAIL_TEMPLATES:
        lang_dict = DEFAULT_EMAIL_TEMPLATES[key]
        meta = DEFAULT_TEMPLATE_METADATA.get(key, {})
        if key in merged_email and merged_email[key] and not force:
            stats["email"]["skipped"] += 1
            logger.info("  [skip]  template '%s' already has content", key)
        else:
            merged_email[key] = lang_dict
            stats["email"]["seeded"] += 1
            logger.info("  [seed]  template '%s' (email + notification)", key)
        if meta:
            if key in merged_meta and merged_meta[key].get("title") and not force:
                stats["metadata"]["skipped"] += 1
            else:
                merged_meta[key] = meta
                stats["metadata"]["seeded"] += 1

    set_all_email_templates(merged_email, metadata=merged_meta)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Seed default email & notification templates (unified) into the database."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing template values (default: skip non-empty templates).",
    )
    args = parser.parse_args()

    # Bootstrap the Flask app context
    from run import app  # noqa: E402

    with app.app_context():
        logger.info("\n=== Seeding Email & Notification Templates (unified) ===\n")
        stats = seed_templates(force=args.force)
        logger.info(
            "\nDone!  Email content: %d seeded, %d skipped.  Pre-fill metadata: %d seeded, %d skipped.\n",
            stats['email']['seeded'], stats['email']['skipped'],
            stats['metadata']['seeded'], stats['metadata']['skipped']
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
