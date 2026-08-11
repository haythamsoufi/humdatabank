"""Add unknown to emaildeliverystatus enum

'unknown' marks a send attempt where the Email API never returned an HTTP
response at all (read timeout / connection error) — as opposed to 'failed',
which means the API (or our own validation) explicitly rejected the send.
See docs/runbooks/email-api-no-response.md.

Revision ID: add_email_delivery_unknown
Revises: report_definition_v2_schema
Create Date: 2026-08-11
"""

from alembic import op


revision = 'add_email_delivery_unknown'
down_revision = 'report_definition_v2_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE emaildeliverystatus ADD VALUE IF NOT EXISTS 'unknown'")


def downgrade():
    pass
