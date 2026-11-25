"""Notes linked to an assignment entity's status.

Revision ID: add_aes_status_note
Revises: dref_monitoring_appeal_plan
Create Date: 2026-11-25

Each note stores the status it was written against so later status changes
leave the original comment in place.
"""
from alembic import op
import sqlalchemy as sa


revision = "add_aes_status_note"
down_revision = "dref_monitoring_appeal_plan"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assignment_entity_status_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_entity_status_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_entity_status_id"],
            ["assignment_entity_status.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_aesn_aes",
        "assignment_entity_status_note",
        ["assignment_entity_status_id"],
    )
    op.create_index(
        "ix_aesn_aes_created",
        "assignment_entity_status_note",
        ["assignment_entity_status_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_aesn_aes_created", table_name="assignment_entity_status_note")
    op.drop_index("ix_aesn_aes", table_name="assignment_entity_status_note")
    op.drop_table("assignment_entity_status_note")
