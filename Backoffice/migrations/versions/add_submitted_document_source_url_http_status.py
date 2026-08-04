"""Add source_url_http_status to submitted_document for FDRS URL probe results.

Revision ID: add_submitted_doc_url_http_status
Revises: add_submission_review_recipient_af
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa


revision = "add_submitted_doc_url_http_status"
down_revision = "add_submission_review_recipient_af"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "submitted_document",
        sa.Column("source_url_http_status", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("submitted_document", "source_url_http_status")
