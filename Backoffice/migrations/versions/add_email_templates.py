"""add email templates to system settings

Revision ID: add_email_templates
Revises: add_organization_branding
Create Date: 2025-01-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json


# revision identifiers, used by Alembic.
revision = 'add_email_templates'
down_revision = 'add_organization_branding'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add default email templates to system_settings table.
    Templates are stored as JSON with template keys mapping to template content.
    """
    # Default email templates (these match the defaults in email_service.py)
    default_templates = {
        'email_template_suggestion_confirmation': '',
        'email_template_admin_notification': '',
        'email_template_security_alert': '',
        'email_template_welcome': '',
    }

    # Insert email templates into system_settings
    # Empty strings mean "use system default" - templates will be loaded from code if empty
    templates_json = json.dumps(default_templates)

    # Escape single quotes for SQL string literal
    # json.dumps() already properly escapes JSON, we just need to escape for SQL
    escaped_json = templates_json.replace("'", "''")

    op.execute(
        f"""
        INSERT INTO system_settings (setting_key, setting_value, description, updated_at)
        VALUES (
            'email_templates',
            '{escaped_json}'::jsonb,
            'Email templates for system-generated emails (Jinja2 format). Leave empty to use system defaults.',
            NOW()
        )
        ON CONFLICT (setting_key) DO NOTHING;
        """
    )


def downgrade():
    """
    Remove email templates from system_settings.
    """
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'email_templates';"
    )
