"""Add enable_discussion to form_template_version

Revision ID: add_enable_discussion
Revises: add_cancelled_aes_status
Create Date: 2026-07-30

Adds enable_discussion and discussion_config columns to form_template_version
to allow per-template enable/disable of the Discussion panel in the entry form.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_enable_discussion'
down_revision = 'add_cancelled_aes_status'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'enable_discussion',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column('discussion_config', sa.JSON(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.drop_column('discussion_config')
        batch_op.drop_column('enable_discussion')
