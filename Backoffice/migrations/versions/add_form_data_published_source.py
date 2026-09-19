"""Add published_source to form_data

Revision ID: add_form_data_published_source
Revises: add_form_data_published_value
Create Date: 2026-09-19

Records whether a published snapshot value was copied from the reported value
or the imputed value at publish time. NULL means never published, cleared, or
published before this column existed — do not backfill from live columns.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_form_data_published_source'
down_revision = 'add_form_data_published_value'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('published_source', sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            'ck_form_data_published_source',
            "published_source IS NULL OR published_source IN ('reported', 'imputed')",
        )


def downgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.drop_constraint('ck_form_data_published_source', type_='check')
        batch_op.drop_column('published_source')
