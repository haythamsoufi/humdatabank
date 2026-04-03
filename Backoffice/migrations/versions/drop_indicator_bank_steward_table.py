"""Drop indicator_bank_steward table – feature removed

Revision ID: drop_ib_steward_table
Revises: add_data_owner_af
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "drop_ib_steward_table"
down_revision = "add_data_owner_af"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "indicator_bank_steward" not in inspect(conn).get_table_names():
        return
    op.drop_index("ix_ib_steward_user", table_name="indicator_bank_steward", if_exists=True)
    op.drop_index("ix_ib_steward_indicator", table_name="indicator_bank_steward", if_exists=True)
    op.drop_table("indicator_bank_steward")


def downgrade():
    op.create_table(
        "indicator_bank_steward",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("indicator_bank_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["indicator_bank_id"], ["indicator_bank.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("indicator_bank_id", "user_id", name="_ib_steward_uc"),
    )
    op.create_index("ix_ib_steward_indicator", "indicator_bank_steward", ["indicator_bank_id"])
    op.create_index("ix_ib_steward_user", "indicator_bank_steward", ["user_id"])
