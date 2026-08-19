"""Drop unused notification_preferences.sound_enabled

In-app notification sound was never shipped (no audio file) and has been
removed from preferences UI, APIs, and the Backoffice/Mobile clients.

Revision ID: drop_notif_sound
Revises: add_val_msg_trans
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "drop_notif_sound"
down_revision = "add_val_msg_trans"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notification_preferences", schema=None) as batch_op:
        batch_op.drop_column("sound_enabled")


def downgrade():
    with op.batch_alter_table("notification_preferences", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sound_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.alter_column("sound_enabled", server_default=None)
