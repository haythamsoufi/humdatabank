"""Add AI chat persistence tables

Revision ID: add_ai_chat_persistence
Revises: add_email_templates
Create Date: 2025-12-26

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_ai_chat_persistence'
down_revision = 'add_email_templates'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_conversation',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_conversation_user_id', 'ai_conversation', ['user_id'], unique=False)
    op.create_index('ix_ai_conversation_last_message_at', 'ai_conversation', ['last_message_at'], unique=False)

    op.create_table(
        'ai_message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversation.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_message_conversation_id', 'ai_message', ['conversation_id'], unique=False)
    op.create_index('ix_ai_message_user_id', 'ai_message', ['user_id'], unique=False)
    op.create_index('ix_ai_message_created_at', 'ai_message', ['created_at'], unique=False)


def downgrade():
    op.drop_index('ix_ai_message_created_at', table_name='ai_message')
    op.drop_index('ix_ai_message_user_id', table_name='ai_message')
    op.drop_index('ix_ai_message_conversation_id', table_name='ai_message')
    op.drop_table('ai_message')

    op.drop_index('ix_ai_conversation_last_message_at', table_name='ai_conversation')
    op.drop_index('ix_ai_conversation_user_id', table_name='ai_conversation')
    op.drop_table('ai_conversation')
