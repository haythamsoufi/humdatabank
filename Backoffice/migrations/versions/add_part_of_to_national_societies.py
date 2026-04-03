"""add part_of field to national_societies

Revision ID: add_part_of_to_national_societies
Revises: add_country_to_ai_documents
Create Date: 2025-01-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_part_of_to_national_societies'
down_revision = 'add_country_to_ai_documents'
branch_labels = None
depends_on = None


def upgrade():
    jsonb_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        'national_societies',
        sa.Column('part_of', jsonb_type, nullable=True)
    )


def downgrade():
    op.drop_column('national_societies', 'part_of')
