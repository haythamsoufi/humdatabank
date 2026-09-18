"""Remove per-section submission flag and assignment_section_status.

Revision ID: drop_section_submission
Revises: rename_upr_visuals_rbac
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa


revision = "drop_section_submission"
down_revision = "rename_upr_visuals_rbac"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_ass_status", table_name="assignment_section_status")
    op.drop_index("ix_ass_section", table_name="assignment_section_status")
    op.drop_index("ix_ass_aes", table_name="assignment_section_status")
    op.drop_table("assignment_section_status")

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_section_submission")


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_section_submission",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column("enable_section_submission", server_default=None)

    op.create_table(
        "assignment_section_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_entity_status_id", sa.Integer(), nullable=False),
        sa.Column("form_section_id", sa.Integer(), nullable=False),
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
            ["form_section_id"],
            ["form_section.id"],
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
            "form_section_id",
            name="uq_aes_section_status",
        ),
    )
    op.create_index("ix_ass_aes", "assignment_section_status", ["assignment_entity_status_id"])
    op.create_index("ix_ass_section", "assignment_section_status", ["form_section_id"])
    op.create_index("ix_ass_status", "assignment_section_status", ["status"])
