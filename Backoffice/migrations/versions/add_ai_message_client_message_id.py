"""Add client_message_id to ai_message for idempotent imports

Revision ID: add_ai_message_client_message_id
Revises: add_ai_chat_persistence
Create Date: 2025-12-28

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_ai_message_client_message_id"
down_revision = "add_ai_chat_persistence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_message", sa.Column("client_message_id", sa.String(length=64), nullable=True))
    op.create_index("ix_ai_message_client_message_id", "ai_message", ["client_message_id"], unique=False)
    op.create_unique_constraint(
        "uq_ai_message_client_message_id",
        "ai_message",
        ["conversation_id", "user_id", "client_message_id"],
    )


def downgrade():
    op.drop_constraint("uq_ai_message_client_message_id", "ai_message", type_="unique")
    op.drop_index("ix_ai_message_client_message_id", table_name="ai_message")
    op.drop_column("ai_message", "client_message_id")
