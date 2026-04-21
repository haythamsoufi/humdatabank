"""Remove template_type from form_template_version

Revision ID: remove_template_type
Revises: add_rbac_tables
Create Date: 2026-01-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "remove_template_type"
down_revision = "add_rbac_tables"
branch_labels = None
depends_on = None


def upgrade():
    # Drop template_type from version-scoped template config
    with op.batch_alter_table("form_template_version", schema=None) as batch_op:
        batch_op.drop_column("template_type")


def downgrade():
    # Restore template_type with a safe default
    with op.batch_alter_table("form_template_version", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "template_type",
                sa.String(length=50),
                nullable=False,
                server_default="operational",
            )
        )
