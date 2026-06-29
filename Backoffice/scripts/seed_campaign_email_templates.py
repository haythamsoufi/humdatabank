#!/usr/bin/env python
"""
Seed campaign email templates for the Communication Center.

Run from the Backoffice directory:

    python scripts/seed_campaign_email_templates.py
    python scripts/seed_campaign_email_templates.py --force

Or via Flask CLI:

    flask seed-campaign-email-templates
    flask seed-campaign-email-templates --force
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

_BACKOFFICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKOFFICE_ROOT not in sys.path:
    sys.path.insert(0, _BACKOFFICE_ROOT)

_CAMPAIGN_STYLE = """
        body { margin: 0; padding: 0; background: #eef2f7; color: #1f2937;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          line-height: 1.65; -webkit-font-smoothing: antialiased; }
        .email-outer { max-width: 960px; width: 100%; margin: 0 auto; padding: 28px 20px; box-sizing: border-box; }
        .email-card { background: #ffffff; border: 1px solid #e2e8f0; }
        .email-header { background: #0d9488; color: #ffffff; padding: 28px 40px; text-align: center; }
        .email-header h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
        .email-body { padding: 32px 40px; background: #ffffff; }
        .email-body p { margin: 0 0 16px; color: #334155; }
        .section { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #0d9488;
          padding: 20px 22px; margin: 20px 0; }
        .action-button { display: inline-block; background: #0d9488; color: #ffffff !important; padding: 12px 24px;
          text-decoration: none; font-weight: 600; font-size: 15px; margin: 10px 0 0; border: 1px solid #0f766e; }
        .email-footer { padding: 22px 40px; text-align: center; font-size: 12px; color: #64748b;
          background: #f8fafc; border-top: 1px solid #e2e8f0; }
        .email-footer p { margin: 6px 0; }
"""


def _wrap(body_html: str) -> str:
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>""" + _CAMPAIGN_STYLE + """</style>
</head>
<body>
    <div class="email-outer">
        <div class="email-card">
            <div class="email-header">
                <h1>{{ title }}</h1>
            </div>
            <div class="email-body">
                <p>Hello {{ user_name }},</p>
""" + body_html + """
            </div>
            <div class="email-footer">
                <p>&copy; {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
            </div>
        </div>
    </div>
</body>
</html>"""


DEFAULT_CAMPAIGN_EMAIL_TEMPLATES = {
    "campaign_template_data_collection_launch": {
        "en": _wrap(
            """
                <p>{{ message }}</p>
                <div class="section">
                    <p><strong>Reporting period:</strong> {{ period_name }}</p>
                    <p>Please review your assignments and begin entering data for this cycle.</p>
                    <a href="{{ dashboard_url }}" class="action-button">Open dashboard</a>
                </div>
            """,
        ),
    },
    "campaign_template_submission_reminder": {
        "en": _wrap(
            """
                <p>{{ message }}</p>
                <div class="section">
                    <p>This is a friendly reminder to complete your pending reporting assignments.</p>
                    <a href="{{ dashboard_url }}" class="action-button">View assignments</a>
                </div>
            """,
        ),
    },
    "campaign_template_deadline_reminder": {
        "en": _wrap(
            """
                <p>{{ message }}</p>
                <div class="section">
                    <p><strong>Deadline:</strong> {{ deadline_date }}</p>
                    <p>Please submit your data before the deadline to avoid delays in consolidation.</p>
                    <a href="{{ action_url }}" class="action-button">Continue reporting</a>
                </div>
            """,
        ),
    },
    "campaign_template_training_announcement": {
        "en": _wrap(
            """
                <p>{{ message }}</p>
                <div class="section">
                    <p>Join us for a training session on using the platform and completing reporting workflows.</p>
                    <a href="{{ action_url }}" class="action-button">View details</a>
                </div>
            """,
        ),
    },
    "campaign_template_general_announcement": {
        "en": _wrap(
            """
                <p>{{ message }}</p>
                <div class="section">
                    <p>If you have questions, contact your system administrator or open Documentation after signing in.</p>
                    <a href="{{ documentation_url }}" class="action-button">Open documentation</a>
                </div>
            """,
        ),
    },
}

DEFAULT_CAMPAIGN_TEMPLATE_METADATA = {
    "campaign_template_data_collection_launch": {
        "label": "Data collection launch",
        "compose_title": "{{org_name}} — New reporting period open",
        "compose_message": (
            "A new data collection period is now open on {{org_name}}. "
            "Please sign in, review your assignments, and begin entering data for this cycle."
        ),
        "priority": "normal",
    },
    "campaign_template_submission_reminder": {
        "label": "Submission reminder",
        "compose_title": "Reminder: complete your reporting assignments",
        "compose_message": (
            "This is a friendly reminder to complete your pending reporting assignments on {{org_name}}. "
            "Open your dashboard to see what is still due."
        ),
        "priority": "normal",
    },
    "campaign_template_deadline_reminder": {
        "label": "Deadline reminder",
        "compose_title": "Deadline approaching — please submit your data",
        "compose_message": (
            "The reporting deadline is approaching. Please submit your data on {{org_name}} "
            "as soon as possible so your National Society can complete consolidation on time."
        ),
        "priority": "high",
    },
    "campaign_template_training_announcement": {
        "label": "Training announcement",
        "compose_title": "Upcoming training session",
        "compose_message": (
            "You are invited to a training session on using {{org_name}} for data collection and reporting. "
            "Details and joining instructions are included in this message."
        ),
        "priority": "normal",
    },
    "campaign_template_general_announcement": {
        "label": "General announcement",
        "compose_title": "Message from {{org_name}}",
        "compose_message": (
            "Please read the update below from {{org_name}}. "
            "Sign in to your dashboard if you need to take action."
        ),
        "priority": "normal",
    },
}


def seed_campaign_templates(force: bool = False, user_id: Optional[int] = None) -> dict:
    from app.services.campaign_email_templates_service import (
        get_all_campaign_email_templates,
        get_campaign_template_metadata,
        set_all_campaign_email_templates,
    )

    stats = {"email": {"seeded": 0, "skipped": 0}, "metadata": {"seeded": 0, "skipped": 0}}
    existing_email = get_all_campaign_email_templates()
    existing_meta = get_campaign_template_metadata()
    merged_email = dict(existing_email)
    merged_meta = {}

    for key, meta in DEFAULT_CAMPAIGN_TEMPLATE_METADATA.items():
        merged_meta[key] = {
            "label": meta.get("label", ""),
            "compose_title": meta.get("compose_title", ""),
            "compose_message": meta.get("compose_message", ""),
            "priority": meta.get("priority", "normal"),
        }

    for key in DEFAULT_CAMPAIGN_EMAIL_TEMPLATES:
        lang_dict = DEFAULT_CAMPAIGN_EMAIL_TEMPLATES[key]
        if key in merged_email and merged_email[key] and not force:
            stats["email"]["skipped"] += 1
            logger.info("  [skip]  campaign template '%s' already has content", key)
        else:
            merged_email[key] = lang_dict
            stats["email"]["seeded"] += 1
            logger.info("  [seed]  campaign template '%s'", key)

        meta = DEFAULT_CAMPAIGN_TEMPLATE_METADATA.get(key, {})
        if meta:
            if key in existing_meta and existing_meta[key].get("title") and not force:
                stats["metadata"]["skipped"] += 1
            else:
                stats["metadata"]["seeded"] += 1

    set_all_campaign_email_templates(merged_email, metadata=merged_meta, user_id=user_id)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Seed default campaign email templates into the database.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template values.")
    args = parser.parse_args()

    from run import app  # noqa: E402

    with app.app_context():
        logger.info("\n=== Seeding Campaign Email Templates ===\n")
        stats = seed_campaign_templates(force=args.force)
        logger.info(
            "\nDone!  HTML: %d seeded, %d skipped.  Compose defaults: %d seeded, %d skipped.\n",
            stats["email"]["seeded"],
            stats["email"]["skipped"],
            stats["metadata"]["seeded"],
            stats["metadata"]["skipped"],
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
