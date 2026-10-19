"""Store an external URL on a resource translation.

Revision ID: add_resource_external_url
Revises: fdrs_fields_on_ns
Create Date: 2026-10-19

FDRS global resources include YouTube links. Those are not files in the
uploads container, so the translation keeps the public URL here.
"""
import sqlalchemy as sa
from alembic import op


revision = "add_resource_external_url"
down_revision = "fdrs_fields_on_ns"
branch_labels = None
depends_on = None


def _column_names() -> set[str]:
    bind = op.get_bind()
    return {col["name"] for col in sa.inspect(bind).get_columns("resource_translation")}


def upgrade():
    # The staging sync added this column before the image contained the migration.
    if "external_url" in _column_names():
        return
    with op.batch_alter_table("resource_translation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_url", sa.String(length=1000), nullable=True))


def downgrade():
    if "external_url" not in _column_names():
        return
    with op.batch_alter_table("resource_translation", schema=None) as batch_op:
        batch_op.drop_column("external_url")
