"""Add enable_ai_validation to form_template_version

Revision ID: set_ai_validation_default_false
Revises: add_digest_idempotency
Create Date: 2026-02-28

Adds enable_ai_validation column to form_template_version to allow per-template
enable/disable of the Run AI validation button in the entry form.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'set_ai_validation_default_false'
down_revision = 'add_digest_idempotency'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'enable_ai_validation',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false()
            )
        )


def downgrade():
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.drop_column('enable_ai_validation')
