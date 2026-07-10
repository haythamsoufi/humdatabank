"""Drop legacy related_programs text column from indicator_bank

Revision ID: drop_ib_related_programs_text
Revises: add_pb_progress_permission
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = 'drop_ib_related_programs_text'
down_revision = 'add_pb_progress_permission'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE indicator_bank
        SET related_programs_list = (
            SELECT jsonb_agg(trim(val))
            FROM regexp_split_to_table(related_programs, '[,|]') AS val
            WHERE trim(val) <> ''
        )
        WHERE related_programs_list IS NULL
          AND related_programs IS NOT NULL
          AND trim(related_programs) <> ''
        """
    )

    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.drop_column('related_programs')


def downgrade():
    with op.batch_alter_table('indicator_bank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('related_programs', sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE indicator_bank
        SET related_programs = (
            SELECT string_agg(elem, ', ')
            FROM jsonb_array_elements_text(related_programs_list) AS elem
        )
        WHERE related_programs_list IS NOT NULL
          AND jsonb_array_length(related_programs_list) > 0
        """
    )
