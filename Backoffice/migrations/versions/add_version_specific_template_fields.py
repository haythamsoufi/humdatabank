"""Add version-specific template fields

Revision ID: add_version_template_fields
Revises: add_version_template_names
Create Date: 2025-01-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_version_template_fields'
down_revision = 'add_version_template_names'
branch_labels = None
depends_on = None


def upgrade():
    # Add version-specific template configuration fields to form_template_version table
    op.add_column('form_template_version', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('form_template_version', sa.Column('template_type', sa.String(length=50), nullable=True))
    op.add_column('form_template_version', sa.Column('add_to_self_report', sa.Boolean(), nullable=True))
    op.add_column('form_template_version', sa.Column('display_order_visible', sa.Boolean(), nullable=True))
    op.add_column('form_template_version', sa.Column('is_paginated', sa.Boolean(), nullable=True))
    op.add_column('form_template_version', sa.Column('enable_export_pdf', sa.Boolean(), nullable=True))
    op.add_column('form_template_version', sa.Column('enable_export_excel', sa.Boolean(), nullable=True))
    op.add_column('form_template_version', sa.Column('enable_import_excel', sa.Boolean(), nullable=True))


def downgrade():
    # Remove version-specific template configuration fields from form_template_version table
    op.drop_column('form_template_version', 'enable_import_excel')
    op.drop_column('form_template_version', 'enable_export_excel')
    op.drop_column('form_template_version', 'enable_export_pdf')
    op.drop_column('form_template_version', 'is_paginated')
    op.drop_column('form_template_version', 'display_order_visible')
    op.drop_column('form_template_version', 'add_to_self_report')
    op.drop_column('form_template_version', 'template_type')
    op.drop_column('form_template_version', 'description')
