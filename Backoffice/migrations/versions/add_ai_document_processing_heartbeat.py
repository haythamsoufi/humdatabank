"""Add cross-worker processing stage/heartbeat columns to ai_documents.

Revision ID: add_ai_doc_processing_hb
Revises: add_in_app_notif_types
Create Date: 2026-08-07

"""

from alembic import op
import sqlalchemy as sa


revision = "add_ai_doc_processing_hb"
down_revision = "add_in_app_notif_types"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("processing_stage", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("processing_heartbeat_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("ai_documents", schema=None) as batch_op:
        batch_op.drop_column("processing_heartbeat_at")
        batch_op.drop_column("processing_stage")
