"""Add enable_export_pdf to assigned_form

Revision ID: add_assignment_pdf_af
Revises: add_assignment_excel_af
Create Date: 2026-08-16

"""
from alembic import op
import sqlalchemy as sa


revision = "add_assignment_pdf_af"
down_revision = "add_assignment_excel_af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_export_pdf",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.execute(
        """
        UPDATE assigned_form af
        SET enable_export_pdf = TRUE
        FROM form_template ft
        INNER JOIN form_template_version ftv ON ft.published_version_id = ftv.id
        WHERE af.template_id = ft.id
          AND ftv.enable_export_pdf = TRUE
        """
    )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column("enable_export_pdf", server_default=None)


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_export_pdf")
