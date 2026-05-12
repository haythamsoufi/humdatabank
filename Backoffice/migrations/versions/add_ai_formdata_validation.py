"""Add ai_formdata_validation table

Revision ID: add_ai_formdata_validation
Revises: add_attachment_config
Create Date: 2026-02-03

Stores latest-only AI validation opinion per FormData row.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_ai_formdata_validation"
down_revision = "add_attachment_config"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_formdata_validation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("form_data_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("opinion_text", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("run_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["form_data_id"], ["form_data.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("form_data_id", name="uq_ai_formdata_validation_form_data_id"),
    )
    op.create_index("ix_ai_formdata_validation_form_data_id", "ai_formdata_validation", ["form_data_id"], unique=True)
    op.create_index("ix_ai_formdata_validation_run_by_user_id", "ai_formdata_validation", ["run_by_user_id"], unique=False)
    op.create_index("ix_ai_formdata_validation_status", "ai_formdata_validation", ["status"], unique=False)
    op.create_index("ix_ai_formdata_validation_verdict", "ai_formdata_validation", ["verdict"], unique=False)
    op.create_index("ix_ai_formdata_validation_updated_at", "ai_formdata_validation", ["updated_at"], unique=False)


def downgrade():
    op.drop_index("ix_ai_formdata_validation_updated_at", table_name="ai_formdata_validation")
    op.drop_index("ix_ai_formdata_validation_verdict", table_name="ai_formdata_validation")
    op.drop_index("ix_ai_formdata_validation_status", table_name="ai_formdata_validation")
    op.drop_index("ix_ai_formdata_validation_run_by_user_id", table_name="ai_formdata_validation")
    op.drop_index("ix_ai_formdata_validation_form_data_id", table_name="ai_formdata_validation")
    op.drop_table("ai_formdata_validation")
