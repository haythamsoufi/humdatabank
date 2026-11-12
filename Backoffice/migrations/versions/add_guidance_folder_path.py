"""Remember the folder a guidance file was uploaded from.

Staff can upload a guidance folder with subfolders. ``folder_path`` keeps
that directory so the library can show the same structure.

Revision ID: add_guidance_folder_path
Revises: add_cancelled_aireasoningtracestatus
Create Date: 2026-11-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "add_guidance_folder_path"
down_revision = "add_cancelled_aireasoningtracestatus"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("guidance_document"):
        return
    cols = {c["name"] for c in insp.get_columns("guidance_document")}
    if "folder_path" not in cols:
        with op.batch_alter_table("guidance_document", schema=None) as batch_op:
            batch_op.add_column(sa.Column("folder_path", sa.String(length=1000), nullable=True))
    indexes = {ix["name"] for ix in inspect(bind).get_indexes("guidance_document")}
    if "ix_guidance_document_owner_folder" not in indexes:
        op.create_index(
            "ix_guidance_document_owner_folder",
            "guidance_document",
            ["owner_key", "folder_path"],
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("guidance_document"):
        return
    indexes = {ix["name"] for ix in insp.get_indexes("guidance_document")}
    if "ix_guidance_document_owner_folder" in indexes:
        op.drop_index("ix_guidance_document_owner_folder", table_name="guidance_document")
    cols = {c["name"] for c in insp.get_columns("guidance_document")}
    if "folder_path" in cols:
        with op.batch_alter_table("guidance_document", schema=None) as batch_op:
            batch_op.drop_column("folder_path")
