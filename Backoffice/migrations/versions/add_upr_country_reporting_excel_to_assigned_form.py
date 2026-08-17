"""Add enable_upr_country_reporting_excel to assigned_form

Revision ID: add_upr_cr_excel_af
Revises: add_email_delivery_unknown
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa


revision = "add_upr_cr_excel_af"
down_revision = "add_email_delivery_unknown"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "enable_upr_country_reporting_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Preserve existing T33 assignment behaviour (was previously hardcoded on template id).
    op.execute(
        """
        UPDATE assigned_form
        SET enable_upr_country_reporting_excel = TRUE
        WHERE template_id = 33
        """
    )

    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.alter_column(
            "enable_upr_country_reporting_excel",
            server_default=None,
        )


def downgrade():
    with op.batch_alter_table("assigned_form", schema=None) as batch_op:
        batch_op.drop_column("enable_upr_country_reporting_excel")
