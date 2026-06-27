"""Add stable_key to form_item and form_section for cross-version field identity

Revision ID: add_stable_key_form_structure
Revises: secretariat_ro_short_name
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_stable_key_form_structure'
down_revision = 'secretariat_ro_short_name'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stable_key', sa.String(length=36), nullable=True))

    with op.batch_alter_table('form_section', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stable_key', sa.String(length=36), nullable=True))

    op.create_index(
        'uq_form_item_stable_key',
        'form_item',
        ['template_id', 'stable_key', 'version_id'],
        unique=True,
        postgresql_where=sa.text('stable_key IS NOT NULL'),
    )
    op.create_index(
        'uq_form_section_stable_key',
        'form_section',
        ['template_id', 'stable_key', 'version_id'],
        unique=True,
        postgresql_where=sa.text('stable_key IS NOT NULL'),
    )


def downgrade():
    op.drop_index('uq_form_section_stable_key', table_name='form_section')
    op.drop_index('uq_form_item_stable_key', table_name='form_item')

    with op.batch_alter_table('form_section', schema=None) as batch_op:
        batch_op.drop_column('stable_key')

    with op.batch_alter_table('form_item', schema=None) as batch_op:
        batch_op.drop_column('stable_key')
