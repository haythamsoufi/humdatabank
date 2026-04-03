"""add organization branding configuration

Revision ID: add_organization_branding
Revises: add_notif_hash_constraint
Create Date: 2025-01-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime
import os


# revision identifiers, used by Alembic.
revision = 'add_organization_branding'
down_revision = 'add_notif_hash_constraint'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add organization branding settings to system_settings table.
    Sets default values from environment variables or uses 'NGO Databank' as default.
    """
    # Get default values from environment or use defaults
    org_name = os.environ.get('ORGANIZATION_NAME', 'NGO Databank')
    org_short_name = os.environ.get('ORGANIZATION_SHORT_NAME', org_name)
    org_domain = os.environ.get('ORGANIZATION_DOMAIN', 'ngodatabank.org')
    org_email_domain = os.environ.get('ORGANIZATION_EMAIL_DOMAIN', org_domain)
    org_logo_path = os.environ.get('ORGANIZATION_LOGO_PATH', 'logo.svg')
    copyright_year = os.environ.get('ORGANIZATION_COPYRIGHT_YEAR', str(datetime.now().year))

    # Create organization_branding JSON object
    branding_data = {
        'organization_name': org_name,
        'organization_short_name': org_short_name,
        'organization_domain': org_domain,
        'organization_email_domain': org_email_domain,
        'organization_logo_path': org_logo_path,
        'organization_copyright_year': copyright_year
    }

    # Insert into system_settings table
    # Note: system_settings table should already exist from previous migrations
    import json
    branding_json = json.dumps(branding_data)

    # Use parameterized query approach - escape single quotes for SQL string literal
    # json.dumps() already properly escapes JSON, we just need to escape for SQL
    escaped_json = branding_json.replace("'", "''")

    op.execute(
        f"""
        INSERT INTO system_settings (setting_key, setting_value, description, updated_at)
        VALUES (
            'organization_branding',
            '{escaped_json}'::jsonb,
            'Organization branding configuration (name, domain, logo, etc.)',
            NOW()
        )
        ON CONFLICT (setting_key) DO NOTHING;
        """
    )

    # Also migrate email distribution rules from ifrc_in/non_ifrc_in to organization_in/non_organization_in
    # Update notification_campaign table email_distribution_rules JSON field
    op.execute("""
        UPDATE notification_campaign
        SET email_distribution_rules = jsonb_set(
            jsonb_set(
                COALESCE(email_distribution_rules::jsonb, '{}'::jsonb),
                '{organization_in}',
                COALESCE((email_distribution_rules::jsonb)->'ifrc_in', '"cc"'::jsonb)
            ),
            '{non_organization_in}',
            COALESCE((email_distribution_rules::jsonb)->'non_ifrc_in', '"to"'::jsonb)
        )::jsonb
        WHERE email_distribution_rules IS NOT NULL
        AND ((email_distribution_rules::jsonb) ? 'ifrc_in' OR (email_distribution_rules::jsonb) ? 'non_ifrc_in');
    """)


def downgrade():
    """
    Remove organization branding settings and revert email distribution rules.
    """
    # Remove organization branding setting
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'organization_branding';"
    )

    # Revert email distribution rules back to ifrc_in/non_ifrc_in
    op.execute("""
        UPDATE notification_campaign
        SET email_distribution_rules = jsonb_set(
            jsonb_set(
                COALESCE(email_distribution_rules::jsonb, '{}'::jsonb),
                '{ifrc_in}',
                COALESCE((email_distribution_rules::jsonb)->'organization_in', '"cc"'::jsonb)
            ),
            '{non_ifrc_in}',
            COALESCE((email_distribution_rules::jsonb)->'non_organization_in', '"to"'::jsonb)
        )::jsonb
        WHERE email_distribution_rules IS NOT NULL
        AND ((email_distribution_rules::jsonb) ? 'organization_in' OR (email_distribution_rules::jsonb) ? 'non_organization_in');
    """)
