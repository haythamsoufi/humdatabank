"""Add JSONB related_programs_list to indicator bank

Revision ID: migrate_related_programs_jsonb
Revises: add_symmetric_data_table_columns
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'migrate_related_programs_jsonb'
down_revision = 'add_symmetric_data_table_columns'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('related_programs_list', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.execute(
        """
        UPDATE indicator_bank
        SET related_programs_list = (
            SELECT jsonb_agg(trim(val))
            FROM regexp_split_to_table(related_programs, '[,|]') AS val
            WHERE trim(val) <> ''
        )
        WHERE related_programs IS NOT NULL
          AND trim(related_programs) <> ''
        """
    )


def downgrade():
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.drop_column('related_programs_list')
