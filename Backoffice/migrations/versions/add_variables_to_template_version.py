"""Add variables to template version

Revision ID: add_variables_field
Revises: add_version_template_fields
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_variables_field'
down_revision = 'add_version_template_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Add variables JSON field to form_template_version table for template variable system
    op.add_column('form_template_version', sa.Column('variables', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove variables field from form_template_version table
    op.drop_column('form_template_version', 'variables')
