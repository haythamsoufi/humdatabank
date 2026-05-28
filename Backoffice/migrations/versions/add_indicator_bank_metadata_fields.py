"""Add indicator bank metadata and aggregated label fields

Revision ID: add_indicator_bank_metadata
Revises: add_chatbot_telemetry_table
Create Date: 2026-05-28

Adds:
- aggregated_label / aggregated_label_translations (local rollup labels)
- area (IFRC SPEF), data_source, disaggregation_guidance, monitoring_questions, tags
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_indicator_bank_metadata"
down_revision = "add_chatbot_telemetry_table"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("indicator_bank", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aggregated_label", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aggregated_label_translations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("area", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("data_source", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("disaggregation_guidance", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("monitoring_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.create_index("ix_indicator_bank_area", ["area"], unique=False)

    with op.batch_alter_table("indicator_bank_history", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aggregated_label", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aggregated_label_translations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("area", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("data_source", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("disaggregation_guidance", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("monitoring_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    with op.batch_alter_table("indicator_bank_history", schema=None) as batch_op:
        batch_op.drop_column("tags")
        batch_op.drop_column("monitoring_questions")
        batch_op.drop_column("disaggregation_guidance")
        batch_op.drop_column("data_source")
        batch_op.drop_column("area")
        batch_op.drop_column("aggregated_label_translations")
        batch_op.drop_column("aggregated_label")

    with op.batch_alter_table("indicator_bank", schema=None) as batch_op:
        batch_op.drop_index("ix_indicator_bank_area")
        batch_op.drop_column("tags")
        batch_op.drop_column("monitoring_questions")
        batch_op.drop_column("disaggregation_guidance")
        batch_op.drop_column("data_source")
        batch_op.drop_column("area")
        batch_op.drop_column("aggregated_label_translations")
        batch_op.drop_column("aggregated_label")
