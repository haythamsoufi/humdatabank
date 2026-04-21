"""Add country linkage to ai_documents

Revision ID: add_country_to_ai_documents
Revises: fix_rbac_access_grant_integrity
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_country_to_ai_documents"
down_revision = "fix_rbac_access_grant_integrity"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.add_column(sa.Column("country_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("country_name", sa.String(length=200), nullable=True))
        batch_op.create_index("ix_ai_documents_country_id", ["country_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_ai_documents_country_id",
            "country",
            ["country_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.drop_constraint("fk_ai_documents_country_id", type_="foreignkey")
        batch_op.drop_index("ix_ai_documents_country_id")
        batch_op.drop_column("country_name")
        batch_op.drop_column("country_id")
