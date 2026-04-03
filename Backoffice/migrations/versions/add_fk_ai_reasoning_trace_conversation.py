"""Add FK from ai_reasoning_traces.conversation_id to ai_conversation

Revision ID: add_fk_trace_conv
Revises: remove_profile_picture_fields
Create Date: 2026-03-05

Narrows conversation_id to String(36) to match ai_conversation.id (UUID string)
and adds a nullable FK with SET NULL on delete.
Orphaned conversation_id values (not present in ai_conversation) are nulled out first.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_fk_trace_conv'
down_revision = 'remove_profile_picture_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Null out orphaned conversation_id values that do not exist in ai_conversation.
    # This must happen BEFORE the FK is added to avoid constraint violations.
    op.execute(
        """
        UPDATE ai_reasoning_traces
        SET conversation_id = NULL
        WHERE conversation_id IS NOT NULL
          AND conversation_id NOT IN (SELECT id FROM ai_conversation)
        """
    )

    # Shrink the column to String(36) to match ai_conversation.id and add FK.
    with op.batch_alter_table('ai_reasoning_traces', schema=None) as batch_op:
        batch_op.alter_column(
            'conversation_id',
            existing_type=sa.String(length=100),
            type_=sa.String(length=36),
            existing_nullable=True,
        )
        batch_op.create_foreign_key(
            'fk_ai_reasoning_traces_conversation_id',
            'ai_conversation',
            ['conversation_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('ai_reasoning_traces', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ai_reasoning_traces_conversation_id', type_='foreignkey')
        batch_op.alter_column(
            'conversation_id',
            existing_type=sa.String(length=36),
            type_=sa.String(length=100),
            existing_nullable=True,
        )
