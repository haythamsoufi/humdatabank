"""Add published_value snapshot columns to form_data + publish audit columns

Revision ID: add_form_data_published_value
Revises: drop_section_submission
Create Date: 2026-09-18

Adds a fourth "kind" of value alongside ``value`` (reported/main), ``prefilled_value``,
and ``imputed_value``: ``published_value`` / ``published_disagg_data`` /
``published_numeric_value`` on ``form_data``. This is a curated snapshot of the
reported value, written only when an admin explicitly runs the FDRS publication tool
(``plugins/fdrs``, see ``fdrs_publication_service.py``) — never by regular form
submission — and is what the public-facing ``GET /api/v1/fdrs/published-data``
endpoint serves to external consumers.

Also adds ``published_at`` / ``published_by_user_id`` audit columns to both
``form_data`` (per item) and ``assignment_entity_status`` (per country per
assignment round) so the publication admin UI can show "last published" without
recomputing from ``form_data`` on every page load.
"""

from alembic import op
import sqlalchemy as sa


revision = 'add_form_data_published_value'
down_revision = 'drop_section_submission'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('published_value', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('published_disagg_data', sa.JSON(none_as_null=True), nullable=True))
        batch_op.add_column(sa.Column('published_numeric_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('published_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_form_data_published_by_user_id',
            'user',
            ['published_by_user_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_form_data_published_at', ['published_at'], unique=False)
        batch_op.create_index('ix_form_data_published_by', ['published_by_user_id'], unique=False)

    with op.batch_alter_table('assignment_entity_status', schema=None) as batch_op:
        batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('published_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_aes_published_by_user_id',
            'user',
            ['published_by_user_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_aes_published_at', ['published_at'], unique=False)
        batch_op.create_index('ix_aes_published_by', ['published_by_user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('assignment_entity_status', schema=None) as batch_op:
        batch_op.drop_index('ix_aes_published_by')
        batch_op.drop_index('ix_aes_published_at')
        batch_op.drop_constraint('fk_aes_published_by_user_id', type_='foreignkey')
        batch_op.drop_column('published_by_user_id')
        batch_op.drop_column('published_at')

    with op.batch_alter_table('form_data', schema=None) as batch_op:
        batch_op.drop_index('ix_form_data_published_by')
        batch_op.drop_index('ix_form_data_published_at')
        batch_op.drop_constraint('fk_form_data_published_by_user_id', type_='foreignkey')
        batch_op.drop_column('published_by_user_id')
        batch_op.drop_column('published_at')
        batch_op.drop_column('published_numeric_value')
        batch_op.drop_column('published_disagg_data')
        batch_op.drop_column('published_value')
