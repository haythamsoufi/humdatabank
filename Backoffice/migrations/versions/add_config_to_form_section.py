"""Add config field to form_section

Revision ID: add_section_config
Revises: add_variables_field
Create Date: 2025-12-03 13:38:08.332719

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_section_config'
down_revision = 'add_variables_field'
branch_labels = None
depends_on = None


def upgrade():
    # Add config JSON field to form_section table for storing section configuration
    # This allows storing max_entries for repeat groups and other configuration options
    op.add_column('form_section', sa.Column('config', sa.JSON(), nullable=True))


def downgrade():
    # Remove config field from form_section table
    op.drop_column('form_section', 'config')
