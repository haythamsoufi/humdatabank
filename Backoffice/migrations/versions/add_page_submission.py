"""Add per-page submission flag and assignment_page_status.

Revision ID: add_page_submission
Revises: add_section_submission
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa


revision = "add_page_submission"
down_revision = "add_section_submission"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_page_submission",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column("enable_page_submission", server_default=None)

    op.create_table(
        "assignment_page_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_entity_status_id", sa.Integer(), nullable=False),
        sa.Column("form_page_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("status_changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status_timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_entity_status_id"],
            ["assignment_entity_status.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["form_page_id"],
            ["form_page.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["status_changed_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "assignment_entity_status_id",
            "form_page_id",
            name="uq_aes_page_status",
        ),
    )
    op.create_index("ix_aps_aes", "assignment_page_status", ["assignment_entity_status_id"])
    op.create_index("ix_aps_page", "assignment_page_status", ["form_page_id"])
    op.create_index("ix_aps_status", "assignment_page_status", ["status"])


def downgrade():
    op.drop_index("ix_aps_status", table_name="assignment_page_status")
    op.drop_index("ix_aps_page", table_name="assignment_page_status")
    op.drop_index("ix_aps_aes", table_name="assignment_page_status")
    op.drop_table("assignment_page_status")

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_page_submission")
