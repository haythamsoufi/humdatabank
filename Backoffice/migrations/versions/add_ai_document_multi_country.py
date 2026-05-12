"""Add multi-country support to ai_documents

Revision ID: add_ai_doc_multi_country
Revises: c9f0a1b2c3d4
Create Date: 2026-02-17

Adds:
- ai_document_countries association table (M2M between ai_documents and country)
- geographic_scope column on ai_documents ('global', 'regional', or NULL for country-specific)
- Migrates existing country_id data into the new M2M table
"""

from alembic import op
import sqlalchemy as sa


revision = "add_ai_doc_multi_country"
down_revision = "c9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Create the M2M association table
    op.create_table(
        "ai_document_countries",
        sa.Column("ai_document_id", sa.Integer(), sa.ForeignKey("ai_documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("country.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_ai_doc_countries_doc_id", "ai_document_countries", ["ai_document_id"])
    op.create_index("ix_ai_doc_countries_country_id", "ai_document_countries", ["country_id"])

    # 2) Add geographic_scope to ai_documents
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.add_column(sa.Column("geographic_scope", sa.String(length=50), nullable=True))

    # 3) Migrate existing country_id into the M2M table
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO ai_document_countries (ai_document_id, country_id) "
            "SELECT id, country_id FROM ai_documents WHERE country_id IS NOT NULL"
        )
    )


def downgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.drop_column("geographic_scope")

    op.drop_index("ix_ai_doc_countries_country_id", table_name="ai_document_countries")
    op.drop_index("ix_ai_doc_countries_doc_id", table_name="ai_document_countries")
    op.drop_table("ai_document_countries")
