"""Add AI chat archiving/retention fields

Revision ID: add_ai_chat_archiving
Revises: add_ai_message_client_message_id
Create Date: 2025-12-28

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_ai_chat_archiving"
down_revision = "add_ai_message_client_message_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_conversation", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("ai_conversation", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("ai_conversation", sa.Column("archive_provider", sa.String(length=32), nullable=True))
    op.add_column("ai_conversation", sa.Column("archive_path", sa.Text(), nullable=True))
    op.add_column("ai_conversation", sa.Column("archive_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("ai_conversation", sa.Column("archive_sha256", sa.String(length=64), nullable=True))

    op.create_index("ix_ai_conversation_is_archived", "ai_conversation", ["is_archived"], unique=False)
    op.create_index("ix_ai_conversation_archived_at", "ai_conversation", ["archived_at"], unique=False)


def downgrade():
    op.drop_index("ix_ai_conversation_archived_at", table_name="ai_conversation")
    op.drop_index("ix_ai_conversation_is_archived", table_name="ai_conversation")

    op.drop_column("ai_conversation", "archive_sha256")
    op.drop_column("ai_conversation", "archive_size_bytes")
    op.drop_column("ai_conversation", "archive_path")
    op.drop_column("ai_conversation", "archive_provider")
    op.drop_column("ai_conversation", "archived_at")
    op.drop_column("ai_conversation", "is_archived")
