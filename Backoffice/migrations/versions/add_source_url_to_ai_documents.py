"""Add source_url to ai_documents for URL-only reference documents

Revision ID: add_source_url_ai_docs
Revises: add_country_to_ai_documents
Create Date: 2026-01-29

When set, the document is reference-only (no local file); download/hyperlinks use this URL.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_source_url_ai_docs"
down_revision = "add_part_of_to_national_societies"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.add_column(sa.Column("source_url", sa.String(length=2000), nullable=True))
        batch_op.create_index("ix_ai_documents_source_url", ["source_url"], unique=False)


def downgrade():
    with op.batch_alter_table("ai_documents") as batch_op:
        batch_op.drop_index("ix_ai_documents_source_url")
        batch_op.drop_column("source_url")
