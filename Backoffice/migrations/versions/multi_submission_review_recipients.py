"""Support multiple specific IFRC admins for submission review notifications.

Revision ID: multi_submission_review_recipients
Revises: add_submitted_doc_url_http_status
Create Date: 2026-08-05

"""
from alembic import op
import sqlalchemy as sa


revision = "multi_submission_review_recipients"
down_revision = "add_submitted_doc_url_http_status"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assigned_form_submission_review_recipient",
        sa.Column("assigned_form_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_form_id"],
            ["assigned_form.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("assigned_form_id", "user_id"),
    )
    op.execute(
        """
        INSERT INTO assigned_form_submission_review_recipient (assigned_form_id, user_id)
        SELECT id, submission_review_recipient_user_id
        FROM assigned_form
        WHERE submission_review_recipient_user_id IS NOT NULL
        """
    )
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_index("ix_assigned_form_submission_review_recipient")
        batch_op.drop_constraint(
            "fk_assigned_form_submission_review_recipient_user",
            type_="foreignkey",
        )
        batch_op.drop_column("submission_review_recipient_user_id")


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
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
    op.execute(
        """
        UPDATE assigned_form AS af
        SET submission_review_recipient_user_id = (
            SELECT r.user_id
            FROM assigned_form_submission_review_recipient AS r
            WHERE r.assigned_form_id = af.id
            LIMIT 1
        )
        """
    )
    op.drop_table("assigned_form_submission_review_recipient")
