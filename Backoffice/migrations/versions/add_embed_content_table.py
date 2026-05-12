"""Add embed_content table for managing external iframe embeds

Revision ID: add_embed_content_table
Revises: add_progress_steps_trace
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa


revision = "add_embed_content_table"
down_revision = "add_progress_steps_trace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'embed_content',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=False, server_default='global_initiative'),
        sa.Column('embed_url', sa.Text(), nullable=False),
        sa.Column('embed_type', sa.String(50), nullable=False, server_default='powerbi'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('aspect_ratio', sa.String(20), nullable=True),
        sa.Column('page_slot', sa.String(50), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_embed_content_category', 'embed_content', ['category'])
    op.create_index('ix_embed_content_active', 'embed_content', ['is_active'])
    op.create_index('ix_embed_content_sort', 'embed_content', ['sort_order'])


def downgrade():
    op.drop_index('ix_embed_content_sort', table_name='embed_content')
    op.drop_index('ix_embed_content_active', table_name='embed_content')
    op.drop_index('ix_embed_content_category', table_name='embed_content')
    op.drop_table('embed_content')
