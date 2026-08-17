"""Add enable_export_excel and enable_import_excel to assigned_form

Revision ID: add_assignment_excel_af
Revises: add_ucp_excel_af
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa


revision = "add_assignment_excel_af"
down_revision = "add_ucp_excel_af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_export_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "enable_import_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Backfill from published template version flags (previous template-level control).
    op.execute(
        """
        UPDATE assigned_form af
        SET enable_export_excel = TRUE
        FROM form_template ft
        INNER JOIN form_template_version ftv ON ft.published_version_id = ftv.id
        WHERE af.template_id = ft.id
          AND ftv.enable_export_excel = TRUE
        """
    )
    op.execute(
        """
        UPDATE assigned_form af
        SET enable_import_excel = TRUE
        FROM form_template ft
        INNER JOIN form_template_version ftv ON ft.published_version_id = ftv.id
        WHERE af.template_id = ft.id
          AND ftv.enable_import_excel = TRUE
        """
    )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column("enable_export_excel", server_default=None)
        batch_op.alter_column("enable_import_excel", server_default=None)


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_import_excel")
        batch_op.drop_column("enable_export_excel")
