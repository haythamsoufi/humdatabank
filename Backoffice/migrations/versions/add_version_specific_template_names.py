"""Add version-specific template names

Revision ID: add_version_template_names
Revises: add_use_profile_picture
Create Date: 2025-12-02 15:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_version_template_names'
down_revision = 'add_use_profile_picture'
branch_labels = None
depends_on = None


def upgrade():
    # Add version-specific template name fields to form_template_version table
    op.add_column('form_template_version', sa.Column('name', sa.String(length=100), nullable=True))
    op.add_column('form_template_version', sa.Column('name_translations', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove version-specific template name fields from form_template_version table
    op.drop_column('form_template_version', 'name_translations')
    op.drop_column('form_template_version', 'name')
