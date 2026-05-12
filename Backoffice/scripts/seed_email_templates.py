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

After editing HTML here, sync inline fallbacks in ``app/services/email/service.py`` and
``app/routes/admin/notifications.py`` (or run ``python scripts/_apply_email_fallbacks.py``).
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Ensure the Backoffice package is importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ═══════════════════════════════════════════════════════════════════════
# Default email templates (Jinja2 HTML used by the email service).
# Mirror inline fallbacks in app/services/email/service.py; DB copies are
# editable under System Configuration → Emails.
# Layout: wide content (max ~960px), card on light gray background, teal accent.
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_EMAIL_TEMPLATES = {

    # ── Indicator Suggestion Confirmation ────────────────────────────
    "email_template_suggestion_confirmation": {
        "en": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Indicator Suggestion Confirmation</title>
    <style>body{margin:0;padding:0;background:#eef2f7;color:#1f2937;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased}.email-outer{max-width:960px;width:100%;margin:0 auto;padding:28px 20px;box-sizing:border-box}.email-card{background:#fff;border:1px solid #e2e8f0}.email-header{background:#0d9488;color:#fff;padding:32px 40px;text-align:center}.email-header h1{margin:0 0 8px;font-size:26px;font-weight:600;letter-spacing:-.02em}.email-header h2{margin:0;font-size:18px;font-weight:500;opacity:.95}.email-body{padding:36px 40px 32px;background:#fff}.email-body p{margin:0 0 16px}.email-body ul{margin:8px 0 0;padding-left:22px}.email-body li{margin:8px 0}.email-footer{padding:22px 40px;text-align:center;font-size:12px;color:#64748b;background:#f8fafc;border-top:1px solid #e2e8f0}.email-footer p{margin:6px 0}.highlight{background:#f0fdfa;border:1px solid #99f6e4;border-left:4px solid #0d9488;padding:20px 22px;margin:22px 0;font-size:14px}.details{background:#f8fafc;border:1px solid #e2e8f0;padding:22px 24px;margin:20px 0}.details h3{margin:0 0 14px;font-size:17px;color:#0f172a;font-weight:600}.comparison-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}.comparison-table th,.comparison-table td{border:1px solid #e2e8f0;padding:10px 12px;text-align:left}.comparison-table th{background:#f1f5f9;font-weight:600;color:#334155}.unchanged{color:#64748b}.changed{background:#fffbeb;font-weight:600;color:#92400e}.new-indicator-list{list-style:none;padding:0;margin:0}.new-indicator-list li{padding:10px 0;border-bottom:1px solid #e2e8f0}.new-indicator-list li:last-child{border-bottom:none}.new-indicator-list strong{color:#0d9488}</style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>{{ org_name }}</h1>
                <h2>Indicator Suggestion Confirmation</h2>
            </div>
            <div class="email-body">
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
            <div class="email-footer">
                <p>This is an automated message. Please do not reply to this email.</p>
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            </div>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Indicator Suggestion</title>
    <style>
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .email-header { background: #0d9488; color: #ffffff; padding: 32px 40px; text-align: center; }
        .email-header h1 { margin: 0 0 8px; font-size: 26px; font-weight: 600; letter-spacing: -0.02em; }
        .email-header h2 { margin: 0; font-size: 18px; font-weight: 500; opacity: 0.95; }
        .email-body { padding: 36px 40px 32px; background: #ffffff; }
        .email-body p { margin: 0 0 16px; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
        .highlight { background: #f0fdfa; border: 1px solid #99f6e4; border-left: 4px solid #0d9488;
          padding: 20px 22px; margin: 22px 0; font-size: 14px; }
        .details { background: #f8fafc; border: 1px solid #e2e8f0; padding: 22px 24px; margin: 20px 0; }
        .details h3 { margin: 0 0 14px; font-size: 17px; color: #0f172a; font-weight: 600; }
        .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 12px 24px;
          text-decoration: none; font-weight: 600; font-size: 15px; margin: 8px 0; border: 1px solid #0f766e; }
        .comparison-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
        .comparison-table th, .comparison-table td { border: 1px solid #e2e8f0; padding: 10px 12px; text-align: left; }
        .comparison-table th { background: #f1f5f9; font-weight: 600; color: #334155; }
        .unchanged { color: #64748b; }
        .changed { background: #fffbeb; font-weight: 600; color: #92400e; }
        .new-indicator-list { list-style: none; padding: 0; margin: 0; }
        .new-indicator-list li { padding: 10px 0; border-bottom: 1px solid #e2e8f0; }
        .new-indicator-list li:last-child { border-bottom: none; }
        .new-indicator-list strong { color: #0d9488; }
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>{{ org_name }}</h1>
                <h2>New Indicator Suggestion</h2>
            </div>
            <div class="email-body">
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
            <div class="email-footer">
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            </div>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Alert</title>
    <style>
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .header { color: #ffffff; padding: 32px 40px; text-align: center; }
        .header.low { background: #d97706; }
        .header.medium { background: #ea580c; }
        .header.high { background: #dc2626; }
        .header.critical { background: #7f1d1d; }
        .header h1 { margin: 0 0 8px; font-size: 26px; font-weight: 600; }
        .header h2 { margin: 0; font-size: 18px; font-weight: 500; opacity: 0.95; }
        .content { padding: 36px 40px 32px; background: #ffffff; }
        .content p { margin: 0 0 12px; }
        .alert-box { padding: 20px 22px; margin: 0 0 22px; border: 1px solid #e2e8f0; }
        .alert-box.low { background: #fffbeb; border-left: 4px solid #f59e0b; }
        .alert-box.medium { background: #fff7ed; border-left: 4px solid #f97316; }
        .alert-box.high { background: #fef2f2; border-left: 4px solid #dc2626; }
        .alert-box.critical { background: #fef2f2; border-left: 4px solid #7f1d1d; }
        .details { background: #f8fafc; border: 1px solid #e2e8f0; padding: 22px 24px; margin: 0 0 22px; }
        .details h3 { margin: 0 0 14px; font-size: 17px; color: #0f172a; font-weight: 600; }
        .details-table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .details-table td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
        .details-table td:first-child { font-weight: 600; width: 28%; color: #475569; }
        .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 12px 24px;
          text-decoration: none; font-weight: 600; font-size: 15px; border: 1px solid #0f766e; }
        .muted { color: #64748b; font-size: 13px; margin-top: 20px; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
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
                <p class="muted">This is an automated security alert. Please review the security dashboard for more details.</p>
            </div>
            <div class="email-footer">
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                <p>This is an automated security monitoring alert.</p>
            </div>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to {{ org_name }}</title>
    <style>
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .email-header { background: #0d9488; color: #ffffff; padding: 32px 40px; text-align: center; }
        .email-header h1 { margin: 0; font-size: 28px; font-weight: 600; letter-spacing: -0.02em; }
        .email-body { padding: 36px 40px 32px; background: #ffffff; }
        .email-body p { margin: 0 0 16px; }
        .email-body ul, .email-body ol { margin: 8px 0 16px; padding-left: 24px; }
        .email-body li { margin: 8px 0; color: #334155; }
        .section { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488;
          padding: 22px 24px; margin: 20px 0; }
        .section h3 { margin: 0 0 12px; font-size: 17px; color: #0f172a; font-weight: 600; }
        .section p { color: #475569; margin: 0 0 10px; }
        .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 12px 24px;
          text-decoration: none; font-weight: 600; font-size: 15px; margin: 10px 0 0; border: 1px solid #0f766e; }
        .highlight { background: #f0fdfa; border: 1px solid #99f6e4; border-left: 4px solid #0d9488;
          padding: 16px 18px; margin: 16px 0 0; font-size: 14px; color: #334155; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
        .email-footer p { margin: 6px 0; }
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>Welcome to {{ org_name }}!</h1>
            </div>
            <div class="email-body">
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
                    <a href="{{ dashboard_url }}" class="action-button">Go to Dashboard</a>
                </div>
                <div class="section">
                    <h3>Documentation</h3>
                    <p>
                        In-app documentation (the same help area as <strong>Admin &rarr; Documentation</strong>)
                        includes getting-started guides and user guides. Use it to learn features, workflows, and
                        best practices once you are signed in and have access.
                    </p>
                    <a href="{{ documentation_url }}" class="action-button">Open documentation</a>
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
                    <a href="{{ notifications_url }}" class="action-button">Manage Notifications</a>
                </div>
                <div class="section">
                    <h3>Need Help?</h3>
                    <p>If you have any questions or need assistance, please don't hesitate to contact your system administrator or support team.</p>
                </div>
                <p>We look forward to working with you!</p>
                <p>Best regards,<br>{{ org_name }} Team</p>
            </div>
            <div class="email-footer">
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                <p>This is an automated welcome email.</p>
            </div>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .email-header { background: #0d9488; color: #ffffff; padding: 28px 40px; text-align: center; }
        .email-header h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
        .email-body { padding: 32px 40px; background: #ffffff; }
        .message { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488;
          padding: 22px 24px; white-space: pre-wrap; font-size: 15px; color: #334155; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
        .email-footer p { margin: 0; }
    </style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>{{ title }}</h1>
            </div>
            <div class="email-body">
                <div class="message">{{ message }}</div>
            </div>
            <div class="email-footer">
                <p>This is an automated message from {{ org_name }}.</p>
            </div>
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
            "explore your dashboard and in-app documentation (Admin → Documentation) "
            "for user guides and getting started. "
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

def seed_templates(force: bool = False, user_id: Optional[int] = None) -> dict:
    """Seed email + notification templates into the database.

    Each template is stored once and used for both emails and the
    Notifications Center (same template, same storage).

    Args:
        force: If True, overwrite existing values. Otherwise skip
               templates that already have content.
        user_id: Optional user id for settings audit (e.g. admin who triggered seed).

    Returns:
        ``{"email": {"seeded": N, "skipped": N}, "metadata": {"seeded": N, "skipped": N}}``
    """
    from app.services.app_settings_service import (
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

    set_all_email_templates(merged_email, metadata=merged_meta, user_id=user_id)

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
