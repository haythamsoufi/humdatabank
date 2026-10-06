"""Add email snapshot attachment flags to assigned_form

Revision ID: add_assignment_email_snap
Revises: add_governance_issue
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa


revision = "add_assignment_email_snap"
down_revision = "add_governance_issue"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "email_attach_pdf",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "email_attach_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column("email_attach_pdf", server_default=None)
        batch_op.alter_column("email_attach_excel", server_default=None)


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("email_attach_excel")
        batch_op.drop_column("email_attach_pdf")
