"""Add chatbot_telemetry table via Flask-Migrate (previously created ad-hoc at runtime).

Revision ID: add_chatbot_telemetry_table
Revises: uq_assigned_form_template_period
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa

revision = 'add_chatbot_telemetry_table'
down_revision = 'uq_assigned_form_template_period'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chatbot_telemetry',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('message_length', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(50), nullable=True),
        sa.Column('page_context', sa.Text(), nullable=True),
        sa.Column('llm_provider', sa.String(50), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('function_calls_made', sa.Text(), nullable=True),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_type', sa.String(255), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
        sa.Column('response_length', sa.Integer(), nullable=True),
        sa.Column('used_provenance', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_chatbot_telemetry_user_timestamp',
        'chatbot_telemetry',
        ['user_id', sa.text('timestamp DESC')],
        unique=False
    )


def downgrade():
    op.drop_index('idx_chatbot_telemetry_user_timestamp', table_name='chatbot_telemetry')
    op.drop_table('chatbot_telemetry')
