"""Add enable_unified_country_plan_excel to assigned_form

Revision ID: add_ucp_excel_af
Revises: add_upr_cr_excel_af
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa


revision = "add_ucp_excel_af"
down_revision = "add_upr_cr_excel_af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_unified_country_plan_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Template 24 = Unified Country Plan (workbook unified_country_plan.xlsx).
    op.execute(
        """
        UPDATE assigned_form
        SET enable_unified_country_plan_excel = TRUE
        WHERE template_id = 24
        """
    )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column(
            "enable_unified_country_plan_excel",
            server_default=None,
        )


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_unified_country_plan_excel")
