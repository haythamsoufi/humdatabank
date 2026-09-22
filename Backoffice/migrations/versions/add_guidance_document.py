"""Add guidance_document table and AIDocument.guidance_document_id

Revision ID: add_guidance_document
Revises: add_form_data_published_source
Create Date: 2026-09-21

Reusable staff-uploaded guidance files (plugin or system owner) plus a
nullable FK so AI Knowledge Base imports can link to them.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_guidance_document"
down_revision = "add_form_data_published_source"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "guidance_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guidance_document_owner_key", "guidance_document", ["owner_key"])
    op.create_index(
        "ix_guidance_document_owner_uploaded",
        "guidance_document",
        ["owner_key", "uploaded_at"],
    )

    with op.batch_alter_table("ai_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("guidance_document_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_ai_documents_guidance_document_id",
            ["guidance_document_id"],
        )
        batch_op.create_foreign_key(
            "fk_ai_documents_guidance_document_id",
            "guidance_document",
            ["guidance_document_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table("ai_documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_ai_documents_guidance_document_id", type_="foreignkey")
        batch_op.drop_index("ix_ai_documents_guidance_document_id")
        batch_op.drop_column("guidance_document_id")

    op.drop_index("ix_guidance_document_owner_uploaded", table_name="guidance_document")
    op.drop_index("ix_guidance_document_owner_key", table_name="guidance_document")
    op.drop_table("guidance_document")
