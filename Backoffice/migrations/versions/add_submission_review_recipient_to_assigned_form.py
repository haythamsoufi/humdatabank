"""Add submission review recipient settings to assigned_form

Revision ID: add_submission_review_recipient_af
Revises: add_reports_permissions
Create Date: 2026-08-04

"""
from alembic import op
import sqlalchemy as sa


revision = "add_submission_review_recipient_af"
down_revision = "add_reports_permissions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "submission_review_recipient_mode",
                sa.String(length=20),
                nullable=False,
                server_default="fds_member",
            )
        )
        batch_op.add_column(
            sa.Column("submission_review_recipient_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_assigned_form_submission_review_recipient_user",
            "user",
            ["submission_review_recipient_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_assigned_form_submission_review_recipient",
            ["submission_review_recipient_user_id"],
        )


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_index("ix_assigned_form_submission_review_recipient")
        batch_op.drop_constraint(
            "fk_assigned_form_submission_review_recipient_user",
            type_="foreignkey",
        )
        batch_op.drop_column("submission_review_recipient_user_id")
        batch_op.drop_column("submission_review_recipient_mode")
